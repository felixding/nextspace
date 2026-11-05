"""Small shared GNUstep fixture setup."""
from contextlib import contextmanager
from io import BytesIO
import json
import os
from pathlib import Path
import re
import select
import shutil
import socket
import subprocess
import tempfile
import time
import uuid


def process_runtime(pid):
    process = Path('/proc') / str(pid)
    candidates = sorted({line.split()[-1] for line in (process/'maps').read_text().splitlines()
        if line.split()[-1].startswith('/') and
           ('.so' in line.split()[-1] or 'libgnustep-' in line.split()[-1])})
    libraries = []
    for path in candidates:
        # The loader also maps non-ELF data such as /etc/ld.so.cache.
        with Path(path).open('rb') as image:
            if image.read(4) == b'\x7fELF':
                libraries.append(path)
    return dict(pid=pid, executable=str((process/'exe').resolve()), libraries=libraries)


def capture_frame(path, size, mode='RGBA'):
    """Read one complete native frame; incomplete or stale-sized pixels are not ready."""
    from PIL import Image
    path = Path(path)
    try:
        data = path.read_bytes()
        with Image.open(BytesIO(data)) as image:
            if image.size == tuple(size):
                return dict(data=data, image=image.convert(mode), path=path)
    except (OSError, SyntaxError):
        pass
    return None


def capture_process_failure(process, artifacts, name):
    """Save a stalled fixture's state before its owner terminates it."""
    root = Path('/proc')/str(process.pid)
    state = dict(pid=process.pid,returncode=process.poll())
    for item in ('status','wchan'):
        try:
            state[item] = (root/item).read_text()
        except OSError:
            pass
    if process.poll() is None:
        try:
            state['runtime'] = process_runtime(process.pid)
        except OSError:
            pass
        debugger = dict(available=bool(shutil.which('gdb')), backtrace_collected=False)
        state['debugger'] = debugger
        if debugger['available']:
            path = artifacts/(name+'-backtrace.log')
            with path.open('w') as log:
                try:
                    result = subprocess.run(['gdb','--batch','--nx',
                        '-iex','set debuginfod enabled off','-p',str(process.pid),
                        '-ex','thread apply all bt'],stdout=log,stderr=log,timeout=15)
                    debugger['returncode'] = result.returncode
                except subprocess.TimeoutExpired:
                    debugger['timed_out'] = True
                    log.write('\nDebugger timed out.\n')
            debugger['backtrace_collected'] = bool(re.search(r'^#0\s', path.read_text(), re.MULTILINE))
    (artifacts/(name+'.json')).write_text(json.dumps(state,indent=2)+'\n')


@contextmanager
def pasteboard_storage(server, probe, env, artifacts):
    """Own native storage for a private test session before launching clients."""
    from integration import until
    started = time.monotonic()
    attempts = []
    with (artifacts/'gpbs.log').open('w') as log:
        storage = subprocess.Popen([str(server), '--no-fork', '-GSLogSyslog', 'NO'],
            env=env, stdout=log, stderr=log)
    try:
        def ready():
            assert storage.poll() is None, (artifacts/'gpbs.log').read_text()
            ping = subprocess.Popen([str(probe), '--ping'], env=env,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                stdout,stderr = ping.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    capture_process_failure(ping,artifacts,'failure-gpbs-ping')
                    capture_process_failure(storage,artifacts,'failure-gpbs-server')
                finally:
                    if ping.poll() is None:
                        ping.kill()
                    stdout,stderr = ping.communicate()
                attempts.append(dict(elapsed_seconds=time.monotonic()-started,
                    returncode=ping.returncode,stdout=stdout,stderr=stderr,timed_out=True))
                # A single stalled query must not end the readiness retry loop.
                return False
            attempts.append(dict(elapsed_seconds=time.monotonic()-started,
                returncode=ping.returncode,stdout=stdout,stderr=stderr))
            return ping.returncode == 0
        until(ready, 'owned native pasteboard storage')
        (artifacts/'gpbs-runtime.json').write_text(json.dumps(process_runtime(storage.pid), indent=2)+'\n')
        yield storage
    finally:
        process = Path('/proc')/str(storage.pid)
        state = {name:(process/name).read_text() for name in ('status','wchan') if (process/name).exists()}
        (artifacts/'gpbs-startup.json').write_text(json.dumps(dict(pid=storage.pid,
            session_id=env.get('NEXTSPACE_SESSION_ID'), config=env.get('GNUSTEP_CONFIG_FILE'),
            attempts=attempts, process=state), indent=2)+'\n')
        if storage.poll() is None:
            storage.terminate()
            try:
                storage.wait(timeout=5)
            except subprocess.TimeoutExpired:
                storage.kill()
                storage.wait()


def private_defaults(env, runtime, application_directory=None):
    source = env.get('GNUSTEP_CONFIG_FILE') or subprocess.check_output(
        ['gnustep-config','--variable=GNUSTEP_CONFIG_FILE'],text=True).strip()
    config = Path(runtime)/'GNUstep.conf'
    # User-installed bundles can shadow the runtime under qualification.
    config.write_text(Path(source).read_text()+
        f'\nGNUSTEP_USER_CONFIG_FILE=\nGNUSTEP_USER_DEFAULTS_DIR={runtime}/defaults\n'
        f'GNUSTEP_USER_DIR_LIBRARY={runtime}/empty-library\n')
    if application_directory:
        with config.open('a') as stream:
            stream.write(f'GNUSTEP_LOCAL_APPS={Path(application_directory).resolve()}\n'
                f'GNUSTEP_SYSTEM_APPS={runtime}/empty-apps\n'
                f'GNUSTEP_NETWORK_APPS={runtime}/empty-apps\n'
                f'GNUSTEP_USER_DIR_APPS={runtime}/empty-apps\n')
    config.chmod(0o600)
    env['GNUSTEP_CONFIG_FILE'] = str(config)


@contextmanager
def headless_session(compositor, artifacts, application_directory=None, extra_env=None, shell_broker=None):
    """Own a private Wayland compositor, defaults database and capture directory."""
    artifacts.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='nextspace-artwork-') as runtime:
        env = dict(os.environ, XDG_RUNTIME_DIR=runtime, WLR_BACKENDS='headless',
            WLR_HEADLESS_OUTPUTS='2', WLR_RENDERER='pixman',
            NEXTSPACE_SESSION_ID='test-artwork-'+uuid.uuid4().hex)
        env.update(extra_env or {})
        for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'WAYLAND_SOCKET'): env.pop(key, None)
        private_defaults(env, runtime, application_directory)
        (artifacts / 'session.json').write_text(json.dumps(dict(session_id=env['NEXTSPACE_SESSION_ID'],application_directory=str(application_directory)),indent=2)+'\n')
        (artifacts / 'GNUstep.conf').write_bytes(Path(env['GNUSTEP_CONFIG_FILE']).read_bytes())
        captures = artifacts / 'captures'; captures.mkdir()
        env['NEXTSPACE_WAYLAND_CAPTURE_DIR'] = str(captures)
        control, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        control.settimeout(5)
        with (artifacts / 'compositor.log').open('w') as log:
            arguments=[str(compositor), '-c', str(child.fileno())];descriptors=[child.fileno()]
            if shell_broker is not None:
                arguments.extend(['-S',str(shell_broker.fileno())]);descriptors.append(shell_broker.fileno())
            server = subprocess.Popen(arguments, env=env,
                pass_fds=descriptors, stdout=subprocess.PIPE, stderr=log, text=True)
            child.close()
            def command(value):
                control.sendall(value.encode()); return json.loads(control.recv(65536))
            try:
                assert select.select([server.stdout], [], [], 10)[0]
                line = server.stdout.readline().strip(); assert line.startswith('WAYLAND_DISPLAY=')
                env['WAYLAND_DISPLAY'] = line.split('=', 1)[1]
                (artifacts / 'compositor-runtime.json').write_text(json.dumps(process_runtime(server.pid), indent=2) + '\n')
                yield env, command
            finally:
                if server.poll() is None: command('quit'); server.wait(timeout=5)
                server.stdout.close(); control.close()
