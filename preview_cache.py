"""Single-source preview cache; keys include source identity and analysis inputs."""
import os


class PreviewCache:
    def __init__(self):
        self.source_key=None
        self.audio=None
        self.analysis_key=None
        self.features=None

    @staticmethod
    def fingerprint(path):
        stat=os.stat(path)
        return (os.path.abspath(path),stat.st_dev,stat.st_ino,stat.st_size,
                stat.st_mtime_ns,stat.st_ctime_ns)

    def prepare(self,path,settings,load_audio,decode_preview,audio_features):
        source=self.fingerprint(path)
        rate=44100 if settings.frequency_max>10584 else 22050
        audio_key=(source,rate)
        if self.source_key!=audio_key:
            samples,sr=load_audio(path,sample_rate=rate)
            playback=decode_preview(path)
            if self.fingerprint(path)!=source:
                raise OSError('Audio changed while loading; refresh preview again.')
            self.audio=(samples,sr,playback)
            self.source_key=audio_key
            self.analysis_key=None
        samples,sr,playback=self.audio
        key=(audio_key,settings.fps,settings.bars,settings.frequency_min,
             settings.frequency_max,settings.frequency_scale,settings.spectrum_mapping)
        if key!=self.analysis_key:
            features=audio_features(samples,sr,*key[1:])
            self.features=features
            self.analysis_key=key
        return samples,sr,playback,self.features
