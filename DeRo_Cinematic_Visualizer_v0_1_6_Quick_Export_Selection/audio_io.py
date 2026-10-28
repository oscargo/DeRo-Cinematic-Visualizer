"""Audio decode through FFmpeg (MP3/WAV/FLAC/M4A etc.)."""
import subprocess
import numpy as np

def load_audio(path, sample_rate=22050, ffmpeg='ffmpeg'):
    proc=subprocess.run([ffmpeg,'-v','error','-i',path,'-vn','-ac','1','-ar',str(sample_rate),'-f','f32le','pipe:1'],capture_output=True)
    if proc.returncode:
        raise RuntimeError(proc.stderr.decode('utf-8','replace')[-1600:])
    samples=np.frombuffer(proc.stdout,dtype='<f4').copy()
    if samples.size==0:
        raise ValueError('No audio samples decoded')
    return samples,sample_rate
