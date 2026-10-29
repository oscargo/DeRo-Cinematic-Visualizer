"""A generated completion chime independent of Windows notification sound schemes."""
import io
import sys
import threading
import wave
import numpy as np


def completion_samples():
    rate=44100
    t=np.arange(round(.95*rate))/rate
    tone=np.zeros_like(t)
    for delay,hz in ((0,523.25),(.15,659.25),(.30,783.99)):
        local=np.maximum(0,t-delay)
        envelope=np.minimum(local/.02,1)*np.exp(-local*5)*(t>=delay)
        tone+=np.sin(2*np.pi*hz*local)*envelope*.19
    tone*=np.minimum((.95-t)/.05,1).clip(0,1)
    return tone.astype('float32'),rate


def completion_wave():
    samples,rate=completion_samples()
    buffer=io.BytesIO()
    with wave.open(buffer,'wb') as wav:
        wav.setparams((1,2,rate,0,'NONE','not compressed'))
        wav.writeframes(np.round(samples*32767).astype('<i2').tobytes())
    return buffer.getvalue()


def completion_tone(on_error=None):
    def play():
        try:
            if sys.platform=='win32':
                import winsound
                # Synchronous memory playback runs on this worker, never on Tk.
                # SND_MEMORY and SND_ASYNC cannot be used together on Windows.
                winsound.PlaySound(completion_wave(),winsound.SND_MEMORY|winsound.SND_NODEFAULT)
            else:
                import sounddevice
                samples,rate=completion_samples()
                sounddevice.play(samples,rate,blocking=False)
        except Exception as exc:
            if on_error:on_error(str(exc))
    thread=threading.Thread(target=play,daemon=True)
    thread.start()
    return thread
