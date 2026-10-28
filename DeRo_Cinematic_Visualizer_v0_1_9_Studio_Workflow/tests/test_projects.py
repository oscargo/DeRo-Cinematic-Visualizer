import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from PIL import ImageChops
from project_io import DEFAULTS, load_project, save_project, validate_settings
from visualizer_core import Renderer, Settings


class ProjectTests(unittest.TestCase):
    def test_project_roundtrip_with_relative_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            audio=folder/'song.wav';audio.touch()
            values=dict(DEFAULTS,audio=str(audio),title='My mixed Case title',title_bold=True,
                        title_italic=True,title_uppercase=False,title_color='#abcdef',
                        title_x=30.0,spectrum_width=94.0,spectrum_y=80.0)
            path=folder/'scene.dero'
            save_project(path,values,2.5,9.25)
            raw=json.loads(path.read_text())
            self.assertEqual(raw['settings']['audio'],'song.wav')
            restored,selection=load_project(path)
            self.assertEqual(restored,values)
            self.assertEqual(selection,[2.5,9.25])
            save_project(path,DEFAULTS)
            self.assertEqual(load_project(path),(DEFAULTS,[0,None]))

    def test_invalid_project_data(self):
        for changes in ({'spectrum_width':101},{'title_x':float('nan')},{'fps':24},
                        {'title_color':'bad'},{'title_bold':'yes'},{'dust':3.2}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                validate_settings(dict(DEFAULTS,**changes))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'invalid.dero';path.write_text('{"version":999}')
            with self.assertRaises(ValueError):load_project(path)
            for start,end in [(4,2),(-1,2),(0,float('inf'))]:
                with self.assertRaises(ValueError):save_project(path,DEFAULTS,start,end)

    def test_title_and_spectrum_render_positions(self):
        base=Settings(width=640,height=360,title='',dust_count=0,bars=32)
        features=np.ones((1,32),np.float32)*.5
        image=Renderer(base,features).render(0)
        shifted=Renderer(Settings(width=640,height=360,title='',dust_count=0,bars=32,
                                 spectrum_x=.4,spectrum_y=.6,spectrum_width=.6),features).render(0)
        self.assertIsNotNone(ImageChops.difference(image,shifted).getbbox())
        title=Renderer(Settings(width=640,height=360,title='Mixed Case',dust_count=0,bars=32,
                               title_x=.3,title_y=.3,title_size=.08,title_color='#ff0000',
                               title_bold=True,title_italic=True,title_uppercase=False),features).render(0)
        bbox=ImageChops.difference(image,title).getbbox()
        self.assertIsNotNone(bbox)
        self.assertLess(bbox[3],180)
        red=np.asarray(title)
        self.assertTrue(np.any((red[:,:,0]>180)&(red[:,:,1]<50)))


if __name__=='__main__':unittest.main()
