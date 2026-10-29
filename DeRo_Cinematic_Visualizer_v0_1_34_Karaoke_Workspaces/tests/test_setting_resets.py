import tkinter as tk
import unittest
from unittest.mock import Mock,patch
from visualizer_app import Application
from project_io import DEFAULTS


class SettingResetTests(unittest.TestCase):
    def setUp(self):
        interp=tk.Tcl()
        app=self.app=Application.__new__(Application)
        app.project_vars={}
        for key,value in DEFAULTS.items():
            kind=tk.BooleanVar if isinstance(value,bool) else tk.IntVar if isinstance(value,int) else tk.DoubleVar if isinstance(value,float) else tk.StringVar
            app.project_vars[key]=kind(interp,value=value)
            setattr(app,key,app.project_vars[key])
        app.reset_text_defaults={'title':'Original Song','artist':'Original Artist'}
        app.schedule_layout_preview=Mock();app.toggle_sound=Mock();app.status=Mock();app.root=None

    def test_individual_resets_and_linked_frequency_bounds(self):
        a=self.app;a.particle_speed.set(30);a.dust.set(700)
        a.reset_setting('particle_speed')
        self.assertEqual(a.particle_speed.get(),DEFAULTS['particle_speed'])
        self.assertEqual(a.dust.get(),700)
        a.title.set('Edited');a.reset_setting('title')
        self.assertEqual(a.title.get(),'Original Song')
        a.frequency_min.set(15000);a.frequency_max.set(20000)
        a.reset_setting('frequency_max')
        self.assertEqual((a.frequency_min.get(),a.frequency_max.get()),(50,10584))

    def test_panel_reset_keeps_other_panels_and_files(self):
        a=self.app;a.audio.set('music.wav');a.overlay_path.set('logo.png')
        a.particle_speed.set(30);a.spectrum_gain.set(2)
        a.reset_panel('Elements')
        self.assertEqual(a.particle_speed.get(),DEFAULTS['particle_speed'])
        self.assertEqual(a.spectrum_gain.get(),2)
        self.assertEqual(a.audio.get(),'music.wav')
        self.assertEqual(a.overlay_path.get(),'logo.png')

    def test_reset_all_cancel_and_preserve_identifying_content(self):
        a=self.app;a.audio.set('song.wav');a.title.set('Song');a.artist.set('Artist');a.dust.set(500)
        with patch('visualizer_app.messagebox.askyesno',return_value=False):a.reset_all_settings()
        self.assertEqual(a.dust.get(),500)
        with patch('visualizer_app.messagebox.askyesno',return_value=True):a.reset_all_settings()
        self.assertEqual(a.dust.get(),130)
        self.assertEqual((a.audio.get(),a.title.get(),a.artist.get()),('song.wav','Song','Artist'))
