"""Export frames as H.264 MP4 with the original audio via FFmpeg."""
import subprocess
import math
import os
import tempfile
from video_encoder import select_encoder, CPU_OPTIONS
from visualizer_core import Renderer, Settings, audio_features
from audio_io import load_audio

def export(audio_path, output_path, settings: Settings, ffmpeg='ffmpeg', progress=None,
           start_seconds=0.0, end_seconds=None, cached_analysis=None, encoder_status=None):
    """Reuse a matching preview snapshot; otherwise decode/analyze normally."""
    reuse=(ffmpeg=='ffmpeg' and cached_analysis is not None
           and cached_analysis.matches(audio_path,settings))
    if reuse:
        samples,sample_rate=cached_analysis.samples,cached_analysis.sample_rate
    else:
        samples,sample_rate=load_audio(audio_path,sample_rate=44100 if settings.frequency_max>10584 else 22050,ffmpeg=ffmpeg)
    duration=len(samples)/sample_rate
    end_seconds=duration if end_seconds is None else float(end_seconds)
    start_seconds=float(start_seconds)
    if (not math.isfinite(start_seconds) or not math.isfinite(end_seconds)
            or not 0 <= start_seconds < end_seconds <= duration):
        raise ValueError('Export range must satisfy 0 ≤ start < end ≤ audio duration.')
    clip_duration=end_seconds-start_seconds
    frame_count=max(1,math.ceil(round(clip_duration*settings.fps, 9)))
    features=(cached_analysis.features if reuse else
              audio_features(samples,sample_rate,settings.fps,settings.bars,settings.frequency_min,settings.frequency_max,settings.frequency_scale,settings.spectrum_mapping))
    renderer=Renderer(settings,features)
    codec,options=select_encoder(settings,ffmpeg,encoder_status)
    # Encode beside the destination, replacing it only after success. A failed
    # GPU attempt cannot leave a corrupt MP4 or destroy an existing export.
    destination=os.path.abspath(output_path)
    fd,temporary=tempfile.mkstemp(prefix='.dero-export-',suffix='.mp4',dir=os.path.dirname(destination))
    os.close(fd)
    try:
        try:
            _encode(ffmpeg,audio_path,temporary,settings,renderer,options,
                    start_seconds,clip_duration,frame_count,progress)
        except EncodingError as exc:
            if codec=='libx264':raise
            if encoder_status:encoder_status('CPU fallback: NVIDIA encoding failed; restarting export. '+str(exc)[-500:])
            _encode(ffmpeg,audio_path,temporary,settings,renderer,CPU_OPTIONS,
                    start_seconds,clip_duration,frame_count,progress)
        os.replace(temporary,destination)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)
    return output_path


class EncodingError(RuntimeError):
    """FFmpeg failed, as distinct from a frame-rendering or application error."""


def _encode(ffmpeg,audio_path,output_path,settings,renderer,options,
            start_seconds,clip_duration,frame_count,progress):
    cmd=[ffmpeg,'-hide_banner','-loglevel','error','-y','-f','rawvideo','-vcodec','rawvideo',
         '-pix_fmt','rgb24','-s',f'{settings.width}x{settings.height}','-r',str(settings.fps),'-i','pipe:0',
         '-ss',str(start_seconds),'-i',audio_path,'-map','0:v:0','-map','1:a:0',*options,
         '-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart','-t',str(clip_duration),'-shortest',output_path]
    # A file avoids filling stderr's pipe while we are feeding RGB frames.
    with tempfile.TemporaryFile() as errors:
        proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=errors)
        try:
            try:
                for i in range(frame_count):
                    proc.stdin.write(renderer.render(start_seconds+i/settings.fps).tobytes())
                    if progress and (i%settings.fps==0 or i==frame_count-1):
                        progress(i+1,frame_count)
                proc.stdin.close()
            except BrokenPipeError:
                # Read the actual encoder failure instead of exposing a pipe error.
                try:proc.stdin.close()
                except BrokenPipeError:pass
            code=proc.wait()
            errors.seek(0,os.SEEK_END)
            size=errors.tell();errors.seek(max(0,size-2000))
            message=errors.read().decode('utf-8','replace')
            if code or not os.path.isfile(output_path) or os.path.getsize(output_path)==0:
                raise EncodingError('FFmpeg export failed: '+message)
        finally:
            if proc.poll() is None:proc.kill()
            proc.wait()
            if proc.stdin and not proc.stdin.closed:
                try:proc.stdin.close()
                except BrokenPipeError:pass
