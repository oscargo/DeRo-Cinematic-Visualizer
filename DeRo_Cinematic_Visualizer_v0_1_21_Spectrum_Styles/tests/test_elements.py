from pathlib import Path
import tempfile
import unittest
import numpy as np
from PIL import Image,ImageChops
from project_io import DEFAULTS,save_project,load_project
from visualizer_core import Renderer,Settings


class ElementsTests(unittest.TestCase):
    def test_image_and_project_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            image=Path(tmp)/'logo.png'
            Image.new('RGBA',(60,40),(255,0,0,255)).save(image)
            project=Path(tmp)/'scene.dero'
            settings=dict(DEFAULTS,overlay_path=str(image),overlay_enabled=True,overlay_opacity=50.)
            save_project(project,settings)
            self.assertEqual(load_project(project)[0],settings)
            s=Settings(width=200,height=200,title='',dust_count=0,overlay_path=str(image),overlay_enabled=True,
                       overlay_size=.4,overlay_shape='Circle',overlay_opacity=.5,overlay_y=.5)
            renderer=Renderer(s)
            actual=renderer.render(0)
            baseline=Renderer(Settings(width=200,height=200,title='',dust_count=0)).render(0)
            self.assertGreater(actual.getpixel((100,100))[0],baseline.getpixel((100,100))[0])
            self.assertEqual(actual.getpixel((61,61)),baseline.getpixel((61,61)))
            self.assertIsNotNone(ImageChops.difference(actual,baseline).getbbox())
            s.overlay_enabled=False
            self.assertIsNone(ImageChops.difference(renderer.render(0),baseline).getbbox())

    def test_particle_direction_and_visibility(self):
        features=np.ones((60,32),np.float32)*.5
        for direction,axis,sign in [('Right',0,1),('Left',0,-1),('Up',1,-1),('Down',1,1)]:
            renderer=Renderer(Settings(width=160,height=90,bars=32,dust_count=10,
                particle_direction=direction),features)
            movement=renderer.trajectories[-1,:,axis]-renderer.trajectories[0,:,axis]
            self.assertTrue(np.all(movement*sign>0),direction)
        off=Renderer(Settings(width=160,height=90,title='',dust_count=10,particles_enabled=False))
        empty=Renderer(Settings(width=160,height=90,title='',dust_count=0))
        self.assertIsNone(ImageChops.difference(off.render(0),empty.render(0)).getbbox())
