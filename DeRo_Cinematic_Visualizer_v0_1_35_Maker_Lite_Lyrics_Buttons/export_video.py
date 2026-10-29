"""Deterministic H.264 exports with cancellation and local performance evidence."""
import subprocess
import math
import os
import tempfile
import time
from export_control import ExportControl,ExportCancelled
from export_diagnostics import ExportReport
from video_encoder import select_encoder,CPU_OPTIONS
from visualizer_core import Renderer,Settings,audio_features
from audio_io import load_audio
from lyric_render import lyric_overlay,IdentityRenderer,ass_filter
from lyric_model import LyricDocument
from contextlib import ExitStack


def export(audio_path,output_path,settings: Settings,ffmpeg='ffmpeg',progress=None,
           start_seconds=0.0,end_seconds=None,cached_analysis=None,encoder_status=None,
           cancel=None,diagnostics=None,lyric_document=None):
    """Optional control/report arguments preserve the existing path-return API."""
    control=cancel if cancel is not None else ExportControl()
    stats=diagnostics if diagnostics is not None else ExportReport(settings)
    status='failed';error=None
    resources=ExitStack()
    try:
        control.check()
        if diagnostics is not None:
            stats.start_monitor(control)
            stats.environment(ffmpeg,control)
        reason=('custom_ffmpeg' if ffmpeg!='ffmpeg' else 'no_preview_cache' if cached_analysis is None else
                cached_analysis.mismatch_reason(audio_path,settings))
        reuse=reason is None
        stats.data['cache']={'reused':reuse,'reason':'matching_preview' if reuse else reason}
        if reuse:samples,sample_rate=cached_analysis.samples,cached_analysis.sample_rate
        else:
            with stats.stage('audio_decode'):
                samples,sample_rate=load_audio(audio_path,sample_rate=44100 if settings.frequency_max>10584 else 22050,
                                              ffmpeg=ffmpeg,cancel=control)
        control.check()
        stats.current_stage='selection_validation'
        duration=len(samples)/sample_rate
        end_seconds=duration if end_seconds is None else float(end_seconds)
        start_seconds=float(start_seconds)
        if (not math.isfinite(start_seconds) or not math.isfinite(end_seconds)
                or not 0<=start_seconds<end_seconds<=duration):
            raise ValueError('Export range must satisfy 0 ≤ start < end ≤ audio duration.')
        clip_duration=end_seconds-start_seconds
        frame_count=max(1,math.ceil(round(clip_duration*settings.fps,9)))
        stats.data.update(selection_start_seconds=start_seconds,selection_duration_seconds=clip_duration,
                          source_duration_seconds=duration,target_frames=frame_count,sample_rate=sample_rate)
        if reuse:features=cached_analysis.features
        else:
            with stats.stage('audio_analysis'):
                features=audio_features(samples,sample_rate,settings.fps,settings.bars,settings.frequency_min,
                                        settings.frequency_max,settings.frequency_scale,settings.spectrum_mapping,
                                        cancel_check=control.check)
        control.check()
        with stats.stage('renderer_preparation'):
            renderer=Renderer(settings,features,cancel_check=control.check)
        doc=LyricDocument(lyric_document)
        overlay=resources.enter_context(lyric_overlay(doc.snapshot(),settings,ffmpeg,control))
        if overlay is not None:renderer=IdentityRenderer(renderer,doc)
        stats.data['lyrics']={'enabled':overlay is not None,'lines':len(doc.events),'warnings':len(doc.warnings())}
        def report_encoder(message):
            stats.encoder(message)
            if encoder_status:encoder_status(message)
        with stats.stage('encoder_probe'):
            codec,options=select_encoder(settings,ffmpeg,report_encoder,control)
        control.check()
        with stats.stage('output_preparation'):
            destination=os.path.abspath(output_path)
            fd,temporary=tempfile.mkstemp(prefix='.dero-export-',suffix='.mp4',dir=os.path.dirname(destination))
            os.close(fd)
        try:
            with stats.stage('render_and_encode'):
                try:
                    _encode(ffmpeg,audio_path,temporary,settings,renderer,options,
                            start_seconds,clip_duration,frame_count,progress,control,stats,overlay)
                except EncodingError as exc:
                    control.check()
                    if codec=='libx264':raise
                    report_encoder('CPU fallback: NVIDIA encoding failed; restarting export. '+str(exc)[-500:])
                    _encode(ffmpeg,audio_path,temporary,settings,renderer,CPU_OPTIONS,
                            start_seconds,clip_duration,frame_count,progress,control,stats,overlay)
            with stats.stage('publish_output'):
                control.commit(lambda:os.replace(temporary,destination))
        finally:
            if os.path.exists(temporary):os.unlink(temporary)
        status='success'
        return output_path
    except ExportCancelled as exc:
        status='canceled';error=exc;raise
    except Exception as exc:
        if control.event.is_set():
            status='canceled';error=ExportCancelled('Export canceled')
            raise error from exc
        error=exc;raise
    finally:
        resources.close()
        stats.finish(status,error)


class EncodingError(RuntimeError):
    """FFmpeg failure, distinct from rendering errors and cancellation."""


def _encode(ffmpeg,audio_path,output_path,settings,renderer,options,
            start_seconds,clip_duration,frame_count,progress,control=None,stats=None,overlay=None):
    control=control if control is not None else ExportControl()
    attempt={'encoder':options[options.index('-c:v')+1],'status':'running',
             'frames_rendered':0,'frames_written':0,'render_seconds':0.,
             'slowest_frame_seconds':0.,'pipe_write_seconds':0.,'final_wait_seconds':0.}
    if stats is not None:stats.data['attempts'].append(attempt)
    cmd=[ffmpeg,'-hide_banner','-loglevel','error','-y','-f','rawvideo','-vcodec','rawvideo',
         '-pix_fmt','rgb24','-s',f'{settings.width}x{settings.height}','-r',str(settings.fps),'-i','pipe:0',
         '-ss',str(start_seconds),'-i',os.path.abspath(audio_path),'-map','0:v:0','-map','1:a:0',
         *(['-filter_threads','1','-vf',ass_filter(start_seconds)] if overlay else []),*options,
         '-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart','-t',str(clip_duration),'-shortest',os.path.abspath(output_path)]
    try:
        control.check()
        # Disk-backed stderr avoids blocking the frame writer on an unread pipe.
        with tempfile.TemporaryFile() as errors:
            proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=errors,**({'cwd':overlay} if overlay else {}))
            try:
                with control.process(proc):
                    if progress:progress(0,frame_count) # restart ETA on a CPU retry
                    try:
                        for i in range(frame_count):
                            control.check();started=time.perf_counter()
                            frame=renderer.render(start_seconds+i/settings.fps).tobytes()
                            elapsed=time.perf_counter()-started
                            attempt['render_seconds']+=elapsed
                            attempt['slowest_frame_seconds']=max(attempt['slowest_frame_seconds'],elapsed)
                            attempt['frames_rendered']+=1
                            control.check();started=time.perf_counter()
                            try:proc.stdin.write(frame)
                            finally:attempt['pipe_write_seconds']+=time.perf_counter()-started
                            attempt['frames_written']+=1
                            if progress and (i%settings.fps==0 or i==frame_count-1):progress(i+1,frame_count)
                        started=time.perf_counter()
                        try:proc.stdin.close()
                        finally:attempt['pipe_write_seconds']+=time.perf_counter()-started
                    except BrokenPipeError:
                        control.check()
                        try:proc.stdin.close()
                        except BrokenPipeError:pass
                    control.check();started=time.perf_counter()
                    try:code=proc.wait()
                    finally:attempt['final_wait_seconds']+=time.perf_counter()-started
                    control.check()
                    errors.seek(0,os.SEEK_END);size=errors.tell();errors.seek(max(0,size-2000))
                    message=errors.read().decode('utf-8','replace')
                    if code or not os.path.isfile(output_path) or os.path.getsize(output_path)==0:
                        raise EncodingError('FFmpeg export failed: '+message)
            finally:
                if proc.stdin and not proc.stdin.closed:
                    try:proc.stdin.close()
                    except BrokenPipeError:pass
        attempt['status']='success'
    except ExportCancelled:
        attempt['status']='canceled';raise
    except Exception:
        if control.event.is_set():
            attempt['status']='canceled'
            raise ExportCancelled('Export canceled')
        attempt['status']='failed';raise
