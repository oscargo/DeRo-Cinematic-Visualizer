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
        app.audio.set(str(audio));app.vocals.set(str(audio));before=app.lyric_document.snapshot()
        with patch('karaoke_workspace.messagebox.showerror'),patch('karaoke_workspace.messagebox.askyesno',return_value=True),patch.object(app,'alignment_available',return_value=True):
            app.start_alignment();app.cancel_alignment();self.pump(lambda:app.lyric_control is None)
        self.assertEqual(app.lyric_document.snapshot(),before)
        with patch('karaoke_workspace.messagebox.askyesno',return_value=True),patch.object(app,'alignment_available',return_value=True):
            app.start_alignment();app.reset_karaoke()
        self.assertIsNone(app.lyric_control)
        self.assertEqual(app.lyric_document.events,[])
    def test_favorites_use_live_names_and_persist_changes(self):
        from lyric_sites import FavoriteSites
        app=self.app;app.artist.set('Earth, Wind & Fire');app.title.set('September')
        path=Path(self.folder.name)/'sites.json';store=FavoriteSites(path,Path(self.folder.name)/'missing.json')
        with patch('favorite_sites_ui.FavoriteSites',return_value=store):app.show_favorite_sites()
        window=app.favorite_sites_window;self.root.update()
        self.assertEqual(self.root.clipboard_get(),'Earth, Wind & Fire September')
        def descendants(widget):
            for child in widget.winfo_children():yield child;yield from descendants(child)
        from tkinter import ttk
        buttons={w.cget('text'):w for w in descendants(window) if isinstance(w,ttk.Button)}
        with patch('favorite_sites_ui.simpledialog.askstring',side_effect=['My site','https://example.com']):buttons['Add'].invoke()
        self.assertEqual(store.load()[-1]['name'],'My site');buttons['Move up'].invoke()
        self.assertEqual(store.load()[-2]['name'],'My site')
        with patch('favorite_sites_ui.messagebox.askyesno',return_value=True):buttons['Remove'].invoke()
        self.assertNotIn('My site',[s['name'] for s in store.load()])
        app.title.set('New title')
        listing=next(w for w in descendants(window) if isinstance(w,tk.Listbox));listing.selection_clear(0,'end');listing.selection_set(0)
        with patch('favorite_sites_ui.webbrowser.open',return_value=True) as browser:buttons['Search current song'].invoke()
        self.assertIn('Earth%2C+Wind+%26+Fire+New+title',browser.call_args.args[0])
    def test_alignment_requires_vocals_and_does_not_change_existing_lyrics(self):
        app=self.app;before=app.lyric_document.snapshot()
        with patch('karaoke_workspace.messagebox.showwarning') as warning:
            app.start_alignment();self.assertEqual(warning.call_args.args[0],'Isolated vocals required')
        self.assertEqual(app.lyric_document.snapshot(),before);self.assertIsNone(app.lyric_control)
    def test_direct_paste_alignment_success_and_inspector_export(self):
        import io,json
        from unittest.mock import Mock
        from lyric_model import LyricDocument
        app=self.app;app.reset_karaoke()
        raw='  Keep my exact words!\n¡Mi corazón!\nLast sung line\n'
        app.lyrics_editor.insert('1.0',raw)
        source=Path(self.folder.name)/'vocals.wav';source.write_bytes(b'fixture');app.vocals.set(str(source))
        prepared=LyricDocument();prepared.set_text(raw,12)
        statuses={str(i):'aligned' for i in range(3)}
        result=[prepared.events,prepared.words,'en',statuses,{}, {'total_lines':3}, {'recognized_segments':[{'text':'Fixture recognition'}]}]
        def launch(cmd,**kwargs):
            request=json.loads(Path(cmd[-2]).read_text())
            self.assertEqual(request['source'],str(source));self.assertEqual(request['lines'],[line.strip() for line in raw.splitlines() if line.strip()])
            Path(cmd[-1]).write_text(json.dumps(result),encoding='utf-8')
            return Mock(stdout=io.StringIO('Alignment device: CPU\n'),stderr=None,poll=Mock(return_value=0),wait=Mock(return_value=0))
        with patch.object(app,'alignment_available',return_value=True),patch('karaoke_workspace.subprocess.Popen',side_effect=launch),patch.object(app,'load_monitor'),patch.object(app,'show_alignment_quality') as quality:
            app.start_alignment();self.pump(lambda:app.lyric_control is None);quality.assert_called_once()
        self.assertEqual(app.lyric_document.text,raw);self.assertEqual(app.lyrics_editor.get('1.0','end-1c'),raw)
        self.assertEqual(str(app.lyrics_editor.cget('state')),'normal')
        self.assertTrue(app.inspector_pages['Word Sync'].winfo_ismapped())
        app.show_sync_inspector();self.root.update()
        window=next(w for w in self.root.winfo_children() if isinstance(w,tk.Toplevel) and w.title()=='Sync Inspector')
        def descendants(widget):
            for child in widget.winfo_children():yield child;yield from descendants(child)
        from tkinter import ttk
        export_button=next(w for w in descendants(window) if isinstance(w,ttk.Button) and w.cget('text')=='Export JSON...')
        output=Path(self.folder.name)/'inspector.json'
        with patch('karaoke_workspace.filedialog.asksaveasfilename',return_value=str(output)):export_button.invoke()
        self.assertEqual(json.loads(output.read_text())['inspector'],result[6]);window.destroy()
