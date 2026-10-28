"""Export frames as H.264 MP4 with the original audio via FFmpeg."""
import subprocess
import math
from visualizer_core import Renderer, Settings, audio_features
from audio_io import load_audio

def export(audio_path, output_path, settings: Settings, ffmpeg='ffmpeg', progress=None,
           start_seconds=0.0, end_seconds=None):
    samples,sample_rate=load_audio(audio_path,ffmpeg=ffmpeg)
    duration=len(samples)/sample_rate
    end_seconds=duration if end_seconds is None else float(end_seconds)
    start_seconds=float(start_seconds)
    if (not math.isfinite(start_seconds) or not math.isfinite(end_seconds)
            or not 0 <= start_seconds < end_seconds <= duration):
        raise ValueError('Export range must satisfy 0 ≤ start < end ≤ audio duration.')
    clip_duration=end_seconds-start_seconds
    frame_count=max(1,math.ceil(round(clip_duration*settings.fps, 9)))
    features=audio_features(samples,sample_rate,settings.fps,settings.bars)
    renderer=Renderer(settings,features)
    cmd=[ffmpeg,'-hide_banner','-loglevel','error','-y','-f','rawvideo','-vcodec','rawvideo',
         '-pix_fmt','rgb24','-s',f'{settings.width}x{settings.height}','-r',str(settings.fps),'-i','pipe:0',
         '-ss',str(start_seconds),'-i',audio_path,'-map','0:v:0','-map','1:a:0','-c:v','libx264','-preset','veryfast',
         '-crf','20','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart','-t',str(clip_duration),'-shortest',output_path]
    proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        for i in range(frame_count):
            proc.stdin.write(renderer.render(start_seconds+i/settings.fps).tobytes())
            if progress and (i%settings.fps==0 or i==frame_count-1):
                progress(i+1,frame_count)
        proc.stdin.close()
        err=proc.stderr.read().decode('utf-8','replace')
        if proc.wait():
            raise RuntimeError(f'FFmpeg export failed: {err[-1000:]}')
    except Exception:
        if proc.poll() is None: proc.kill()
        proc.wait()
        raise
    finally:
        if proc.stdin and not proc.stdin.closed: proc.stdin.close()
        if proc.stderr: proc.stderr.close()
    return output_path
