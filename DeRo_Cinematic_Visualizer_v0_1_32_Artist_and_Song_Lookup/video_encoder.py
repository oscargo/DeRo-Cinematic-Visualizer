"""Select NVIDIA encoding using a real encode probe, with CPU fallback."""
import subprocess

ENCODER_CHOICES=('Auto (GPU if available)','NVIDIA NVENC','CPU (compatible)')
CPU_OPTIONS=['-c:v','libx264','-preset','veryfast','-crf','20']
NVENC_OPTIONS=['-c:v','h264_nvenc','-preset','p4','-tune','hq',
               '-rc','vbr','-cq','20','-b:v','0']


def select_encoder(settings,ffmpeg='ffmpeg',report=None,cancel=None):
    if cancel is not None:cancel.check()
    mode=settings.export_encoder
    if mode not in ENCODER_CHOICES:raise ValueError('Unsupported export encoder: '+str(mode))
    if mode==ENCODER_CHOICES[2]:
        if report:report('CPU (libx264)')
        return 'libx264',CPU_OPTIONS
    # Presence in ffmpeg -encoders alone does not prove a usable GPU/driver.
    cmd=[ffmpeg,'-hide_banner','-loglevel','error','-nostdin','-f','lavfi',
         '-i',f'color=c=black:s={settings.width}x{settings.height}:r={settings.fps}',
         '-frames:v','1','-an',*NVENC_OPTIONS,'-pix_fmt','yuv420p','-f','null','-']
    try:
        result=(cancel.run(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=20) if cancel is not None else
                subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=20,check=False))
        available=result.returncode==0
        reason=result.stderr.decode('utf-8','replace').strip().splitlines()
        reason=reason[0][:240] if reason else ''
    except subprocess.TimeoutExpired:
        available=False;reason='GPU test timed out'
    if available:
        if report:report('NVIDIA NVENC (GPU encoding)')
        return 'h264_nvenc',NVENC_OPTIONS
    if report:report('CPU fallback: NVIDIA NVENC unavailable. '+(reason or 'GPU test failed'))
    return 'libx264',CPU_OPTIONS
