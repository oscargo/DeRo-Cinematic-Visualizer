import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
from dataclasses import replace
from lyric_model import LyricDocument
from lyric_render import exact_frame,IdentityRenderer
from lyric_ass import ass_file
from project_io import DEFAULTS,save_project,load_project,load_project_full
from export_video import export
from visualizer_core import Settings,Renderer,audio_features
from audio_io import load_audio
from audio_mix import mix_spec,prepare_mix
from export_control import ExportControl,ExportCancelled

class LyricModelTests(unittest.TestCase):
    def document(self):
        doc=LyricDocument();doc.set_text('Don’t change my words!\n¡Mi corazón!',10)
        return doc
    def test_exact_text_and_timing_roundtrip(self):
        doc=self.document();doc.set_word(0,0,.4,1.1)
        self.assertEqual(doc.events[0][2],'Don’t change my words!')
        self.assertEqual(doc.words['1'][-1][2],'corazón!')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'song.dero';save_project(path,DEFAULTS,lyrics=doc.snapshot())
            values,selection,restored=load_project_full(path)
            self.assertEqual(restored.snapshot(),doc.snapshot());self.assertEqual(values,DEFAULTS)
            self.assertEqual(load_project(path)[1],selection)
    def test_old_projects_open_without_lyrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'old.dero';save_project(path,DEFAULTS)
            self.assertEqual(load_project_full(path)[2].events,[])
    def test_tampered_text_and_malformed_words_rejected(self):
        for malformed in ([[]],[[0,1,'invented']]):
            data=self.document().snapshot();data['word_timings']['0']=malformed
            with self.assertRaises(ValueError):LyricDocument(data)
        data=self.document().snapshot();data['word_timings']['01']=data['word_timings']['1']
        with self.assertRaises(ValueError):LyricDocument(data)
    def test_failed_alignment_does_not_replace_existing_data(self):
        doc=self.document();before=doc.snapshot()
        with self.assertRaises(ValueError):doc.apply_alignment(([[0,1,'wrong']],{},'en',{}, {},{},{}))
        self.assertEqual(doc.snapshot(),before)
    def test_snapshots_are_independent_and_negative_shift_rejected(self):
        doc=self.document();snapshot=doc.snapshot();doc.style['enabled']=False
        self.assertTrue(snapshot['style']['enabled'])
        with self.assertRaises(ValueError):doc.shift(-1)
    def test_ass_layouts_include_original_words_and_progressive_tags(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc=self.document()
            for mode in ('single','preview','alternating','classic_flow'):
                doc.style['lyric_display_mode']=mode
                path=Path(tmp)/'lyrics.ass';ass_file(doc.ass_project(),path)
                text=path.read_text(encoding='utf-8-sig');self.assertIn('corazón!',text);self.assertIn('\\kf',text)
    def test_sync_saved_project_import_preserves_manual_word_times(self):
        doc=self.document();doc.set_word(0,0,.1,.8)
        sync=dict(doc.snapshot(),format='KaraokeStudioProject',version=2,song='Song',artist='Artist',audio='mix.wav',reviewed_lines={'1':True},lyric_display_mode='alternating',audio_choice=1)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'sync.json';path.write_text(json.dumps(sync),encoding='utf-8')
            values,_,loaded=load_project_full(path)
            self.assertEqual(loaded.words,doc.words);self.assertEqual(loaded.text,doc.text)
            self.assertEqual(loaded.style['lyric_display_mode'],'alternating')
            self.assertEqual(loaded.data['alignment_status']['1'],'reviewed')
            self.assertEqual(values['audio_track'],'Stem mix');self.assertEqual(values['title'],'Song')
    def test_identity_hidden_only_during_lyric_section(self):
        doc=self.document();doc.shift(2)
        self.assertTrue(doc.identity_visible(1));self.assertFalse(doc.identity_visible(3))
        doc.style['show_identity']=True;self.assertTrue(doc.identity_visible(3))

@unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg required')
class LyricPipelineTests(unittest.TestCase):
    def test_exact_frame_and_clipped_export_use_absolute_lyric_times(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'song.wav'
            subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=frequency=440:duration=4',str(source)],check=True)
            settings=Settings(width=320,height=180,fps=30,bars=16,dust_count=0,particles_enabled=False,title='',artist='',export_encoder='Auto')
            # Use the official CPU choice rather than a duplicated display string.
            from video_encoder import ENCODER_CHOICES
            settings=replace(settings,export_encoder=ENCODER_CHOICES[-1])
            samples,sr=load_audio(str(source));features=audio_features(samples,sr,settings.fps,settings.bars)
            doc=LyricDocument();doc.set_text('Exact lyric',4);doc.set_line_bounds(0,2,3.6)
            doc.style.update(lyric_font_size=24,opening_progress_enabled=False,lyric_lead_seconds=0)
            renderer=Renderer(settings,features)
            before=np.array(exact_frame(renderer,1,doc.snapshot()));during=np.array(exact_frame(renderer,2.5,doc.snapshot()))
            self.assertGreater(np.abs(during.astype(float)-np.array(renderer.render(2.5)).astype(float)).sum(),1000)
            self.assertTrue(np.array_equal(before,np.array(renderer.render(1))))
            output=root/'clip.mp4';export(str(source),str(output),settings,start_seconds=2.5,end_seconds=2.7,lyric_document=doc.snapshot())
            raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(output),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'])
            decoded=np.frombuffer(raw,np.uint8).reshape(180,320,3)
            # Clipped first frame must contain the lyric displayed at 2.5s, not 0s.
            region=(slice(60,120),slice(35,285))
            expected=during[region].astype(float);actual=decoded[region].astype(float)
            self.assertLess(np.abs(expected-actual).mean(),10)
    def test_stem_mix_cache_invalidates_changed_sources_and_keeps_gains(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'a.wav'
            subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=duration=0.2',str(source)],check=True)
            a=mix_spec(source,source,100,20);b=mix_spec(source,source,100,30)
            self.assertNotEqual(a['path'],b['path']);self.assertTrue(Path(prepare_mix(a)).is_file())
            source.touch();self.assertNotEqual(a['path'],mix_spec(source,source,100,20)['path'])
            with self.assertRaises(ValueError):mix_spec(source,source,0,0)
    def test_control_input_and_cancellation(self):
        import sys
        control=ExportControl();result=control.run([sys.executable,'-c','import sys;sys.stdout.buffer.write(sys.stdin.buffer.read())'],input=b'lyrics',stdin=subprocess.PIPE,stdout=subprocess.PIPE)
        self.assertEqual(result.stdout,b'lyrics');control.cancel()
        with self.assertRaises(ExportCancelled):control.check()

class AlignmentAdapterTests(unittest.TestCase):
    def test_isolated_worker_keeps_exact_lyrics_with_supported_anchor_fixture(self):
        import sys,types
        from whisperx_worker import align_exact_lyrics
        lines=['Never change these words','We sing every line','Keep the lyrics exact']
        recognized=[]
        for i,text in enumerate(lines):
            a=i*3+1
            words=[{'word':word,'start':a+j*.6,'end':a+(j+1)*.6,'score':.95} for j,word in enumerate(text.split())]
            recognized.append({'start':a,'end':a+2.4,'text':text,'words':words})
        model=types.SimpleNamespace(transcribe=lambda *a,**k:{'language':'en','segments':recognized})
        def aligned(segments,*args,**kwargs):
            result=[]
            for seg in segments:
                words=seg['text'].split();a=seg['start'];b=seg['end'];step=(b-a)/len(words)
                result.append(dict(seg,words=[{'word':word,'start':a+j*step,'end':a+(j+1)*step,'score':.95} for j,word in enumerate(words)]))
            return {'segments':result}
        whisper=types.SimpleNamespace(load_audio=lambda p:np.zeros(44100*12),load_model=lambda *a,**k:model,load_align_model=lambda **k:(None,{}),align=aligned)
        torch=types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda:False))
        messages=[]
        with patch.dict(sys.modules,whisperx=whisper,torch=torch):result=align_exact_lyrics('fixture.wav',lines,'en',messages.append)
        doc=LyricDocument();doc.set_text('\n'.join(lines),12);doc.apply_alignment(result)
        self.assertEqual([e[2] for e in doc.events],lines)
        self.assertTrue(any(v=='aligned' for v in doc.data['alignment_status'].values()))
        self.assertEqual([w[2] for w in doc.words['0']],lines[0].split())
