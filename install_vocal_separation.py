"""Install Demucs while pinning the user's existing PyTorch/CUDA packages."""
import argparse
import importlib.metadata
from pathlib import Path
import subprocess
import sys
import tempfile


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true',help='Check prerequisites without installing anything')
    parser.add_argument('--alignment',action='store_true',help='Install WhisperX while preserving PyTorch')
    args=parser.parse_args(argv)
    try:
        import torch
        import torchaudio
        versions={name:importlib.metadata.version(name) for name in ('torch','torchaudio')}
    except (ImportError,OSError,RuntimeError,importlib.metadata.PackageNotFoundError) as exc:
        print('Use the same working Python 3.12 environment as DeRo Sync.')
        print('A compatible PyTorch and torchaudio installation is required first: '+str(exc))
        print('See https://pytorch.org/get-started/locally/')
        return 1
    for name,version in versions.items():print(name+': '+version)
    print('CUDA available: '+str(torch.cuda.is_available()))
    if args.check:return 0
    requirements=Path(__file__).resolve().with_name('requirements-alignment.txt' if args.alignment else 'requirements-separation.txt')
    if not requirements.is_file():print(requirements.name+' is missing. Extract the complete app ZIP.');return 1
    with tempfile.TemporaryDirectory(prefix='dero-separation-install-') as folder:
        constraints=Path(folder)/'preserve-torch.txt'
        constraints.write_text(''.join(name+'=='+version+'\n' for name,version in versions.items()),encoding='utf-8')
        result=subprocess.run([sys.executable,'-m','pip','install','-r',str(requirements),'-c',str(constraints)])
    if result.returncode:
        print('Installation failed. Existing torch/torchaudio versions were pinned; do not replace your working CUDA build to bypass a conflict.')
        return result.returncode
    if args.alignment:return subprocess.run([sys.executable,'-c','import whisperx; print("WhisperX import OK")']).returncode
    return subprocess.run([sys.executable,'-m','demucs','--help']).returncode


if __name__=='__main__':raise SystemExit(main())
