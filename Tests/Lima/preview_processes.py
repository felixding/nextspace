"""Reap only processes from a private preview after its desktop has stopped."""
import os
from pathlib import Path
import signal
import time


def reap_preview_processes(runtime, grace=3):
    runtime=Path(runtime)
    if (not runtime.is_absolute() or runtime.name!='runtime' or
            not runtime.parent.name.startswith('macbook-preview-') or
            runtime.is_symlink() or runtime.stat().st_uid!=os.getuid()):
        raise ValueError('Cleanup requires an owned private preview runtime')
    marker=os.fsencode('XDG_RUNTIME_DIR='+str(runtime))
    def owned():
        result=[]
        for process in Path('/proc').iterdir():
            if not process.name.isdigit() or int(process.name)==os.getpid():continue
            try:
                if process.stat().st_uid==os.getuid() and marker in (process/'environ').read_bytes().split(b'\0'):
                    result.append(int(process.name))
            except (OSError,PermissionError):pass
        return result
    def send(pid,number):
        # Recheck exact session membership immediately before signalling.
        if pid in owned():
            try:os.kill(pid,number)
            except ProcessLookupError:pass
    stopped=owned()
    for pid in stopped:send(pid,signal.SIGTERM)
    deadline=time.monotonic()+grace
    while owned() and time.monotonic()<deadline:time.sleep(.05)
    forced=owned()
    for pid in forced:send(pid,signal.SIGKILL)
    deadline=time.monotonic()+1
    while owned() and time.monotonic()<deadline:time.sleep(.05)
    return dict(terminated=stopped,forced=forced,remaining=owned())
