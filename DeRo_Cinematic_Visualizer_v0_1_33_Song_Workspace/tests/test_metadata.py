import shutil
import subprocess
import tempfile
from pathlib import Path
import unittest
from audio_io import read_metadata, suggested_name
from project_io import DEFAULTS, save_project, load_project
from visualizer_core import Renderer, Settings
from PIL import ImageChops


class MetadataTests(unittest.TestCase):
    def test_safe_names(self):
        self.assertEqual(suggested_name('An Artist','A Song'),'An Artist - A Song')
        self.assertEqual(suggested_name('','Song'),'Song')
        self.assertEqual(suggested_name('',''),'Untitled')
        self.assertEqual(suggested_name('A/B','Song: One?'),'A_B - Song_ One_')
        self.assertEqual(suggested_name('','CON'),'_CON')

    def test_artist_project_and_render(self):
        values=dict(DEFAULTS,title='Song',artist='Artist',artist_font='Serif',artist_bold=True,
                    artist_color='#ff0000',artist_x=30.,artist_y=40.)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'Artist - Song.dero'
            save_project(path,values)
            self.assertEqual(load_project(path)[0],values)
        base=Renderer(Settings(width=640,height=360,title='',dust_count=0)).render(0)
        row=Renderer(Settings(width=640,height=360,title='',artist='Artist',artist_y=.4,
                              artist_size=.06,dust_count=0)).render(0)
        bbox=ImageChops.difference(base,row).getbbox()
        self.assertIsNotNone(bbox)
        self.assertLess(bbox[3],200)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg tools required')
    def test_real_tags_and_missing_tags(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'unrelated filename.mp3'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=duration=0.2',
                            '-metadata','title=Actual Song','-metadata','artist=Actual Artist',str(path)],check=True)
            self.assertEqual(read_metadata(str(path)),{'title':'Actual Song','artist':'Actual Artist'})
            plain=Path(tmp)/'plain.wav'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=duration=0.2',str(plain)],check=True)
            self.assertEqual(read_metadata(str(plain)),{'title':'','artist':''})
        self.assertEqual(read_metadata('missing.wav'),{'title':'','artist':''})

    def test_mutagen_has_priority_and_ffprobe_only_fills_missing_tags(self):
        from unittest.mock import Mock,patch
        import json
        with patch('mutagen.File',return_value={'title':['Local title'],'artist':['Local artist']}),patch('audio_io.subprocess.run') as probe:
            self.assertEqual(read_metadata('music.mp3'),{'title':'Local title','artist':'Local artist'})
            probe.assert_not_called()
        response=Mock(returncode=0,stdout=json.dumps({'format':{'tags':{'title':'Other title','artist':'Recovered artist'}}}))
        with patch('mutagen.File',return_value={'title':['Local title']}),patch('audio_io.subprocess.run',return_value=response):
            self.assertEqual(read_metadata('music.mp3'),{'title':'Local title','artist':'Recovered artist'})
