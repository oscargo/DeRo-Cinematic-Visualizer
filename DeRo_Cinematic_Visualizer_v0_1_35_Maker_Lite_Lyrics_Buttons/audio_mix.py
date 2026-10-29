"""Deterministic, cached two-stem audio mix shared by preview and export."""
import hashlib,json,os,subprocess,tempfile
from pathlib import Path
from export_control import ExportControl

def mix_spec(instrumental,vocals,instrumental_gain=100,vocal_gain=20):
    sources=[str(Path(p).resolve()) for p in (instrumental,vocals)]
    gains=[float(instrumental_gain),float(vocal_gain)]
    if any(not 0<=g<=100 for g in gains):raise ValueError('Stem levels must be between 0 and 100%.')
    if not any(gains):raise ValueError('At least one stem must be audible.')
    identities=[]
    for path in sources:
        st=os.stat(path);identities.append([path,st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns])
    key=hashlib.sha256(json.dumps([identities,gains]).encode()).hexdigest()
    folder=Path(tempfile.gettempdir())/'dero-stem-mixes'
    return {'sources':sources,'gains':gains,'path':str(folder/(key+'.wav'))}

def prepare_mix(spec,control=None):
    control=control or ExportControl();destination=Path(spec['path'])
    if destination.is_file():return str(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.mix-',suffix='.wav',dir=destination.parent);os.close(fd)
    try:
        a,b=spec['gains']
        filters=f'[0:a]volume={a/100:.8f}[a];[1:a]volume={b/100:.8f}[b];[a][b]amix=inputs=2:normalize=0:duration=longest,alimiter=limit=0.98:level=0[m]'
        result=control.run(['ffmpeg','-v','error','-y','-i',spec['sources'][0],'-i',spec['sources'][1],'-filter_complex',filters,'-map','[m]','-ar','44100','-ac','2','-c:a','pcm_s16le',tmp],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        if result.returncode:raise RuntimeError('Stem mix failed: '+result.stderr.decode('utf-8','replace')[-1200:])
        control.check();os.replace(tmp,destination)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    return str(destination)
