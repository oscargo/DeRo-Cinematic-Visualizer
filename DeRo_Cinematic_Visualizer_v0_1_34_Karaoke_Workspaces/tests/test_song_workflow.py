from pathlib import Path
import hashlib
import shutil
import tempfile
import tkinter as tk
import unittest
import wave
from unittest.mock import Mock,patch
from export_control import ExportControl,ExportCancelled
from project_io import DEFAULTS,save_project,load_project,validate_settings
from song_separation import separate_song,_run
from visualizer_app import Application


class SongSettingsTests(unittest.TestCase):
    def test_language_and_stems_roundtrip_with_relative_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);project=root/'song.dero'
            values=dict(DEFAULTS,song_language='Spanish / Español',audio=str(root/'mix.wav'),
                        instrumental=str(root/'instrumental.wav'),vocals=str(root/'vocals.wav'),audio_track='Vocals')
            save_project(project,values)
            loaded,_=load_project(project)
            self.assertEqual(loaded,values)
        self.assertEqual(validate_settings({})['song_language'],'Auto Detect')
        with self.assertRaises(ValueError):validate_settings(dict(DEFAULTS,audio_track='Unknown'))

    def test_confirmed_import_is_a_fresh_project_then_starts_separation(self):
        app=Application.__new__(Application);interp=tk.Tcl();app.project_vars={}
        for key,value in DEFAULTS.items():
            kind=tk.BooleanVar if isinstance(value,bool) else tk.IntVar if isinstance(value,int) else tk.DoubleVar if isinstance(value,float) else tk.StringVar
            app.project_vars[key]=kind(interp,value=value);setattr(app,key,app.project_vars[key])
        app.background.set('old.png');app.vocals.set('old vocals.wav');app.particle_speed.set(30)
        app.clear_media=Mock();app.song_workflow_status=Mock();app._remember_folder=Mock()
        app.update_project_title=Mock();app.show_inspector=Mock();app.start_separation=Mock()
        app.import_confirmed_song('new.mp3','New song','New artist')
        self.assertEqual((app.audio.get(),app.title.get(),app.artist.get()),('new.mp3','New song','New artist'))
        self.assertEqual(app.background.get(),'');self.assertEqual(app.vocals.get(),'')
        self.assertEqual(app.particle_speed.get(),DEFAULTS['particle_speed'])
        self.assertIsNone(app.project_path);self.assertIsNone(app.saved_project_state)
        app.show_inspector.assert_called_once_with('Separation');app.start_separation.assert_called_once()

    def test_selected_missing_stem_never_silently_uses_original_audio(self):
        app=Application.__new__(Application);app.audio_track=Mock(get=Mock(return_value='Vocals'))
        app.vocals=Mock(get=Mock(return_value=''));app.audio=Mock(get=Mock(return_value='original.mp3'))
        with self.assertRaises(ValueError):app.active_audio_path()


@unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg required')
class SeparationWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.audio=self.root/'Song.wav'
        self.write_source(2205)
        self.demucs_calls=0

    def write_source(self,frames):
        with wave.open(str(self.audio),'wb') as wav:
            wav.setparams((1,2,22050,0,'NONE','not compressed'));wav.writeframes(b'\0\0'*frames)

    def fake_demucs(self,command,control,emit):
        control.check()
        if '-m' in command and 'demucs' in command:
            self.demucs_calls+=1
            model=command[command.index('-n')+1];prepared=Path(command[-1]);output=Path(command[command.index('-o')+1])/model/prepared.stem
            output.mkdir(parents=True)
            with wave.open(str(prepared),'rb') as wav:
                self.assertEqual((wav.getnchannels(),wav.getframerate()),(2,44100))
            shutil.copy2(prepared,output/'vocals.wav');shutil.copy2(prepared,output/'no_vocals.wav')
        else:_run(command,control,emit)

    def run_separation(self,**kwargs):
        with patch('song_separation._run',side_effect=self.fake_demucs):
            return separate_song(str(self.audio),check_dependencies=False,**kwargs)

    def test_real_ffmpeg_preparation_staged_outputs_and_cache_reuse(self):
        original=hashlib.sha256(self.audio.read_bytes()).digest()
        instrumental,vocals=self.run_separation()
        self.assertTrue(Path(instrumental).is_file());self.assertTrue(Path(vocals).is_file())
        self.assertEqual(self.demucs_calls,1)
        self.assertEqual(self.run_separation(reuse_existing=True),(instrumental,vocals));self.assertEqual(self.demucs_calls,1)
        self.assertEqual(hashlib.sha256(self.audio.read_bytes()).digest(),original)
        self.assertFalse(list((self.root/'Karaoke Maker Stems').glob('.dero-separation-*')))

    def test_changed_source_preserves_previous_stems(self):
        first=self.run_separation();old=Path(first[0]).read_bytes()
        self.write_source(4410)
        second=self.run_separation()
        self.assertNotEqual(first,second);self.assertEqual(Path(first[0]).read_bytes(),old)

    def test_failed_demucs_does_not_publish_partial_stems(self):
        def fail(command,control,emit):
            if 'demucs' in command:raise RuntimeError('model unavailable')
            return _run(command,control,emit)
        with patch('song_separation._run',side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,'model unavailable'):
                separate_song(str(self.audio),check_dependencies=False)
        self.assertFalse((self.root/'Karaoke Maker Stems'/'htdemucs_ft'/'Song').exists())
        self.assertFalse(list((self.root/'Karaoke Maker Stems').glob('.dero-separation-*')))

    def test_cancellation_preserves_source_and_cleans_staging(self):
        control=ExportControl();original=self.audio.read_bytes()
        def emit(message):
            if message.startswith('Running '):control.cancel()
        with self.assertRaises(ExportCancelled):self.run_separation(control=control,emit=emit)
        self.assertEqual(self.audio.read_bytes(),original)
        self.assertFalse(list((self.root/'Karaoke Maker Stems').glob('.dero-separation-*')))

    def test_missing_dependency_is_actionable_without_creating_output(self):
        with patch('song_separation.importlib.util.find_spec',return_value=None):
            with self.assertRaisesRegex(RuntimeError,'same Python 3.12 environment as DeRo Sync'):
                separate_song(str(self.audio))
        self.assertFalse((self.root/'Karaoke Maker Stems').exists())
