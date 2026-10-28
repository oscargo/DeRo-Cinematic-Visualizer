"""Cooperative cancellation plus interruption of blocked FFmpeg pipe writes."""
from contextlib import contextmanager
import subprocess
import threading


class ExportCancelled(RuntimeError):
    pass


class ExportControl:
    def __init__(self):
        self.event=threading.Event()
        self.lock=threading.Lock()
        self.processes=set()
        self.committed=False

    def check(self):
        if self.event.is_set():raise ExportCancelled('Export canceled')

    def cancel(self):
        with self.lock:
            if self.committed:return False
            self.event.set()
            processes=list(self.processes)
        for proc in processes:
            try:proc.kill()
            except OSError:pass
        return True

    @contextmanager
    def process(self,proc):
        with self.lock:
            self.processes.add(proc)
            canceled=self.event.is_set()
        try:
            if canceled:
                try:proc.kill()
                except OSError:pass
            self.check()
            yield proc
            self.check()
        finally:
            if proc.poll() is None:
                try:proc.kill()
                except OSError:pass
            proc.wait()
            for pipe in (proc.stdout,proc.stderr):
                if pipe is not None:pipe.close()
            with self.lock:self.processes.discard(proc)

    def run(self,cmd,timeout=None,**kwargs):
        self.check()
        with self.process(subprocess.Popen(cmd,**kwargs)) as proc:
            stdout,stderr=proc.communicate(timeout=timeout)
            self.check()
            return subprocess.CompletedProcess(cmd,proc.returncode,stdout,stderr)

    def commit(self,operation):
        # Cancellation and the final atomic replacement have one ordering point.
        with self.lock:
            self.check()
            operation()
            self.committed=True

    def pids(self):
        with self.lock:return [proc.pid for proc in self.processes]
