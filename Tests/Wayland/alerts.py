"""Drive real DesktopKit alert cancellation and keyboard defaults at five densities."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from integration import read_json_lines, until
from gnustep import process_runtime


def assert_on_output(window,outputs):
    assert any(window['x']>=head['x'] and window['y']>=head['y'] and
        window['x']+window['width']<=head['x']+head['width'] and
        window['y']+window['height']<=head['y']+head['height'] for head in outputs), ('Alert crosses an output gap',window,outputs)


def run(probe, env, command, artifacts):
    artifacts.mkdir(parents=True, exist_ok=True)
    original = command('outputs')
    records = []
    client = None
    scale, index = None, None
    try:
        for scale in (120, 150, 180, 210, 240):
            for head in original:
                assert command(f"test-scale {head['name']} {scale} 10000")['ok']
                assert command('confirm')['ok']
            log = artifacts / f'{scale}.jsonl'
            with log.open('w') as stdout, (artifacts / f'{scale}.stderr').open('w') as stderr:
                client = subprocess.Popen([probe, '-GSBackend', 'libgnustep-wayland', '-GSTheme', 'NextSpace',
                    '-NSUseRunningCopy', 'NO'], env=env, stdout=stdout, stderr=stderr)
            def events():
                assert client.poll() is None, (artifacts / f'{scale}.stderr').read_text()
                return read_json_lines(log, '{')
            for index in range(2):
                row = until(lambda: next((r for r in events() if r['event'] == 'alert' and r['index'] == index), None),
                            'loaded alert default action')
                if index == 0:
                    (artifacts / f'{scale}-runtime.json').write_text(json.dumps(process_runtime(client.pid), indent=2) + '\n')
                def ready():
                    return next((w for w in command('windows') if w['pid'] == client.pid and w['visible'] and
                        w['focused'] and w['client_id'] == row['window'] and w['preferred_scale'] == scale and
                        w['buffer_width'] == (w['width'] * scale + 60) // 120 and
                        w['buffer_height'] == (w['height'] * scale + 60) // 120), None)
                window = until(ready, 'focused alert at preferred density')
                assert_on_output(window,command('outputs'))
                if index == 0:
                    x = round(window['x'] + row['cancel_x'])
                    y = round(window['y'] + window['height'] - row['cancel_y'])
                    assert command(f"pointer {x} {y}")['ok']
                    assert command('button 272 1')['ok']; time.sleep(.02); assert command('button 272 0')['ok']
                else:
                    assert command('key 28 1')['ok']; time.sleep(.02); assert command('key 28 0')['ok']
                records.append(dict(scale=scale, index=index, window=window))
            client.wait(timeout=10)
            assert client.returncode == 0, (artifacts / f'{scale}.stderr').read_text()
            assert any(r['event'] == 'passed' for r in read_json_lines(log, '{'))
            until(lambda: all(w['pid'] != client.pid for w in command('windows')),
                  'exited alert process surfaces removed')
            client = None
        (artifacts / 'results.json').write_text(json.dumps(dict(alerts=records,
            passed=['loaded default action', 'pointer cancellation', 'Return after cancellation']), indent=2) + '\n')
    except Exception as error:
        failure = dict(error=str(error), scale=scale, index=index,
            pid=client.pid if client else None, exit_code=client.poll() if client else None)
        try:
            failure['windows'] = command('windows')
            if client and client.poll() is None:
                failure['runtime'] = process_runtime(client.pid)
                for name in ('status', 'wchan', 'syscall'):
                    try:
                        failure[name] = Path(f'/proc/{client.pid}/{name}').read_text()
                    except OSError as diagnostic_error:
                        failure[name] = str(diagnostic_error)
                if shutil.which('gdb'):
                    with (artifacts / 'failure-backtrace.log').open('w') as log:
                        subprocess.run(['gdb', '--batch', '--nx', '-p', str(client.pid),
                            '-ex', 'thread apply all bt'], stdout=log, stderr=log, timeout=10)
        except Exception as diagnostic_error:
            failure['diagnostic_error'] = str(diagnostic_error)
        (artifacts / 'failure.json').write_text(json.dumps(failure, indent=2) + '\n')
        raise
    finally:
        original_error = sys.exception()
        try:
            if client and client.poll() is None:
                client.terminate()
                try:
                    client.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    client.kill(); client.wait(timeout=5)
                    (artifacts / 'cleanup.json').write_text(json.dumps(dict(
                        pid=client.pid, sigterm_timed_out=True, returncode=client.returncode), indent=2) + '\n')
                    if original_error:
                        original_error.add_note('Alert probe ignored SIGTERM and required SIGKILL during cleanup.')
            for head in original:
                assert command(f"test-scale {head['name']} {head['scale']} 10000")['ok']
                assert command('confirm')['ok']
        except Exception as cleanup_error:
            if original_error is None:
                raise
            original_error.add_note('Alert cleanup also failed: ' + str(cleanup_error))
