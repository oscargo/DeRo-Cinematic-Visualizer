"""DeRo Sync-style Demucs workflow; preserve source audio and existing stems."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from export_control import ExportControl

MODELS={'High quality — HTDemucs Fine-Tuned':'htdemucs_ft','Standard — HTDemucs':'htdemucs'}


def _run(command,control,emit):
    # Independent handles avoid changing the child writer's file offset.
    with tempfile.TemporaryDirectory(prefix='dero-process-log-') as folder:
        path=Path(folder)/'process.log'
        with open(path,'wb') as writer,open(path,'rb') as reader:
            proc=subprocess.Popen(command,stdout=writer,stderr=subprocess.STDOUT,
                                  creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            with control.process(proc):
                while proc.poll() is None:
                    control.check()
                    chunk=reader.read(65536)
                    if chunk and emit:emit(chunk.decode('utf-8','replace')[-4000:])
                    control.event.wait(.15)
                control.check()
                chunk=reader.read()
                if chunk and emit:emit(chunk.decode('utf-8','replace')[-4000:])
                if proc.returncode:
                    reader.seek(0,os.SEEK_END);size=reader.tell();reader.seek(max(0,size-2000))
                    raise RuntimeError(reader.read().decode('utf-8','replace') or f'Process exited with code {proc.returncode}')


def separate_song(audio_path,model='htdemucs_ft',ffmpeg='ffmpeg',control=None,emit=None,
                  python=sys.executable,check_dependencies=True,reuse_existing=False):
    control=control if control is not None else ExportControl()
    control.check()
    source=Path(audio_path).resolve()
    if not source.is_file():raise ValueError('Choose an existing music file first.')
    if model not in MODELS.values():raise ValueError('Choose a supported Demucs model.')
    if check_dependencies and importlib.util.find_spec('demucs') is None:
        raise RuntimeError('Demucs is not installed in this Python environment. Use the same Python 3.12 environment as DeRo Sync, or install requirements-separation.txt. Existing CUDA/PyTorch installations are not changed automatically.')
    stat=source.stat()
    identity={'path':str(source),'size':stat.st_size,'mtime_ns':stat.st_mtime_ns,'ctime_ns':stat.st_ctime_ns,'model':model}
    digest=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:10]
    root=source.parent/'Karaoke Maker Stems'
    model_root=root/model;model_root.mkdir(parents=True,exist_ok=True)
    target=model_root/source.stem
    manifest=target/'dero_source.json'
    if reuse_existing and manifest.is_file():
        try:
            if json.loads(manifest.read_text())==identity and all((target/name).is_file() and (target/name).stat().st_size>44 for name in ('vocals.wav','no_vocals.wav')):
                if emit:emit('Matching stems already exist; reusing them.')
                control.commit(lambda:None)
                return str(target/'no_vocals.wav'),str(target/'vocals.wav')
        except (OSError,ValueError):pass
    if target.exists():target=model_root/(source.stem[:120]+'_'+digest)
    if target.exists():
        # Never overwrite another run, even if its manifest is incomplete.
        index=2;base=target
        while target.exists():target=base.with_name(base.name+'_'+str(index));index+=1
    with tempfile.TemporaryDirectory(prefix='.dero-separation-',dir=root) as temporary:
        temporary=Path(temporary);wav=temporary/(source.stem+'.wav');output=temporary/'stems'
        if emit:emit('Preparing stereo 44.1 kHz WAV input. The original audio is unchanged.')
        _run([ffmpeg,'-hide_banner','-nostdin','-y','-loglevel','error','-i',str(source),
              '-map','0:a:0','-vn','-ac','2','-ar','44100','-c:a','pcm_s16le',str(wav)],control,emit)
        if not wav.is_file() or wav.stat().st_size<44:raise RuntimeError('FFmpeg did not produce valid processing audio.')
        if emit:emit('Running '+model+'. Demucs selects CUDA when it is available.')
        _run([python,'-m','demucs','-n',model,'--two-stems','vocals','-o',str(output),str(wav)],control,emit)
        stems=output/model/source.stem
        if emit:emit('Validating vocal and instrumental outputs...')
        for name in ('no_vocals.wav','vocals.wav'):
            path=stems/name
            if not path.is_file() or path.stat().st_size<44:raise RuntimeError('Demucs did not produce both usable stems.')
            _run([ffmpeg,'-v','error','-i',str(path),'-t','0.02','-f','null','-'],control,None)
        control.check()
        (stems/'dero_source.json').write_text(json.dumps(identity,indent=2),encoding='utf-8')
        control.commit(lambda:os.replace(stems,target))
    if emit:emit('Separation complete. Instrumental and vocal tracks are ready.')
    return str(target/'no_vocals.wav'),str(target/'vocals.wav')
