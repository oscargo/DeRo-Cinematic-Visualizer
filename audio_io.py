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


def read_metadata(path, ffprobe='ffprobe'):
    """Read only title/artist tags; do not invent artist information."""
    import json
    try:
        proc=subprocess.run([ffprobe,'-v','error','-show_entries',
            'format_tags=title,artist:stream=codec_type:stream_tags=title,artist',
            '-of','json',path],capture_output=True,text=True,timeout=10)
        if proc.returncode:return {'title':'','artist':''}
        data=json.loads(proc.stdout)
        tags={}
        for stream in data.get('streams',[]):
            if stream.get('codec_type')=='audio':
                tags.update({k.lower():v for k,v in stream.get('tags',{}).items()})
                break
        tags.update({k.lower():v for k,v in data.get('format',{}).get('tags',{}).items()})
        return {key:str(tags.get(key,'')).strip() for key in ('title','artist')}
    except (OSError,ValueError,subprocess.TimeoutExpired):
        return {'title':'','artist':''}


def suggested_name(artist, song):
    """A Windows-safe filename stem shared by project, PNG, and MP4 dialogs."""
    import re
    parts=[part.strip() for part in (artist,song) if part.strip()]
    name=' - '.join(parts) or 'Untitled'
    name=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',name).strip().rstrip('. ')
    name=name[:180].rstrip('. ') or 'Untitled'
    if name.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}:
        name='_'+name
    return name
