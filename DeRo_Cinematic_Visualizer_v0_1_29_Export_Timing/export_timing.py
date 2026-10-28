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
