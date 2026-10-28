from dataclasses import replace
from pathlib import Path
import json
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import wave
from unittest.mock import Mock,patch
import numpy as np
from PIL import Image
from audio_io import load_audio
from export_control import ExportControl,ExportCancelled
from export_diagnostics import ExportReport,report_json
from export_timing import ExportETA
from export_video import export,_encode,EncodingError
from preview_cache import PreviewCache
from video_encoder import CPU_OPTIONS,NVENC_OPTIONS
from visualizer_core import Settings,Renderer,audio_features


class ETATests(unittest.TestCase):
    def test_rate_retry_reset_stall_and_finalization(self):
        eta=ExportETA()
        self.assertIn('estimating',eta.text(now=0))
        eta.update(0,100,now=10);eta.update(10,100,now=11)
        self.assertIn('~00:00:09',eta.text(now=11))
        self.assertIn('estimating',eta.text(now=20))
        eta.update(0,100,now=21)
        self.assertIn('estimating',eta.text(now=21))
        eta.update(100,100,now=31)
        self.assertIn('finalizing',eta.text(now=31))
        eta.finished=True;self.assertEqual(eta.text(now=40),'Remaining: —')


class ControlTests(unittest.TestCase):
    def test_cancel_and_commit_have_a_defined_order(self):
        control=ExportControl();control.cancel();operation=Mock()
        with self.assertRaises(ExportCancelled):control.commit(operation)
        operation.assert_not_called()
        control=ExportControl();control.commit(operation)
        self.assertFalse(control.cancel());control.check()
        operation.assert_called_once()

    def test_cancel_interrupts_registered_subprocess(self):
        control=ExportControl();errors=[]
        def worker():
            try:control.run([sys.executable,'-c','import time; time.sleep(60)'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            except Exception as exc:errors.append(exc)
        thread=threading.Thread(target=worker,daemon=True);thread.start()
        deadline=time.monotonic()+3
        while not control.pids() and time.monotonic()<deadline:time.sleep(.01)
        self.assertTrue(control.pids());control.cancel();thread.join(3)
        self.assertFalse(thread.is_alive());self.assertEqual(control.pids(),[])
        self.assertIsInstance(errors[0],ExportCancelled)

    def test_cancel_interrupts_a_blocked_frame_pipe(self):
        control=ExportControl();ready=threading.Event();errors=[]
        renderer=Mock()
        def render(_):ready.set();return Image.new('RGB',(1024,1024))
        renderer.render.side_effect=render
        real_popen=subprocess.Popen
        def fake_ffmpeg(cmd,**kwargs):
            return real_popen([sys.executable,'-c','import time; time.sleep(60)'],**kwargs)
        def worker():
            try:
                _encode('ffmpeg','source','out.mp4',Settings(width=1024,height=1024),renderer,
                        CPU_OPTIONS,0,1,1,None,control)
            except Exception as exc:errors.append(exc)
        with patch('export_video.subprocess.Popen',side_effect=fake_ffmpeg):
            thread=threading.Thread(target=worker,daemon=True);thread.start()
            self.assertTrue(ready.wait(3));time.sleep(.05)
            self.assertTrue(thread.is_alive());control.cancel();thread.join(3)
        self.assertFalse(thread.is_alive());self.assertEqual(control.pids(),[])
        self.assertIsInstance(errors[0],ExportCancelled)

    def test_analysis_and_particle_setup_accept_cancellation(self):
        check=Mock(side_effect=ExportCancelled())
        with self.assertRaises(ExportCancelled):
            audio_features(np.zeros(22050),22050,30,16,cancel_check=check)
        checks=Mock(side_effect=[None,ExportCancelled()])
        with self.assertRaises(ExportCancelled):
            Renderer(Settings(dust_count=2,bars=16),np.zeros((100,16)),cancel_check=checks)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
class DiagnosticExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.source=self.root/'private song.wav';self.out=self.root/'private output.mp4'
        with wave.open(str(self.source),'wb') as wav:
            wav.setparams((1,2,22050,0,'NONE','not compressed'));wav.writeframes(b'\0\0'*22050)
        self.settings=Settings(width=160,height=90,fps=10,bars=16,dust_count=3,
                               title='Private title',background='',export_encoder='CPU (compatible)')

    def test_successful_cached_export_has_useful_path_free_report(self):
        cache=PreviewCache();cache.prepare(str(self.source),self.settings,load_audio,lambda _:None,audio_features)
        stats=ExportReport(self.settings)
        export(str(self.source),str(self.out),self.settings,cached_analysis=cache.snapshot(),diagnostics=stats)
        data=json.loads(report_json(stats.data))
        self.assertEqual(data['status'],'success');self.assertEqual(data['cache']['reason'],'matching_preview')
        self.assertNotIn('audio_analysis',data['stage_seconds'])
        self.assertEqual(data['attempts'][0]['frames_written'],10)
        self.assertEqual(data['final_encoder'],'libx264')
        self.assertGreater(data['total_seconds'],0)
        self.assertGreater(data['average_frame_render_seconds'],0)
        self.assertGreaterEqual(data['slowest_frame_render_seconds'],data['average_frame_render_seconds'])
        for key in ('render_seconds','pipe_write_seconds','final_wait_seconds'):
            self.assertGreaterEqual(data['attempts'][0][key],0)
        text=report_json(data)
        for private in (str(self.root),'private song','private output','Private title'):
            self.assertNotIn(private,text)
        self.assertIn('Frame rendering',stats.summary())
        self.assertFalse(list(self.root.glob('.dero-export-*')))
        self.assertTrue(stats.monitor is None or not stats.monitor.is_alive())

    def test_cancellation_preserves_output_and_records_canceled_attempt(self):
        self.out.write_bytes(b'keep this existing export')
        control=ExportControl();stats=ExportReport(self.settings)
        def progress(i,n):
            if i==1:control.cancel()
        with self.assertRaises(ExportCancelled):
            export(str(self.source),str(self.out),self.settings,progress=progress,cancel=control,diagnostics=stats)
        self.assertEqual(self.out.read_bytes(),b'keep this existing export')
        self.assertEqual(stats.data['status'],'canceled')
        self.assertEqual(stats.data['attempts'][0]['status'],'canceled')
        self.assertEqual(stats.data['failure_stage'],'render_and_encode')
        self.assertFalse(list(self.root.glob('.dero-export-*')))
        self.assertEqual(control.pids(),[])

    def test_failure_report_does_not_include_exception_paths(self):
        stats=ExportReport(self.settings)
        with patch('export_video._encode',side_effect=EncodingError(str(self.root)+' private log')):
            with self.assertRaises(EncodingError):
                export(str(self.source),str(self.out),self.settings,diagnostics=stats)
        self.assertEqual(stats.data['status'],'failed')
        self.assertEqual(stats.data['error_type'],'EncodingError')
        self.assertNotIn(str(self.root),report_json(stats.data))

    def test_cancel_during_gpu_failure_never_retries_cpu(self):
        control=ExportControl()
        def fail(*args):control.cancel();raise EncodingError('GPU failed')
        with patch('export_video.select_encoder',return_value=('h264_nvenc',NVENC_OPTIONS)),patch('export_video._encode',side_effect=fail) as encode:
            with self.assertRaises(ExportCancelled):export(str(self.source),str(self.out),self.settings,cancel=control)
            encode.assert_called_once()
        self.assertFalse(list(self.root.glob('.dero-export-*')))

    def test_cache_miss_is_explained(self):
        cache=PreviewCache();cache.prepare(str(self.source),self.settings,load_audio,lambda _:None,audio_features)
        stats=ExportReport(replace(self.settings,bars=32))
        export(str(self.source),str(self.out),replace(self.settings,bars=32),cached_analysis=cache.snapshot(),diagnostics=stats)
        self.assertEqual(stats.data['cache']['reason'],'analysis_settings_changed')
        self.assertIn('audio_decode',stats.data['stage_seconds']);self.assertIn('audio_analysis',stats.data['stage_seconds'])

    def test_preparation_cancel_has_report_and_no_process_or_output(self):
        control=ExportControl();control.cancel();stats=ExportReport(self.settings)
        with self.assertRaises(ExportCancelled):
            export(str(self.source),str(self.out),self.settings,cancel=control,diagnostics=stats)
        self.assertEqual(stats.data['status'],'canceled')
        self.assertEqual(stats.data['attempts'],[]);self.assertEqual(control.pids(),[])
        self.assertFalse(self.out.exists())

    def test_unavailable_memory_monitor_does_not_prevent_export(self):
        with patch('export_diagnostics.psutil',None):
            stats=ExportReport(self.settings)
            export(str(self.source),str(self.out),self.settings,diagnostics=stats)
        self.assertEqual(stats.data['status'],'success')
        self.assertFalse(stats.data['memory']['available'])
        self.assertIn('Frame rendering',stats.summary())
        self.assertIn('unavailable',stats.summary())

    def test_cancel_reports_canceled_even_if_platform_pipe_raises_oserror(self):
        control=ExportControl();stats=ExportReport(self.settings)
        def fail(*args):control.cancel();raise OSError('platform pipe closed')
        with patch('export_video._encode',side_effect=fail):
            with self.assertRaises(ExportCancelled):
                export(str(self.source),str(self.out),self.settings,cancel=control,diagnostics=stats)
        self.assertEqual(stats.data['status'],'canceled')
        self.assertFalse(self.out.exists())
