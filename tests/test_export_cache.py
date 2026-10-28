from dataclasses import replace
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import wave
from unittest.mock import Mock,patch
import numpy as np
from audio_io import load_audio
from export_video import export
from preview_cache import PreviewCache
from visualizer_core import Settings,audio_features
from visualizer_app import Application
from project_io import DEFAULTS


class ExportCacheTests(unittest.TestCase):
    def test_snapshot_keys_and_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source.wav';path.write_bytes(b'first')
            settings=Settings()
            cache=PreviewCache()
            self.assertIsNone(cache.snapshot())
            cache.prepare(str(path),settings,lambda *a,**k:(np.zeros(100),22050),
                          lambda _:None,lambda *a:np.zeros((1,384)))
            snapshot=cache.snapshot()
            self.assertTrue(snapshot.matches(str(path),replace(settings,width=640,height=360,title='Different')))
            for key,value in [('fps',30),('bars',32),('frequency_min',60),
                              ('frequency_max',18000),('frequency_scale','Linear'),('spectrum_mapping','Stepped')]:
                self.assertFalse(snapshot.matches(str(path),replace(settings,**{key:value})))
            cache.features=np.ones((1,384))
            self.assertIsNot(snapshot.features,cache.features)
            path.write_bytes(b'other')
            self.assertFalse(snapshot.matches(str(path),settings))

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
    def test_cached_and_fresh_exports_match_and_stale_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.wav'
            rate=22050;t=np.arange(rate*2)/rate
            tone=np.sin(2*np.pi*np.where(t<1,220,880)*t)
            with wave.open(str(source),'wb') as wav:
                wav.setparams((1,2,rate,0,'NONE','not compressed'))
                wav.writeframes((tone*16000).astype('<i2').tobytes())
            settings=Settings(width=160,height=90,fps=10,bars=16,dust_count=4)
            cache=PreviewCache()
            cache.prepare(str(source),settings,load_audio,lambda _:None,audio_features)
            snapshot=cache.snapshot()
            args=dict(start_seconds=1,end_seconds=1.5)
            with patch('export_video.load_audio',side_effect=AssertionError('decoded again')),patch('export_video.audio_features',side_effect=AssertionError('analyzed again')):
                export(str(source),str(root/'cached.mp4'),settings,cached_analysis=snapshot,**args)
            export(str(source),str(root/'fresh.mp4'),settings,**args)
            for stream,options in [('video',['-an','-f','rawvideo','-pix_fmt','rgb24']),
                                   ('audio',['-vn','-f','s16le'])]:
                def decoded(name):
                    return subprocess.check_output(['ffmpeg','-v','error','-i',str(root/name),*options,'pipe:1'])
                self.assertEqual(decoded('cached.mp4'),decoded('fresh.mp4'),stream)
            # Changing an analysis input must execute the normal pipeline.
            with patch('export_video.load_audio',wraps=load_audio) as load,patch('export_video.audio_features',wraps=audio_features) as analyze:
                export(str(source),str(root/'changed.mp4'),replace(settings,bars=32),cached_analysis=snapshot,**args)
                load.assert_called_once();analyze.assert_called_once()
            source.touch()
            with patch('export_video.load_audio',wraps=load_audio) as load:
                export(str(source),str(root/'stale.mp4'),settings,cached_analysis=snapshot,**args)
                load.assert_called_once()

    def test_gui_passes_captured_snapshot_to_export_worker(self):
        app=Mock()
        app.busy=False;app.audio.get.return_value='source.wav'
        app.loaded_audio_path='source.wav'
        app.selection_bounds.return_value=(0,1)
        app.project_vars={key:Mock(get=Mock(return_value=value)) for key,value in DEFAULTS.items()}
        app.settings.return_value=Settings();app.progress={}
        app.filename_stem.return_value='test'
        snapshot=app.preview_cache.snapshot.return_value
        with patch('visualizer_app.os.path.isfile',return_value=True), \
             patch('visualizer_app.os.path.getsize',return_value=100), \
             patch('visualizer_app.shutil.which',return_value='ffmpeg'), \
             patch('visualizer_app.filedialog.asksaveasfilename',return_value='out.mp4'), \
             patch('visualizer_app.threading.Thread') as thread, \
             patch('visualizer_app.export') as run:
            Application.export_file(app)
            app.preview_cache.snapshot.assert_called_once()
            thread.call_args.kwargs['target']()
            self.assertIs(run.call_args.kwargs['cached_analysis'],snapshot)
            self.assertEqual(run.call_args.kwargs['start_seconds'],0)
            self.assertEqual(run.call_args.kwargs['end_seconds'],1)
