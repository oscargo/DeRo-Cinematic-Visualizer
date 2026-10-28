"""Local, path-free performance evidence. No media or raw subprocess logs."""
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime,timezone
import json
import platform
import shutil
import subprocess
import threading
import time
import numpy as np
import PIL
try:
    import psutil
except (ImportError,OSError):
    psutil=None

APP_VERSION='0.1.30'


class ExportReport:
    def __init__(self,settings):
        allowed=('width','height','fps','bars','frequency_min','frequency_max',
                 'frequency_scale','spectrum_mapping','spectrum_style','spectrum_density',
                 'dust_count','particles_enabled','particle_continuous','particle_speed',
                 'particle_direction','particle_reactive','reactive_fraction','export_encoder')
        values=asdict(settings)
        self.data={'schema_version':1,'app_version':APP_VERSION,
                   'created_utc':datetime.now(timezone.utc).isoformat(),
                   'settings':{k:values[k] for k in allowed},
                   'versions':{'python':platform.python_version(),'numpy':np.__version__,
                               'pillow':PIL.__version__,'os':platform.system(),
                               'os_release':platform.release(),'architecture':platform.machine(),
                               'logical_cpu_count':psutil.cpu_count() if psutil is not None else None,
                               'ffmpeg':None,'nvidia_devices':[]},
                   'stage_seconds':{},'encoder_events':[],'attempts':[],
                   'cache':{'reused':False,'reason':'not_checked'},
                   'memory':{'available':False,'sampling_interval_seconds':.25,
                             'app_sampled_peak_rss_bytes':None,
                             'tracked_subprocess_sampled_peak_rss_bytes':None,
                             'scope':'application RSS includes preview and other in-process work; FFmpeg and environment-check subprocesses tracked separately'},
                   'status':'running','failure_stage':None,'error_type':None,
                   'timing_notes':'Rendering and FFmpeg encoding overlap. Pipe-write time includes transfer and backpressure, not isolated encoder runtime. Renderer preparation includes particles and background. Attempts include any retried frames.'}
        self.started=time.perf_counter()
        self.done=threading.Event();self.monitor=None;self.current_stage='preparation'

    @contextmanager
    def stage(self,name):
        self.current_stage=name;started=time.perf_counter()
        try:yield
        except Exception:
            self.data['failure_stage']=name
            raise
        finally:
            stages=self.data['stage_seconds']
            stages[name]=stages.get(name,0)+time.perf_counter()-started

    def start_monitor(self,control):
        if psutil is None:return
        def sample():
            try:
                memory=self.data['memory'];rss=psutil.Process().memory_info().rss
                memory['available']=True
                memory['app_sampled_peak_rss_bytes']=max(memory['app_sampled_peak_rss_bytes'] or 0,rss)
                child=0
                for pid in control.pids():
                    try:child+=psutil.Process(pid).memory_info().rss
                    except (psutil.Error,OSError):pass
                memory['tracked_subprocess_sampled_peak_rss_bytes']=max(memory['tracked_subprocess_sampled_peak_rss_bytes'] or 0,child)
            except (psutil.Error,OSError):pass
        def monitor():
            sample()
            while not self.done.wait(.25):sample()
            sample()
        self.monitor=threading.Thread(target=monitor,daemon=True);self.monitor.start()

    def environment(self,ffmpeg,control):
        with self.stage('environment_checks'):
            try:
                result=control.run([ffmpeg,'-version'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=3)
                words=result.stdout.decode('utf-8','replace').split()
                if result.returncode==0 and len(words)>2:self.data['versions']['ffmpeg']=words[2]
            except (OSError,subprocess.TimeoutExpired):pass
            if shutil.which('nvidia-smi'):
                try:
                    result=control.run(['nvidia-smi','--query-gpu=name,driver_version','--format=csv,noheader'],
                                       stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=3)
                    if result.returncode==0:
                        self.data['versions']['nvidia_devices']=[line.strip() for line in result.stdout.decode('utf-8','replace').splitlines()[:8]]
                except (OSError,subprocess.TimeoutExpired):pass

    def encoder(self,message):
        if message.startswith('NVIDIA NVENC'):kind='nvidia_nvenc';reason=None
        elif message.startswith('CPU fallback'):
            kind='cpu_fallback';text=message.lower()
            reason=('driver_unavailable' if 'libcuda' in text or 'nvcuda' in text else
                    'encoder_missing' if 'unknown encoder' in text else
                    'probe_timeout' if 'timed out' in text else
                    'runtime_encode_failure' if 'restarting export' in text else 'gpu_probe_failed')
        else:kind='cpu';reason=None
        self.data['encoder_events'].append({'encoder':kind,'reason':reason})

    def finish(self,status,error=None):
        self.done.set()
        if self.monitor:self.monitor.join(timeout=1)
        self.data['status']=status
        self.data['total_seconds']=max(0,time.perf_counter()-self.started)
        self.data['error_type']=type(error).__name__ if error is not None else None
        if error is not None and self.data['failure_stage'] is None:self.data['failure_stage']=self.current_stage
        attempts=self.data['attempts'];frames=sum(a['frames_rendered'] for a in attempts)
        self.data['final_encoder']=attempts[-1]['encoder'] if attempts else None
        render=sum(a['render_seconds'] for a in attempts)
        self.data['frames_rendered_all_attempts']=frames
        self.data['average_frame_render_seconds']=render/frames if frames else None
        self.data['slowest_frame_render_seconds']=max((a['slowest_frame_seconds'] for a in attempts),default=0)
        self.data['effective_export_fps']=(self.data.get('target_frames',0)/self.data['total_seconds']
                                          if status=='success' and self.data['total_seconds']>0 else None)

    def summary(self):
        d=self.data
        stages=d['stage_seconds'];attempts=d['attempts']
        render=sum(a['render_seconds'] for a in attempts)
        feed=sum(a['pipe_write_seconds'] for a in attempts)
        finish=sum(a['final_wait_seconds'] for a in attempts)
        memory=d['memory']['app_sampled_peak_rss_bytes']
        memory_text=f'{memory/1048576:.1f} MiB' if memory is not None else 'unavailable'
        return (f"Export {d['status']} in {d.get('total_seconds',0):.1f}s. "
                f"Cache: {d['cache']['reason']}.\n"
                f"Decode {stages.get('audio_decode',0):.2f}s; analysis {stages.get('audio_analysis',0):.2f}s; "
                f"renderer setup {stages.get('renderer_preparation',0):.2f}s.\n"
                f"Frame rendering {render:.2f}s; FFmpeg pipe writes {feed:.2f}s; final wait {finish:.2f}s.\n"
                f"App sampled peak RAM: {memory_text}.")



def report_json(data):
    return json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)
