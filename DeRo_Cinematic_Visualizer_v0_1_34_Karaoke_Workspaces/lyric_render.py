"""One cinematic renderer plus the same libass overlay for previews and export."""
from contextlib import contextmanager
from dataclasses import replace
from io import BytesIO
import os
from pathlib import Path
import subprocess
import tempfile
from PIL import Image
from export_control import ExportControl
from lyric_model import LyricDocument
from lyric_ass import ass_file

class IdentityRenderer:
    def __init__(self,renderer,document):
        self.renderer=renderer;self.document=document
    def render(self,seconds):
        renderer=self.renderer
        if self.document.identity_visible(seconds):return renderer.render(seconds)
        settings=renderer.s
        try:
            renderer.s=replace(settings,title='',artist='')
            return renderer.render(seconds)
        finally:renderer.s=settings

@contextmanager
def lyric_overlay(document,settings,ffmpeg='ffmpeg',control=None):
    doc=LyricDocument(document)
    if not doc.style['enabled'] or not doc.events:
        yield None;return
    control=control or ExportControl()
    result=control.run([ffmpeg,'-hide_banner','-filters'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
    if result.returncode or not any(line.split()[1:2]==[b'ass'] for line in result.stdout.splitlines()):
        raise RuntimeError('This FFmpeg build needs the libass ASS filter to render lyrics. Install a full FFmpeg build.')
    with tempfile.TemporaryDirectory(prefix='dero-lyrics-') as folder:
        ass_file(doc.ass_project(),Path(folder)/'lyrics.ass',settings.width,settings.height)
        yield folder

def ass_filter(seconds):
    # Raw cinematic frames start at zero; lyric timestamps use absolute song time.
    return f'setpts=PTS+{float(seconds):.6f}/TB,ass=lyrics.ass,setpts=PTS-STARTPTS'

def exact_frame(renderer,seconds,document,ffmpeg='ffmpeg',control=None):
    control=control or ExportControl();doc=LyricDocument(document)
    frame=IdentityRenderer(renderer,doc).render(seconds).convert('RGB')
    with lyric_overlay(doc.snapshot(),renderer.s,ffmpeg,control) as folder:
        if folder is None:return frame
        result=control.run([ffmpeg,'-hide_banner','-loglevel','error','-filter_threads','1',
            '-f','rawvideo','-pix_fmt','rgb24','-s',f'{frame.width}x{frame.height}','-r',str(renderer.s.fps),
            '-i','pipe:0','-vf',ass_filter(seconds),'-frames:v','1','-f','image2pipe','-vcodec','png','pipe:1'],
            input=frame.tobytes(),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=folder,timeout=60)
        if result.returncode:raise RuntimeError(result.stderr.decode('utf-8','replace')[-2000:])
        return Image.open(BytesIO(result.stdout)).convert('RGB')
