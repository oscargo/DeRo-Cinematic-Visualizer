"""Nonblocking, best-effort completion sound; never changes export success."""
import sys
import numpy as np


def completion_tone():
    try:
        if sys.platform=='win32':
            import winsound
            winsound.PlaySound('SystemAsterisk',winsound.SND_ALIAS|winsound.SND_ASYNC|winsound.SND_NODEFAULT)
        else:
            import sounddevice
            rate=44100
            t=np.arange(round(.65*rate))/rate
            tone=np.zeros_like(t)
            for delay,hz in ((0,523.25),(.12,659.25),(.24,783.99)):
                local=np.maximum(0,t-delay)
                envelope=np.minimum(local/.025,1)*np.exp(-local*7)*(t>=delay)
                tone+=np.sin(2*np.pi*hz*local)*envelope*.07
            sounddevice.play(tone.astype('float32'),rate,blocking=False)
    except Exception:
        # Missing/muted audio hardware must never turn a saved export into an error.
        pass
