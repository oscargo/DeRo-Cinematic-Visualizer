from pathlib import Path
import tempfile
import unittest
import numpy as np
from project_io import DEFAULTS,save_project,load_project
from visualizer_core import Settings,Renderer


class ContinuousParticleTests(unittest.TestCase):
    def test_high_speed_stays_populated_for_all_directions(self):
        features=np.zeros((1200,32),np.float32)
        for direction in ('Out','Left','Right','Up','Down'):
            with self.subTest(direction=direction):
                common=dict(fps=10,bars=32,dust_count=48,particle_speed=30,particle_direction=direction)
                old=Renderer(Settings(**common,particle_continuous=False),features)
                live=Renderer(Settings(**common,particle_continuous=True),features)
                def count(renderer):
                    p=renderer.trajectories[-1]
                    return np.count_nonzero(np.all((p>=0)&(p<=1),axis=1)&(renderer.particle_fades[-1]>.1))
                self.assertEqual(count(old),0)
                self.assertGreater(count(live),30)
                self.assertTrue(np.all((live.particle_fades>=0)&(live.particle_fades<=1)))
                jumps=np.linalg.norm(np.diff(live.trajectories,axis=0),axis=-1)>.2
                self.assertTrue(jumps.any())
                # Position replacement must be invisible on its birth frame.
                self.assertTrue(np.all(live.particle_fades[1:][jumps]==0))

    def test_seek_determinism_and_saved_toggle(self):
        settings=Settings(width=320,height=180,fps=10,bars=32,dust_count=12,particle_speed=30)
        features=np.zeros((600,32),np.float32)
        one=Renderer(settings,features);two=Renderer(settings,features)
        np.testing.assert_array_equal(one.trajectories,two.trajectories)
        np.testing.assert_array_equal(one.particle_fades,two.particle_fades)
        expected=one.render(50).tobytes();one.render(3)
        self.assertEqual(one.render(50).tobytes(),expected)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'scene.dero'
            for enabled in (False,True):
                save_project(path,dict(DEFAULTS,particle_continuous=enabled))
                self.assertEqual(load_project(path)[0]['particle_continuous'],enabled)
