import json
import shutil
import subprocess
import tempfile
import tkinter as tk
import unittest
import wave
from pathlib import Path
from unittest.mock import patch, Mock
from types import SimpleNamespace

import numpy as np
from export_video import export
from visualizer_app import Application
from visualizer_core import Renderer, Settings


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.app = Application.__new__(Application)
        interp = tk.Tcl()
        self.app.selection_start = tk.DoubleVar(interp, 1)
        self.app.selection_end = tk.DoubleVar(interp, 2)
        self.app.length = 3

    def test_bounds(self):
        self.assertEqual(self.app.selection_bounds(), (1, 2))
        for start, end in [(2, 1), (-1, 2), (0, 4), (1, 1), (0, float('inf'))]:
            self.app.selection_start.set(start)
            self.app.selection_end.set(end)
            with self.assertRaises(ValueError):
                self.app.selection_bounds()

    def test_timeline_click_seeks_and_starts_without_duplicate_animation(self):
        app=self.app
        app.position=tk.DoubleVar(value=0,master=app.selection_start._root)
        app.renderer=object();app.length=10;app.playing=False
        app.scrub=Mock()
        app.scrub.coords.side_effect=lambda value:(10+value*10,0)
        app.display_frame=Mock();app.animate=Mock()
        with patch('visualizer_app.time.monotonic',return_value=100):
            self.assertEqual(app.timeline_click(SimpleNamespace(x=60)),'break')
            self.assertEqual(app.position.get(),5)
            self.assertEqual(app.t0,95)
            self.assertTrue(app.playing)
            self.assertFalse(app.play_selection)
            app.timeline_click(SimpleNamespace(x=85))
            self.assertEqual(app.position.get(),7.5)
            app.animate.assert_called_once()
            app.timeline_click(SimpleNamespace(x=-10))
            self.assertEqual(app.position.get(),0)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
    def test_trimmed_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / 'source.wav'
            output = Path(tmp) / 'clip.mp4'
            sr = 22050
            t = np.arange(sr * 3) / sr
            # Different tones make an incorrect audio offset detectable.
            frequency = np.where(t < 1, 220, 880)
            samples = (np.sin(2*np.pi*frequency*t)*16000).astype('<i2')
            with wave.open(str(audio), 'wb') as wav:
                wav.setparams((1, 2, sr, 0, 'NONE', 'not compressed'))
                wav.writeframes(samples.tobytes())
            settings = Settings(width=160, height=90, fps=10, bars=32, dust_count=3)
            timestamps = []
            original = Renderer.render
            def render(renderer, seconds):
                timestamps.append(seconds)
                return original(renderer, seconds)
            progress = []
            with patch.object(Renderer, 'render', render):
                export(str(audio), str(output), settings, start_seconds=1, end_seconds=1.6,
                       progress=lambda i,n: progress.append((i,n)))
            self.assertAlmostEqual(timestamps[0], 1)
            self.assertTrue(all(1 <= value < 1.6 for value in timestamps))
            info = json.loads(subprocess.check_output([
                'ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(output)]))
            streams = {stream['codec_type']: stream for stream in info['streams']}
            self.assertEqual(int(streams['video']['nb_frames']), len(timestamps))
            self.assertAlmostEqual(float(info['format']['duration']), .6, delta=.12)
            self.assertIn('audio', streams)
            self.assertEqual(progress[-1], (len(timestamps), len(timestamps)))
            decoded = subprocess.check_output(['ffmpeg','-v','error','-i',str(output),
                '-vn','-ac','1','-ar',str(sr),'-f','f32le','pipe:1'])
            signal = np.frombuffer(decoded, dtype='<f4')
            peak = np.argmax(abs(np.fft.rfft(signal))) * sr / len(signal)
            self.assertAlmostEqual(peak, 880, delta=10)
            for start,end in [(2,1),(-1,1),(0,4)]:
                with self.assertRaises(ValueError):
                    export(str(audio), str(output), settings, start_seconds=start,end_seconds=end)
            export(str(audio), str(output), settings)
            info = json.loads(subprocess.check_output(['ffprobe','-v','error',
                '-show_format','-of','json',str(output)]))
            self.assertAlmostEqual(float(info['format']['duration']), 3, delta=.12)


if __name__ == '__main__':
    unittest.main()
