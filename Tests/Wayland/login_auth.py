#!/usr/bin/env python3
"""Synthetic greetd IPC checks; no real account credentials or PAM changes."""
import argparse
import errno
import json
import os
from pathlib import Path
import select
import shlex
import socket
import struct
import subprocess
import sys
import tempfile
import time


def receive(connection, length):
    data = b''
    while len(data) < length:
        part = connection.recv(length - len(data))
        if not part: return None
        data += part
    return data


def server():
    setup = json.loads(sys.stdin.readline())
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(setup['socket'])
    if os.geteuid() == 0: os.chown(setup['socket'], setup['uid'], setup['gid'], follow_symlinks=False)
    os.chmod(setup['socket'], 0o600)
    listener.listen(1); listener.settimeout(10)
    print(json.dumps(dict(event='ready')), flush=True)
    requests, ok = [], True
    trace=[]
    def event(kind, **values):
        if setup.get('trace'):
            trace.append(dict(event=kind,time=time.time(),**values))
            Path(setup['trace']).write_text(json.dumps(trace,indent=2)+'\n')
    connection, _ = listener.accept()
    with connection:
        connection.settimeout(10)
        if setup.get('wire') == 'close':
            pass
        else:
            for expected, reply in setup['exchanges']:
                header = receive(connection, 4)
                if not header:
                    ok = not setup['exchanges']
                    break
                length = struct.unpack('@I', header)[0]
                assert length <= 65536
                payload = receive(connection, length)
                request = json.loads(payload)
                ok = ok and request == expected
                safe = dict(request)
                if 'response' in safe: safe['response'] = '[redacted]'
                requests.append(safe)
                event('request',request=safe)
                wire = setup.get('wire')
                if wire == 'delay': time.sleep(31); break
                if wire == 'oversized': connection.sendall(struct.pack('@I', 65537)); break
                if wire == 'short-header': connection.sendall(b'\x20'); break
                if wire == 'short-body': connection.sendall(struct.pack('@I', 20) + b'{}'); break
                payload = b'not-json' if wire == 'bad-json' else json.dumps(reply, ensure_ascii=False).encode()
                data = struct.pack('@I', len(payload)) + payload
                if wire == 'fragmented':
                    for byte in data:
                        connection.sendall(bytes([byte])); time.sleep(0.0002)
                else: connection.sendall(data)
                event('reply',reply=reply)
            if not setup['exchanges']:
                ok = connection.recv(1) == b''
    listener.close()
    print(json.dumps(dict(ok=ok, requests=requests)), flush=True)


def run(probe, artifacts):
    artifacts.mkdir(parents=True)
    rows = []
    success = dict(type='success')
    user, secret = 'nativeユーザー', 'synthetic秘密'

    def check(name, script, exchanges, wire=None, unprivileged=False):
        directory = artifacts / name
        directory.mkdir()
        path = directory / 'script.json'
        path.write_text(json.dumps(script, ensure_ascii=False))
        with tempfile.TemporaryDirectory(prefix='ns-login-') as runtime:
            endpoint = str(Path(runtime) / 'auth')
            command = [sys.executable, str(Path(__file__).resolve()), '--server']
            preexec = None
            if unprivileged and os.geteuid() == 0:
                os.chown(runtime, 65534, 65534)
                preexec = lambda: os.setuid(65534)
            elif not unprivileged and os.geteuid() != 0:
                command = ['sudo', '-n', *command]
            with (directory / 'server.stderr').open('w') as errors:
                process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=errors, text=True, preexec_fn=preexec)
            try:
                process.stdin.write(json.dumps(dict(socket=endpoint, uid=os.getuid(), gid=os.getgid(),
                    exchanges=exchanges, wire=wire), ensure_ascii=False) + '\n')
                process.stdin.flush()
                assert select.select([process.stdout], [], [], 10)[0], 'No mock service readiness'
                assert json.loads(process.stdout.readline())['event'] == 'ready'
                arguments = [str(probe), endpoint, str(path)]
                client = subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if wire == 'delay':
                    deadline = time.monotonic() + 5
                    libraries = []
                    while time.monotonic() < deadline:
                        assert client.poll() is None, 'Deadline probe exited before runtime observation'
                        libraries = sorted({line.split()[-1] for line in Path(f'/proc/{client.pid}/maps').read_text().splitlines()
                            if 'libgnustep-base.so.' in line or 'libobjc.so.' in line})
                        if all(any(token in name for name in libraries)
                               for token in ('libgnustep-base.so.','libobjc.so.')): break
                        time.sleep(0.01)
                    assert any('libgnustep-base.so.' in name for name in libraries)
                    assert any('libobjc.so.' in name for name in libraries)
                    (directory / 'runtime.json').write_text(json.dumps(dict(pid=client.pid,
                        executable=str(Path(f'/proc/{client.pid}/exe').resolve()), libraries=libraries), indent=2) + '\n')
                stdout, stderr = client.communicate(timeout=40)
                result = subprocess.CompletedProcess(arguments, client.returncode, stdout, stderr)
                (directory / 'probe.stderr').write_text(result.stderr)
                assert result.returncode == 0, result.stderr
                actual = json.loads(result.stdout)
                assert secret not in result.stdout + result.stderr, 'Credentials reached probe output'
                process.stdin.close()
                assert select.select([process.stdout], [], [], 10)[0], 'No mock service completion'
                observed = json.loads(process.stdout.readline())
                process.wait(timeout=5)
                assert process.returncode == 0 and observed['ok'], observed
                (directory / 'results.json').write_text(json.dumps(dict(actual=actual, service=observed), indent=2) + '\n')
                rows.append(dict(name=name, actual=actual, service=observed))
                return actual, observed
            finally:
                if not process.stdin.closed: process.stdin.close()
                if process.poll() is None:
                    process.wait(timeout=40)
                process.stdout.close()

    begin = dict(operation='begin', user=user)
    request = dict(type='create_session', username=user)
    literal = ['space value', "a'b", '日本語', '$(touch forbidden)', '`touch forbidden`', '; touch forbidden']
    arguments = [sys.executable, '-c', 'import json,sys; print(json.dumps(sys.argv[1:]))', *literal]
    quoted = ["'" + value.replace("'", "'\\''") + "'" for value in arguments]
    script = [begin, dict(operation='respond', response=secret), dict(operation='respond'),
              dict(operation='respond', response='visible value'), dict(operation='respond'),
              dict(operation='start', arguments=arguments, environment=['XDG_SESSION_TYPE=wayland'])]
    def message(kind, value): return dict(type='auth_message', auth_message_type=kind, auth_message=value)
    exchanges = [(request, message('secret', 'Password:')),
        (dict(type='post_auth_message_response', response=secret), message('info', 'Notice')),
        (dict(type='post_auth_message_response'), message('visible', 'Token:')),
        (dict(type='post_auth_message_response', response='visible value'), message('error', 'Notice')),
        (dict(type='post_auth_message_response'), success),
        (dict(type='start_session', cmd=quoted, env=['XDG_SESSION_TYPE=wayland']), success)]
    actual, observed = check('conversation', script, exchanges, wire='fragmented')
    assert len(actual) == 6 and all('reply' in item for item in actual)
    command = ' '.join(observed['requests'][-1]['cmd'])
    assert shlex.split(command) == arguments
    result = subprocess.run(['/bin/sh', '-c', 'exec ' + command], cwd=artifacts, capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == literal and not (artifacts / 'forbidden').exists()
    error_reply = dict(type='error', error_type='auth_error', description='Authentication failed')
    actual, _ = check('auth-error-cancel', [begin, dict(operation='cancel')],
        [(request, error_reply), (dict(type='cancel_session'), success)])
    assert actual[0]['reply'] == error_reply and actual[1]['reply'] == success
    invalid = [dict(operation='begin', user=''), dict(operation='respond', response=42),
        dict(operation='start', arguments=[], environment=[]), dict(operation='start', arguments=[''], environment=[]),
        dict(operation='start', arguments=['program'], environment=['INVALID']), dict(operation='begin', user='x\0y')]
    actual, _ = check('invalid-request', invalid, [])
    assert len(actual) == len(invalid) and all(item.get('error') == errno.EINVAL for item in actual)
    actual, _ = check('wrong-peer', [begin], [], unprivileged=True)
    assert actual == [dict(operation='connect', error=errno.EACCES)]
    for wire in ('oversized', 'short-header', 'short-body', 'bad-json', 'close'):
        actual, _ = check(wire, [begin, dict(operation='cancel')], [(request, success)], wire=wire)
        assert all('error' in item and 'reply' not in item for item in actual), actual
        assert actual[-1]['error'] == errno.ENOTCONN
    for name, reply in [('array', []), ('missing-type', {}), ('unknown-type', dict(type='unknown')),
                        ('missing-prompt', dict(type='auth_message', auth_message_type='secret')),
                        ('invalid-prompt-kind', message('unknown','Prompt'))]:
        actual, _ = check(name, [begin], [(request, reply)])
        assert actual[0]['error'] == errno.EPROTO, actual
    repeated = [dict(operation='respond') for _ in range(100)]
    actual, _ = check('many-pam-messages', repeated, [(dict(type='post_auth_message_response'), message('info','Notice'))] * 100)
    assert len(actual) == 100 and all('reply' in item for item in actual)
    actual, _ = check('deadline', [begin], [(request, success)], wire='delay')
    assert actual[0]['error'] == errno.ETIMEDOUT
    (artifacts / 'results.json').write_text(json.dumps(rows, indent=2) + '\n')
    print(f'Native Login IPC: {len(rows)} synthetic transport/conversation cases PASS')


if __name__ == '__main__':
    if sys.argv[1:] == ['--server']: server()
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--probe', type=Path, required=True)
        parser.add_argument('--artifacts', type=Path, required=True)
        args = parser.parse_args()
        run(args.probe.resolve(), args.artifacts.resolve())
