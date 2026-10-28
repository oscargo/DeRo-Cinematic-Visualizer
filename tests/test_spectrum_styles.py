from pathlib import Path
import tempfile
import unittest
import numpy as np
from PIL import ImageChops
from project_io import DEFAULTS,load_project,save_project,validate_settings
from visualizer_core import Renderer,Settings,audio_features
from export_video import export
import shutil,subprocess,json


class SpectrumStylesTests(unittest.TestCase):
    def test_styles_and_density_make_different_images(self):
        features=np.linspace(.1,.9,64,dtype=np.float32)[None,:]
        images={}
        for style in ('Classic bars','Gradient bars','Glow bars','Reflected bars','Filled spectrum'):
            s=Settings(width=320,height=180,title='',dust_count=0,bars=64,spectrum_y=.65,
                       spectrum_height=.2,spectrum_style=style)
            images[style]=Renderer(s,features).render(0)
        base=images['Classic bars']
        for style,image in images.items():
            if style!='Classic bars':self.assertIsNotNone(ImageChops.difference(base,image).getbbox(),style)
        sparse=Renderer(Settings(width=320,height=180,title='',dust_count=0,bars=64,
                                spectrum_y=.65,spectrum_height=.2,spectrum_density=.5),features).render(0)
        self.assertIsNotNone(ImageChops.difference(base,sparse).getbbox())

    def test_narrow_bass_bands_are_not_copied_from_one_fft_bin(self):
        sr=22050;t=np.arange(sr)/sr
        features=audio_features(np.sin(2*np.pi*73*t),sr,10,384)[5]
        # These early narrow bands used to round to the same FFT bin.
        self.assertGreater(len(np.unique(np.round(features[:6],5))),4)
        self.assertTrue(np.isfinite(features).all())

    def test_high_density_interpolates_instead_of_duplicating_bars(self):
        renderer=Renderer(Settings(width=1920,height=1080,bars=16,dust_count=0,title='',
            spectrum_mirrored=False,spectrum_density=2,spectrum_height=.3))
        layer=np.asarray(renderer.spectrum_layer(np.linspace(.1,.9,16)))
        count=32;span=1920*.82;step=span/(count+2)
        xs=np.round(960+(np.arange(count)-(count-1)/2)*step).astype(int)
        tops=[int(np.flatnonzero(layer[:,x,3])[0]) for x in xs]
        self.assertGreater(len(set(tops)),24)

    def test_high_frequency_analysis_and_invalid_ranges(self):
        sr=44100;t=np.arange(sr)/sr
        features=audio_features(np.sin(2*np.pi*16000*t),sr,10,128,14000,18000,'Linear')
        centers=np.linspace(14000,18000,129)
        peak=int(np.argmax(features[5]))
        self.assertLess(abs((centers[peak]+centers[peak+1])/2-16000),100)
        with self.assertRaises(ValueError):audio_features(np.zeros(100),22050,10,32,20,20000)
        with self.assertRaises(ValueError):validate_settings(dict(DEFAULTS,frequency_min=5000,frequency_max=1000))

    def test_options_roundtrip_and_reactive_sources(self):
        values=dict(DEFAULTS,bands=1024,spectrum_density=150.,spectrum_fill=25.,
                    frequency_min=20.,frequency_max=20000.,spectrum_style='Reflected bars',
                    spectrum_mirrored=False,particle_reactivity='Treble')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'styles.dero';save_project(path,values)
            self.assertEqual(load_project(path)[0],values)
        s=Settings(bars=32,frequency_min=20,frequency_max=20000,particle_reactivity='Treble',dust_count=0)
        r=Renderer(s)
        values=np.zeros(32,np.float32);values[-4:]=1
        self.assertGreater(float(r.reactive_energy(values)),0)
        s.particle_reactivity='Bass'
        self.assertEqual(float(r.reactive_energy(values)),0)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
    def test_export_full_range_with_new_style(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio=Path(tmp)/'source.wav';out=Path(tmp)/'Artist - Song.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=16000:sample_rate=44100:duration=0.3',str(audio)],check=True)
            export(str(audio),str(out),Settings(width=160,height=90,fps=10,bars=128,dust_count=0,
                frequency_min=20,frequency_max=20000,spectrum_style='Filled spectrum',spectrum_mirrored=False))
            metadata=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(out)]))
            self.assertEqual({s['codec_type'] for s in metadata['streams']},{'audio','video'})
