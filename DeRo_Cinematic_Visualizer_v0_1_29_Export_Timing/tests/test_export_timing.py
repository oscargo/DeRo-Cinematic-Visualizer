import queue
import unittest
from unittest.mock import Mock,patch
from export_timing import ExportTimer,format_duration
from visualizer_app import Application


class ExportTimingTests(unittest.TestCase):
    def test_duration_rollovers(self):
        for seconds,expected in [(0,'00:00:00'),(59.9,'00:00:59'),(60,'00:01:00'),
                                 (3661,'01:01:01'),(360000,'100:00:00')]:
            self.assertEqual(format_duration(seconds),expected)

    def test_live_elapsed_frozen_total_and_restart(self):
        timer=ExportTimer()
        self.assertEqual(timer.text(),'Export time: —')
        with patch('export_timing.time.monotonic',return_value=100):timer.start()
        with patch('export_timing.time.monotonic',return_value=165):
            self.assertEqual(timer.text(),'Elapsed: 00:01:05')
        timer.stop(65.5)
        with patch('export_timing.time.monotonic',return_value=1000):
            self.assertEqual(timer.text(),'Total export time: 00:01:05')
            timer.start()
            self.assertEqual(timer.text(),'Elapsed: 00:00:00')

    def test_poll_ticks_without_progress_and_preserves_worker_total(self):
        app=Application.__new__(Application)
        app.root=Mock();app.q=queue.Queue();app.export_timer=ExportTimer();app.export_time=Mock()
        with patch('export_timing.time.monotonic',return_value=100):app.export_timer.start()
        with patch('export_timing.time.monotonic',return_value=107):app.poll()
        app.export_time.set.assert_called_with('Elapsed: 00:00:07')
        app.q.put(('export_timing',12.4))
        with patch('export_timing.time.monotonic',return_value=150):app.poll()
        app.export_time.set.assert_called_with('Total export time: 00:00:12')
        app.poll()
        app.export_time.set.assert_called_with('Total export time: 00:00:12')

    def test_encoder_label_tracks_actual_selection_and_fallback(self):
        app=Application.__new__(Application)
        app.root=Mock();app.q=queue.Queue();app.export_device=Mock()
        app.encoder_status=Mock();app.status=Mock()
        for message,expected in [
            ('NVIDIA NVENC (GPU encoding)','GPU — NVIDIA NVENC'),
            ('CPU fallback: driver failed','CPU (fallback)'),
            ('CPU (libx264)','CPU')]:
            app.q.put(('encoder',message));app.poll()
            app.export_device.set.assert_called_with('Encoding: '+expected+' | Rendering: CPU')
