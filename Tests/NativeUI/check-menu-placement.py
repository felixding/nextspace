#!/usr/bin/env python3
"""Use direct AppKit menus, real work areas and original pointer tracking."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Wayland'))
from gnustep import private_defaults
from integration import until
from shell import Shell

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--probe', type=Path, required=True)
parser.add_argument('--compositor', type=Path, required=True)
parser.add_argument('--shell-probe', type=Path, required=True)
parser.add_argument('--backend', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--expect-gui-sha256', required=True)
parser.add_argument('--menu-level', type=int, choices=(3, 20, 101), default=3)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
results = dict(complete=False, checks=[])
processes = []
last_settled = {}


def save():
    (args.output / 'results.json').write_text(json.dumps(results, indent=2) + '\n')


def record(case, **evidence):
    results['checks'].append(dict(case=case, passed=True, **evidence))
    save()


with tempfile.TemporaryDirectory(prefix='native-menu-placement-') as runtime:
    env = dict(os.environ, XDG_RUNTIME_DIR=runtime, WLR_BACKENDS='headless',
               WLR_HEADLESS_OUTPUTS='2', WLR_RENDERER='pixman')
    for name in ('DISPLAY', 'WAYLAND_DISPLAY', 'WAYLAND_SOCKET', 'LD_PRELOAD'):
        env.pop(name, None)
    private_defaults(env, runtime)
    bundles = Path(runtime) / 'empty-library/Bundles'
    bundles.mkdir(parents=True)
    (bundles / 'libgnustep-wayland-032.bundle').symlink_to(args.backend.resolve())
    control, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    broker, broker_child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    control.settimeout(10)
    with (args.output / 'compositor.stderr').open('w') as log:
        server = subprocess.Popen([str(args.compositor), '-c', str(child.fileno()),
            '-S', str(broker_child.fileno())], pass_fds=[child.fileno(), broker_child.fileno()],
            env=env, stdout=subprocess.PIPE, stderr=log, text=True)
    processes.append(server)
    child.close()
    broker_child.close()
    shell = None

    def command(value):
        control.sendall(value.encode())
        return json.loads(control.recv(1048576))

    def outputs():
        before = shell.output_batches
        shell.send('outputs')
        shell.wait(lambda: shell.output_batches > before, 'fresh output work areas')
        return sorted(shell.outputs.values(), key=lambda h: h['x'])

    try:
        assert select.select([server.stdout], [], [], 15)[0], 'Compositor startup'
        line = server.stdout.readline().strip()
        assert line.startswith('WAYLAND_DISPLAY='), line
        env['WAYLAND_DISPLAY'] = line.split('=', 1)[1]
        shell = Shell(str(args.shell_probe), broker, env, args.output, 0, version=13)
        processes.append(shell.process)
        heads = outputs()
        assert len(heads) == 2, heads
        for head in heads:
            shell.send(f"insets {head['id']} 7 11 67 64")
        first = heads[0]
        assert command(f"resize-output {first['name']} 1464 918")['ok']

        for scale in (120, 150, 180, 210, 240):
            assert command(f"test-scale {first['name']} {scale} 10000")['ok']
            assert command('confirm')['ok']
            head, second = outputs()
            directory = args.output / str(scale)
            directory.mkdir()
            case_runtime = Path(runtime) / str(scale)
            case_runtime.mkdir()
            case_env = dict(env)
            private_defaults(case_env, case_runtime)
            case_bundles = case_runtime / 'empty-library/Bundles'
            case_bundles.mkdir(parents=True)
            (case_bundles / 'libgnustep-wayland-032.bundle').symlink_to(args.backend.resolve())
            with (directory / 'probe.stderr').open('w') as log:
                probe = subprocess.Popen([str(args.probe), '-GSBackend', 'wayland',
                    '-GSTheme', 'NextSpace', '-NSUseRunningCopy', 'NO'], env=case_env,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True)
            processes.append(probe)
            identity = {}

            def send(value):
                probe.stdin.write(value + '\n')
                probe.stdin.flush()

            def read():
                assert select.select([probe.stdout], [], [], 10)[0], 'Native menu response'
                value = json.loads(probe.stdout.readline())
                with (directory / 'probe.jsonl').open('a') as log:
                    log.write(json.dumps(value) + '\n')
                return value

            def state():
                send('state')
                return read()

            def window():
                return next((w for w in command('windows') if w['pid'] == probe.pid
                    and w['client_id'] == identity.get('window') and w['visible']), None)

            last_settled = {}
            def settled():
                s = state()
                identity['window'] = s['window']
                w = window()
                last_settled.update(state=s, window=w)
                if not w:
                    last_settled.update(windows=command('windows'),popups=command('popups'))
                return (s, w) if w and (w['width'], w['height']) == tuple(s['frame'][2:]) else False

            def fits(w, h):
                return (w['x'] >= h['work_x'] and w['y'] >= h['work_y']
                    and w['x'] + w['width'] <= h['work_x'] + h['work_width']
                    and w['y'] + w['height'] <= h['work_y'] + h['work_height'])

            try:
                assert read()['event'] == 'ready'
                libraries = {line.split()[-1] for line in (Path('/proc') / str(probe.pid) / 'maps').read_text().splitlines()
                    if 'libgnustep-gui.so.' in line}
                assert len(libraries) == 1, libraries
                library = Path(libraries.pop())
                assert hashlib.sha256(library.read_bytes()).hexdigest() == args.expect_gui_sha256
                (directory / 'runtime.json').write_text(json.dumps(dict(
                    library=str(library), sha256=args.expect_gui_sha256)) + '\n')
                send('items 12')
                s, w = until(settled, 'direct native menu mapped')
                assert fits(w, head), ('Default menu ignores work-area origin', w, head)
                assert w['preferred_scale'] == scale, ('Native menu is on the wrong density', w, head)
                record(f'{scale}-default-origin', window=w, work=head)

                # A saved menu position can become invalid on a smaller display.
                send(f"move {s['work'][0]} {s['work'][1] - s['frame'][3]}")
                send('show')
                s, w = until(lambda: (v if fits(v[1], head) else False)
                    if (v := settled()) else False, 'saved native menu constrained')
                record(f'{scale}-saved-position-reopen', window=w)

                send('items 20')
                s, w = until(lambda: (v if len(v[0]['items']) == 20 else False)
                    if (v := settled()) else False, 'dynamic native menu layout')
                if w['height'] <= head['work_height']:
                    assert fits(w, head), (w, head)
                else:
                    assert w['y'] == head['work_y'], (w, head)
                record(f'{scale}-dynamic-model-growth', window=w)

                # Menus taller than the screen must use NSMenuView's existing
                # edge shifting; all item hit rectangles come from NSMenuView.
                send('items 55')
                send(f'level {args.menu_level}')
                s, w = until(lambda: (v if len(v[0]['items']) == 55 and v[1]['level']==args.menu_level else False)
                    if (v := settled()) else False, 'oversized native menu layout')
                item = s['items'][0]
                x = round(w['x'] + item[0] + item[2] / 2)
                y = round(w['y'] + item[1] + item[3] / 2)
                assert command(f'pointer {x} {y}')['ok']
                assert command('button 272 1')['ok']
                last = s['items'][-1]
                edge = head['work_y'] + head['work_height'] - 1
                deadline = time.monotonic() + 8
                while True:
                    w = window()
                    target_y = round(w['y'] + last[1] + last[3] / 2)
                    if target_y <= edge - 2:
                        break
                    assert time.monotonic() < deadline, ('Original native menu did not edge-scroll', w, head)
                    for dx in (0, 1):
                        assert command(f'pointer {x + dx} {edge}')['ok']
                        time.sleep(.025)
                assert command(f'pointer {x} {target_y}')['ok']
                assert command('button 272 0')['ok']
                s = until(lambda: (v if v['last'] == 55 and v['actions'] == 1 else False)
                    if (v := state()) else False, 'last original menu command activated')
                record(f'{scale}-oversized-last-item-pointer-action', window=window(), state=s)

                send('items 12')
                s, w = until(lambda: (v if len(v[0]['items']) == 12 else False)
                    if (v := settled()) else False, 'native menu after tracking')
                assert command(f"move {w['id']} {second['work_x'] + 20} {second['work_y'] + 20}")['ok']
                # The test move and its native configure are asynchronous.
                # Finish that transaction before setMain: changes geometry;
                # matching only the screen can retain the old menu origin.
                def moved():
                    value = settled()
                    if not value:return False
                    native, mapped = value
                    top = max(rect['frame'][1] + rect['frame'][3] for rect in native['screens'])
                    expected = (round(native['frame'][0]), round(top-native['frame'][1]-native['frame'][3]))
                    return native if native['work'][0] == second['work_x'] and (mapped['x'],mapped['y']) == expected else False
                s = until(moved, 'native second-output move acknowledged before adoption')
                send('deactivate')
                until(lambda: (v if not v['active'] else False) if (v := state()) else False,
                      'inactive host before production menu show sequence')
                send('adopt')
                s, w = until(lambda: (v if fits(v[1], second) else False)
                    if (v := settled()) else False, 'native adoption on offset output')
                record(f'{scale}-offset-output-adoption', window=w, work=second,initially_inactive=True)
                send('normal')
                normal = until(lambda: next((v for v in command('windows')
                    if v['pid'] == probe.pid and v['title'] == 'Native normal window'
                    and v['visible']), None), 'ordinary titled window mapped')
                shell.send(f"move {normal['id']} -9000 -9000")
                before = shell.done
                shell.send('snapshot')
                shell.wait(lambda: shell.done > before, 'production move processed before assertion')
                def normal_constrained():
                    w = next(v for v in command('windows') if v['id'] == normal['id'])
                    return w if any(min(w['x'] + max(w['width'], 32), h['x'] + h['logical_width'])
                        - max(w['x'], h['x']) >= 32
                        and min(w['y'] + 22, h['y'] + h['logical_height']) - max(w['y'], h['y']) >= 16
                        for h in (head, second)) else False
                normal = until(normal_constrained, 'normal-window title remains constrained')
                record(f'{scale}-normal-window-constraint-preserved', window=normal)
                send('quit')
                probe.wait(timeout=10)
                assert probe.returncode == 0
            finally:
                # Always release an unfinished native tracking gesture.
                command('button 272 0')
                if probe.poll() is None:
                    probe.terminate()
                    probe.wait(timeout=10)
        results['complete'] = True
        save()
        print(json.dumps(dict(complete=True, checks=len(results['checks']))))
    except BaseException as failure:
        results['error'] = repr(failure)
        results['last_settled'] = last_settled
        save()
        raise
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
        if shell:
            shell.log.close()
        control.close()
        broker.close()
        (args.output / 'cleanup.json').write_text(json.dumps(dict(
            exits=[p.returncode for p in processes], live=[p.pid for p in processes if p.poll() is None])) + '\n')
