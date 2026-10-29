import io
import wave
import unittest
from unittest.mock import Mock,patch
import numpy as np
from notifications import completion_wave,completion_tone


class NotificationTests(unittest.TestCase):
    def test_chime_has_valid_pcm_and_no_clipping(self):
        with wave.open(io.BytesIO(completion_wave()),'rb') as wav:
            self.assertEqual(wav.getnchannels(),1)
            self.assertEqual(wav.getsampwidth(),2)
            self.assertAlmostEqual(wav.getnframes()/wav.getframerate(),.95,places=2)
            samples=np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2')
            self.assertGreater(float(np.max(np.abs(samples))),5000)
            self.assertLess(float(np.max(np.abs(samples))),32767)

    def test_windows_uses_generated_sound_not_system_alias(self):
        backend=Mock(SND_MEMORY=4,SND_NODEFAULT=2)
        errors=Mock()
        with patch('notifications.sys.platform','win32'),patch.dict('sys.modules',winsound=backend):
            thread=completion_tone(errors);thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        sound,flags=backend.PlaySound.call_args.args
        self.assertTrue(sound.startswith(b'RIFF'))
        self.assertEqual(flags,6)
        errors.assert_not_called()

    def test_unavailable_sound_is_reported(self):
        backend=Mock(SND_MEMORY=4,SND_NODEFAULT=2)
        backend.PlaySound.side_effect=RuntimeError('Output unavailable')
        errors=Mock()
        with patch('notifications.sys.platform','win32'),patch.dict('sys.modules',winsound=backend):
            completion_tone(errors).join(timeout=5)
        errors.assert_called_once_with('Output unavailable')
