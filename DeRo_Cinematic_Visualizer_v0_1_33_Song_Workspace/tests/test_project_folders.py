from pathlib import Path
import tempfile
from unittest.mock import Mock,patch
import unittest
from visualizer_app import Application
from project_io import DEFAULTS,save_project


class FolderMemoryTests(unittest.TestCase):
    def test_project_folder_survives_restart_and_cancel(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'Projects';folder.mkdir()
            prefs=Path(tmp)/'config'/'folders.json'
            with patch.object(Application,'_preferences_file',return_value=str(prefs)):
                first=Application.__new__(Application);first.folder_preferences={}
                first._remember_folder('project',str(folder/'song.dero'))
                first._remember_folder('music',str(Path(tmp)/'music.wav'))
                second=Application.__new__(Application)
                second.folder_preferences=second._load_folder_preferences()
                self.assertEqual(second.folder_preferences['project'],str(folder))
                self.assertEqual(second.folder_preferences['music'],tmp)
                second.project_path=None;second.confirm_replace=Mock(return_value=True)
                with patch('visualizer_app.filedialog.askopenfilename',return_value='') as dialog:
                    second.open_project()
                    self.assertEqual(dialog.call_args.kwargs['initialdir'],str(folder))
                self.assertEqual(second._load_folder_preferences()['project'],str(folder))
                folder.rmdir()
                self.assertTrue(Path(second._browse_initial_folder('project','')).is_dir())

    def test_successful_open_and_save_update_project_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefs=Path(tmp)/'folders.json'
            project=Path(tmp)/'scene.dero';save_project(project,DEFAULTS)
            app=Application.__new__(Application);app.folder_preferences={};app.project_path=None
            app.confirm_replace=Mock(return_value=True);app.clear_media=Mock()
            app.project_vars={key:Mock() for key in DEFAULTS}
            app.selection_start=Mock();app.selection_end=Mock();app.status=Mock();app.song_workflow_status=Mock()
            app.project_state=Mock(return_value=(DEFAULTS,[0,None]));app.update_project_title=Mock()
            with patch.object(Application,'_preferences_file',return_value=str(prefs)):
                with patch('visualizer_app.filedialog.askopenfilename',return_value=str(project)):
                    app.open_project()
                self.assertEqual(app._load_folder_preferences()['project'],tmp)
                destination=Path(tmp)/'Other';destination.mkdir()
                app.busy=False;app.filename_stem=Mock(return_value='Artist - Song')
                with patch('visualizer_app.filedialog.asksaveasfilename',return_value=str(destination/'song.dero')) as dialog:
                    self.assertTrue(app.save_project_file(True))
                    self.assertEqual(dialog.call_args.kwargs['initialdir'],tmp)
                self.assertEqual(app._load_folder_preferences()['project'],str(destination))
