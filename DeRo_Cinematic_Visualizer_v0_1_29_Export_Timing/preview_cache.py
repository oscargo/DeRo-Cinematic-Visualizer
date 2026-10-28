"""Single-source preview cache; keys include source identity and analysis inputs."""
from dataclasses import dataclass
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

    @classmethod
    def key(cls,path,settings):
        rate=44100 if settings.frequency_max>10584 else 22050
        return ((cls.fingerprint(path),rate),settings.fps,settings.bars,
                settings.frequency_min,settings.frequency_max,
                settings.frequency_scale,settings.spectrum_mapping)

    def snapshot(self):
        """Capture references, never the mutable cache, for an export worker."""
        if self.audio is None or self.analysis_key is None:return None
        samples,sr,_=self.audio
        return CachedAnalysis(self.analysis_key,samples,sr,self.features)

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


@dataclass(frozen=True)
class CachedAnalysis:
    key: tuple
    samples: object
    sample_rate: int
    features: object

    def matches(self,path,settings):
        try:return self.key==PreviewCache.key(path,settings)
        except OSError:return False
