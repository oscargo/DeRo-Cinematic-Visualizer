"""Stereo preview playback with a device-clock-based playhead and exact loops."""
import subprocess
import time
import numpy as np


def decode_preview(path,ffmpeg='ffmpeg',rate=44100):
    result=subprocess.run([ffmpeg,'-v','error','-i',str(path),'-vn','-ac','2',
        '-ar',str(rate),'-f','f32le','pipe:1'],capture_output=True)
    if result.returncode:raise RuntimeError(result.stderr.decode('utf-8','replace')[-1200:])
    data=np.frombuffer(result.stdout,dtype='<f4').reshape(-1,2).copy()
    if not len(data):raise ValueError('No preview audio decoded.')
    return data


class PreviewAudio:
    def __init__(self,stream_factory=None,clock=time.monotonic):
        self.factory=stream_factory
        self.clock=clock
        self.stream=None
        self.samples=None
        self.rate=44100
        self.muted=False
        self.start_frame=0;self.end_frame=0;self.cursor=0
        self.loop=False
        self.anchor_song=0.;self.anchor_clock=0.

    def load(self,samples):
        self.stop()
        self.samples=samples

    def play(self,start,end,loop=False,loop_start=None):
        self.stop()
        if self.samples is None:return False
        self.start_frame=max(0,min(len(self.samples),round(start*self.rate)))
        self.end_frame=max(self.start_frame,min(len(self.samples),round(end*self.rate)))
        self.cursor=self.start_frame
        if loop_start is not None:self.start_frame=max(0,min(self.end_frame-1,round(loop_start*self.rate)))
        self.loop=loop
        if self.end_frame<=self.start_frame:return False
        self.anchor_song=start;self.anchor_clock=self.clock()
        factory=self.factory
        if factory is None:
            import sounddevice
            factory=sounddevice.OutputStream
        try:
            self.stream=factory(samplerate=self.rate,channels=2,dtype='float32',
                                latency='low',callback=self.callback)
            self.stream.start()
        except Exception:
            self.stop();raise
        return True

    def callback(self,out,frames,info,status):
        self.anchor_song=self.cursor/self.rate
        self.anchor_clock=self.clock()+max(0,info.outputBufferDacTime-info.currentTime)
        out.fill(0)
        offset=0
        while offset<frames:
            available=self.end_frame-self.cursor
            count=min(frames-offset,available)
            if count:
                if not self.muted:out[offset:offset+count]=self.samples[self.cursor:self.cursor+count]
                self.cursor+=count;offset+=count
            if self.cursor>=self.end_frame:
                if self.loop:self.cursor=self.start_frame
                else:break

    def position(self):
        value=self.anchor_song+(self.clock()-self.anchor_clock)
        start,end=self.start_frame/self.rate,self.end_frame/self.rate
        if self.loop and end>start and value>=end:value=start+(value-start)%(end-start)
        return max(start,min(end,value))

    def stop(self):
        stream=self.stream;self.stream=None
        if stream is not None:
            try:stream.stop()
            finally:stream.close()
