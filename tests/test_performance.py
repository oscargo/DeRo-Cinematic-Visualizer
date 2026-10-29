from concurrent.futures import Future
from dataclasses import replace
from pathlib import Path
from queue import Queue
import tempfile
import unittest
from unittest.mock import Mock,patch
import numpy as np
from preview_cache import PreviewCache
from visualizer_app import Application
from visualizer_core import Renderer,Settings,_load_font


class PerformanceTests(unittest.TestCase):
    def test_disabled_particles_and_live_enable_match_fresh_renderer(self):
        features=np.zeros((60,16),np.float32)
        settings=Settings(width=160,height=90,bars=16,dust_count=12,particles_enabled=False)
        with patch.object(Renderer,'_make_particles',side_effect=AssertionError('unused')):
            renderer=Renderer(settings,features)
            renderer.render(1)
        self.assertEqual(renderer.trajectories.nbytes+renderer.particle_fades.nbytes,0)
        settings.particles_enabled=True
        expected=Renderer(replace(settings),features)
        self.assertEqual(renderer.render(1).tobytes(),expected.render(1).tobytes())
        renderer.render(0)
        self.assertEqual(renderer.render(1).tobytes(),expected.render(1).tobytes())

    def test_font_cache_tracks_size_and_style(self):
        _load_font.cache_clear()
        renderer=Renderer(Settings(width=160,height=90,dust_count=0))
        first=renderer.title_font()
        self.assertIs(first,renderer.title_font())
        renderer.s.title_size*=2
        self.assertIsNot(first,renderer.title_font())
        self.assertLessEqual(_load_font.cache_info().currsize,64)

    def test_audio_cache_invalidates_source_and_analysis_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'audio.wav';path.write_bytes(b'first')
            cache=PreviewCache();settings=Settings(bars=16)
            load=Mock(return_value=(np.zeros(100),22050))
            decode=Mock(return_value=np.zeros((100,2)))
            analyze=Mock(return_value=np.zeros((2,16)))
            def prepare():return cache.prepare(str(path),settings,load,decode,analyze)
            prepare();prepare()
            self.assertEqual((load.call_count,decode.call_count,analyze.call_count),(1,1,1))
            for field,value in [('fps',30),('bars',32),('frequency_min',60),
                                ('frequency_scale','Logarithmic'),('spectrum_mapping','Smooth')]:
                setattr(settings,field,value);prepare()
            self.assertEqual(load.call_count,1)
            self.assertEqual(analyze.call_count,6)
            path.write_bytes(b'other') # same path and size
            prepare()
            self.assertEqual((load.call_count,decode.call_count,analyze.call_count),(2,2,7))
            settings.frequency_max=18000;prepare()
            self.assertEqual(load.call_args.kwargs['sample_rate'],44100)

    def test_worker_copies_settings_and_cancels_queued_edit(self):
        app=Application.__new__(Application)
        app.renderer=Renderer(Settings(dust_count=0,width=160,height=90))
        app.features=np.zeros((2,16));app.q=Queue()
        app.particle_request=None;app.particle_future=None;app.particle_generation=0
        app.particle_executor=Mock()
        first=Future();second=Future()
        app.particle_executor.submit.side_effect=[first,second]
        app.request_particle_preview({'dust_count':5})
        submitted=app.particle_executor.submit.call_args.args[1]
        self.assertEqual(app.renderer.s.dust_count,0)
        self.assertEqual(submitted.dust_count,5)
        app.request_particle_preview({'dust_count':6})
        self.assertTrue(first.cancelled())
        app.request_particle_preview({'dust_count':6})
        self.assertEqual(app.particle_executor.submit.call_count,2)
        second.set_result('new renderer')
        kind,(generation,source,result,error)=app.q.get_nowait()
        self.assertEqual((kind,generation,result,error),('particles_ready',2,'new renderer',None))

    def test_poll_discards_old_generation_and_replaced_source(self):
        app=Application.__new__(Application)
        app.q=Queue();app.root=Mock();app.status=Mock()
        app.apply_layout_preview=Mock();app.particle_generation=3
        source=object();app.renderer=source
        app.q.put(('particles_ready',(2,source,'obsolete',None)))
        app.q.put(('particles_ready',(3,object(),'wrong source',None)))
        app.poll()
        self.assertIs(app.renderer,source)
        app.apply_layout_preview.assert_not_called()
        app.q.put(('particles_ready',(3,source,'latest',None)))
        app.poll()
        self.assertEqual(app.renderer,'latest')
        app.apply_layout_preview.assert_called_once()

    def test_file_changed_during_decode_is_not_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'audio.wav';path.write_bytes(b'first')
            cache=PreviewCache()
            def decode(_):path.write_bytes(b'other');return np.zeros((2,2))
            with self.assertRaisesRegex(OSError,'changed while loading'):
                cache.prepare(str(path),Settings(),Mock(return_value=(np.zeros(2),22050)),decode,Mock())
            self.assertIsNone(cache.source_key)
