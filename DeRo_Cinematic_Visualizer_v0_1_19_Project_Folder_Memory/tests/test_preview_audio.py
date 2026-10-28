from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import numpy as np
from preview_audio import PreviewAudio


class PreviewAudioTests(unittest.TestCase):
    def setUp(self):
        self.clock=Mock(return_value=10.)
        self.factory=Mock()
        self.player=PreviewAudio(self.factory,self.clock)
        self.player.rate=10
        self.data=np.column_stack((np.arange(10),-np.arange(10))).astype('float32')
        self.player.load(self.data)
        self.info=SimpleNamespace(outputBufferDacTime=5.1,currentTime=5.)

    def render(self,count):
        out=np.empty((count,2),np.float32)
        self.player.callback(out,count,self.info,None)
        return out

    def test_seek_stereo_stop_and_device_clock(self):
        self.player.play(.2,.7)
        np.testing.assert_array_equal(self.render(3),self.data[2:5])
        self.clock.return_value=10.2
        self.assertAlmostEqual(self.player.position(),.3)
        np.testing.assert_array_equal(self.render(4),np.concatenate((self.data[5:7],np.zeros((2,2)))))
        stream=self.player.stream
        self.player.stop()
        stream.stop.assert_called_once();stream.close.assert_called_once()
        self.assertIsNone(self.player.stream)

    def test_mute_advances_and_unmute_keeps_position(self):
        self.player.play(0,1)
        self.player.muted=True
        np.testing.assert_array_equal(self.render(3),np.zeros((3,2)))
        self.player.muted=False
        np.testing.assert_array_equal(self.render(2),self.data[3:5])

    def test_selection_loop_wraps_exactly(self):
        self.player.play(.4,.6,True,loop_start=.2)
        expected=self.data[[4,5,2,3,4,5,2]]
        np.testing.assert_array_equal(self.render(7),expected)

    def test_failed_device_closes_stream(self):
        self.factory.return_value.start.side_effect=RuntimeError('No device')
        with self.assertRaises(RuntimeError):self.player.play(0,1)
        self.assertIsNone(self.player.stream)
        self.factory.return_value.close.assert_called_once()
