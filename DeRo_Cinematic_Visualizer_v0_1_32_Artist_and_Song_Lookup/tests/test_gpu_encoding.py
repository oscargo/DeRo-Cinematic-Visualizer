from dataclasses import replace
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import wave
from unittest.mock import Mock,patch
from export_video import export,EncodingError,_encode
from project_io import DEFAULTS,save_project,load_project,validate_settings
from video_encoder import select_encoder,CPU_OPTIONS,NVENC_OPTIONS
from visualizer_core import Settings


class GPUSelectionTests(unittest.TestCase):
    def test_existing_positional_settings_arguments_keep_their_meaning(self):
        self.assertEqual(Settings(320,180,30,'Title').title,'Title')

    def test_cpu_selection_skips_probe(self):
        with patch('video_encoder.subprocess.run') as run:
            self.assertEqual(select_encoder(Settings(export_encoder='CPU (compatible)')),
                             ('libx264',CPU_OPTIONS))
            run.assert_not_called()

    def test_real_probe_required_and_uses_output_dimensions(self):
        settings=Settings(width=1920,height=1080,fps=60)
        report=Mock()
        with patch('video_encoder.subprocess.run',return_value=Mock(returncode=0,stderr=b'')) as run:
            self.assertEqual(select_encoder(settings,report=report),('h264_nvenc',NVENC_OPTIONS))
            command=run.call_args.args[0]
            self.assertIn('color=c=black:s=1920x1080:r=60',command)
            self.assertIn('h264_nvenc',command)
            self.assertEqual(run.call_args.kwargs['timeout'],20)
            report.assert_called_once_with('NVIDIA NVENC (GPU encoding)')

    def test_missing_gpu_and_timeout_fall_back(self):
        for outcome in (Mock(returncode=1,stderr=b'Cannot load GPU driver'),
                        subprocess.TimeoutExpired('ffmpeg',20)):
            with self.subTest(outcome=outcome),patch('video_encoder.subprocess.run') as run:
                if isinstance(outcome,Exception):run.side_effect=outcome
                else:run.return_value=outcome
                report=Mock()
                self.assertEqual(select_encoder(Settings(export_encoder='NVIDIA NVENC'),report=report)[0],'libx264')
                self.assertIn('CPU fallback',report.call_args.args[0])

    def test_project_roundtrip_and_legacy_default(self):
        self.assertEqual(validate_settings({})['export_encoder'],'Auto (GPU if available)')
        with self.assertRaises(ValueError):validate_settings(dict(DEFAULTS,export_encoder='bad codec'))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'project.dero'
            save_project(path,dict(DEFAULTS,export_encoder='NVIDIA NVENC'))
            self.assertEqual(load_project(path)[0]['export_encoder'],'NVIDIA NVENC')


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
class GPUFallbackExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.source=self.root/'source.wav';self.output=self.root/'out.mp4'
        with wave.open(str(self.source),'wb') as wav:
            wav.setparams((1,2,22050,0,'NONE','not compressed'));wav.writeframes(b'\0\0'*22050)
        self.settings=Settings(width=160,height=90,fps=10,bars=16,dust_count=2)

    def test_gpu_runtime_failure_retries_cpu_and_produces_valid_mp4(self):
        report=Mock();attempts=[]
        def encode(*args):
            attempts.append(args[5])
            if len(attempts)==1:
                Path(args[2]).write_bytes(b'partial GPU output')
                raise EncodingError('simulated driver failure')
            return _encode(*args)
        with patch('export_video.select_encoder',return_value=('h264_nvenc',NVENC_OPTIONS)),patch('export_video._encode',side_effect=encode):
            export(str(self.source),str(self.output),self.settings,start_seconds=.2,end_seconds=.7,encoder_status=report)
        self.assertEqual(attempts,[NVENC_OPTIONS,CPU_OPTIONS])
        self.assertIn('CPU fallback',report.call_args.args[0])
        info=subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=codec_name','-of','csv=p=0',str(self.output)]).decode()
        self.assertIn('h264',info);self.assertIn('aac',info)
        self.assertFalse(list(self.root.glob('.dero-export-*')))

    def test_failed_export_preserves_existing_file(self):
        self.output.write_bytes(b'existing export')
        with patch('export_video.select_encoder',return_value=('h264_nvenc',NVENC_OPTIONS)),patch('export_video._encode',side_effect=EncodingError('encoder failed')) as encode:
            with self.assertRaises(EncodingError):export(str(self.source),str(self.output),self.settings)
        self.assertEqual(encode.call_count,2)
        self.assertEqual(self.output.read_bytes(),b'existing export')
        self.assertFalse(list(self.root.glob('.dero-export-*')))

    def test_rendering_error_does_not_retry_encoding(self):
        with patch('export_video.select_encoder',return_value=('h264_nvenc',NVENC_OPTIONS)),patch('export_video._encode',side_effect=ValueError('bad frame')) as encode:
            with self.assertRaisesRegex(ValueError,'bad frame'):export(str(self.source),str(self.output),self.settings)
            encode.assert_called_once()
        self.assertFalse(self.output.exists())

    def test_actual_ffmpeg_pipe_failure_recovers_to_cpu(self):
        report=Mock()
        with patch('export_video.select_encoder',return_value=('h264_nvenc',['-c:v','dero_missing_encoder'])):
            export(str(self.source),str(self.output),self.settings,encoder_status=report)
        self.assertIn('CPU fallback',report.call_args.args[0])
        self.assertIn('dero_missing_encoder',report.call_args.args[0])
        self.assertGreater(self.output.stat().st_size,0)
        self.assertFalse(list(self.root.glob('.dero-export-*')))
