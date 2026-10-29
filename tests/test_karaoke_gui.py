"""Desktop integration checks; run with DISPLAY set to a working X server."""
import os,time,tempfile,subprocess,tkinter as tk,unittest
from pathlib import Path
from unittest.mock import patch
from visualizer_app import Application

@unittest.skipUnless(os.environ.get('DISPLAY'),'Desktop display required')
class KaraokeDesktopTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.prefs=patch.object(Application,'_preferences_file',return_value=str(Path(self.folder.name)/'prefs.json'));self.prefs.start()
        self.root=tk.Tk();self.app=Application(self.root);self.root.geometry('1040x820');self.root.update()
        self.app.length=12
        self.app.lyrics_editor.insert('1.0','Never change these words\nWe sing every line\nKeep the lyrics exact')
        self.app.apply_lyrics();self.root.update()
    def tearDown(self):
        self.app.destroy_application();self.prefs.stop();self.folder.cleanup()
    def pump(self,condition,timeout=10):
        deadline=time.monotonic()+timeout
        while not condition() and time.monotonic()<deadline:self.root.update();time.sleep(.02)
        self.assertTrue(condition())
    def test_tabs_word_edit_undo_redo_and_save_load(self):
        app=self.app
        for name in ('Audio','Separation','Lyrics','Word Sync','Video Designer','Output'):
            app.show_inspector(name);self.root.update();self.assertTrue(app.inspector_pages[name].winfo_ismapped())
        app.word_start.set('.1');app.word_end.set('.8');app.apply_word_times();self.root.update()
        self.assertEqual(app.lyric_document.words['0'][0][:2],[.1,.8])
        self.assertIn('timing items need review',app.lyric_message.get())
        app.undo_lyrics();self.root.update();self.assertEqual(app.lyric_document.words['0'][0][0],0)
        app.redo_lyrics();self.root.update();self.assertEqual(app.lyric_document.words['0'][0][0],.1)
        app.project_path=str(Path(self.folder.name)/'scene.dero');self.assertTrue(app.save_project_file())
        before=app.lyric_document.snapshot()
        with patch('visualizer_app.filedialog.askopenfilename',return_value=app.project_path):app.open_project()
        self.root.update();self.assertEqual(app.lyric_document.snapshot(),before)
    def test_canceled_alignment_preserves_document_and_reset_accepts_new_work(self):
        app=self.app;audio=Path(self.folder.name)/'input.wav'
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=duration=1',str(audio)],check=True)
        app.audio.set(str(audio));before=app.lyric_document.snapshot()
        with patch('karaoke_workspace.messagebox.showerror'):
            app.start_alignment();app.cancel_alignment();self.pump(lambda:app.lyric_control is None)
        self.assertEqual(app.lyric_document.snapshot(),before)
        app.start_alignment();app.reset_karaoke();self.assertIsNone(app.lyric_control)
        self.assertEqual(app.lyric_document.events,[])
