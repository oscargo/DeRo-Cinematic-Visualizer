"""Monotonic elapsed export time, independent of progress and encoder retries."""
import time


def format_duration(seconds):
    seconds=max(0,int(seconds))
    hours,remainder=divmod(seconds,3600)
    minutes,seconds=divmod(remainder,60)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}'


class ExportTimer:
    def __init__(self):
        self.started=None
        self.elapsed=None

    def start(self):
        self.started=time.monotonic()
        self.elapsed=None
        return self.started

    def stop(self,elapsed):
        self.elapsed=max(0,elapsed)
        self.started=None

    def text(self):
        if self.started is not None:
            return 'Elapsed: '+format_duration(time.monotonic()-self.started)
        if self.elapsed is not None:
            return 'Total export time: '+format_duration(self.elapsed)
        return 'Export time: —'


class ExportETA:
    """Recent frame throughput, reset per encoder attempt; excludes unknown mux time."""
    def __init__(self):
        from collections import deque
        self.samples=deque(maxlen=12)
        self.total=0
        self.finished=False

    def update(self,completed,total,now=None):
        now=time.monotonic() if now is None else now
        if self.samples and completed<=self.samples[-1][1]:self.samples.clear()
        self.samples.append((now,completed));self.total=total

    def text(self,now=None):
        import math
        now=time.monotonic() if now is None else now
        if self.finished:return 'Remaining: —'
        if not self.samples:return 'Remaining: estimating...'
        last,completed=self.samples[-1]
        if completed>=self.total:return 'Remaining: finalizing audio/video...'
        first,initial=self.samples[0]
        elapsed=last-first
        if len(self.samples)<2 or elapsed<.5 or completed<=initial or now-last>5:
            return 'Remaining: estimating...'
        remaining=math.ceil((self.total-completed)*elapsed/(completed-initial))
        return 'Remaining: ~'+format_duration(remaining)+' (estimate; finalization extra)'
