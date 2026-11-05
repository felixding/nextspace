#!/usr/bin/env python3
"""Real pointer-driven Wayland transfers with an independent toolkit."""
import argparse
import base64
import json
import os
from pathlib import Path
import select
import signal
import socket
import subprocess
import tempfile
import time
import uuid
from integration import until
from gnustep import process_runtime


def events(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.startswith('{')]


def run(compositor, client, artifacts, registry_probe=None, native_probe=None, pair='gtk-gtk',
        reject_target=False, same_client=False, file_drag=False, move=False, local_move=False, legacy_source=False,
        pasteboard_server=None, pasteboard_probe=None, protocol_mode='native', repeat=1, invalid_files=None,
        delayed_drop=False, reentrant_move=False, framed=False, negative_origin=False):
    source_kind, target_kind = pair.split('-')
    native_source, native_target = source_kind == 'native', target_kind == 'native'
    if (native_source or native_target) and not native_probe: raise ValueError('Native probe is required')
    if same_client and pair != 'native-native': raise ValueError('Shared connection requires two native windows')
    if local_move and not native_source: raise ValueError('Local action masks require a native source')
    if reentrant_move and not native_source: raise ValueError('Reentrant movement requires a native source')
    if legacy_source and (not native_source or move or local_move): raise ValueError('Legacy fixture supports native copy drags')
    if not 1 <= repeat <= 1048576 or (repeat != 1 and file_drag):
        raise ValueError('Text repetition requires a text source')
    if invalid_files and pair != 'gtk-native': raise ValueError('Invalid URI fixture requires GTK to native')
    if delayed_drop and (pair != 'native-native' or not file_drag): raise ValueError('Delayed fixture requires native mixed data')
    rejected = reject_target or invalid_files is not None
    if bool(pasteboard_server) != bool(pasteboard_probe): raise ValueError('Storage requires its ping probe')
    source_title = 'NativeDragSource' if native_source else 'GtkDragSource'
    target_title = 'NativeDragTarget' if native_target else 'GtkDragTarget'
    artifacts.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='nextspace-drag-') as runtime:
        env = dict(os.environ, XDG_RUNTIME_DIR=runtime, WLR_BACKENDS='headless',
                   WLR_HEADLESS_OUTPUTS='2', WLR_RENDERER='pixman', GDK_BACKEND='wayland',
                   GSK_RENDERER='cairo', GTK_A11Y='none',
                   NEXTSPACE_GS_BACKEND='wayland', NEXTSPACE_SESSION_ID='test-' + str(uuid.uuid4()))
        for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'WAYLAND_SOCKET'):
            env.pop(key, None)
        control, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        control.settimeout(5)
        with (artifacts / 'compositor.log').open('w') as log:
            switches = {'native': [], 'no-fractional': ['-F'], 'no-viewporter': ['-V'], 'no-placement': ['-A']}[protocol_mode]
            server = subprocess.Popen([compositor, '-c', str(child.fileno()), *switches], pass_fds=[child.fileno()],
                                      env=env, stdout=subprocess.PIPE, stderr=log, text=True)
        child.close()
        clients = []
        toolkit_clients = {}
        def command(value):
            control.sendall(value.encode())
            return json.loads(control.recv(65536))
        def window(title, expect_alive=False):
            process = toolkit_clients.get(title)
            if expect_alive and process is not None:
                assert process.poll() is None, f'{title} exited {process.returncode}'
            return next((w for w in command('windows') if w['title'] == title and w['visible']), None)
        def backing_scale(scale):
            return ((scale + 119) // 120) * 120 if protocol_mode in ('no-fractional', 'no-viewporter') else scale
        def source_action():
            entries = [e for e in events(artifacts / 'source.log') if e['event'] == 'drag-action']
            return entries[-1]['action'] if entries else None
        def negotiated(state, target, action):
            return state['target'] == target['id'] and state['action'] == action
        def start_drag():
            nonlocal source
            source = window(source_title)
            kind = 'drag-begin' if native_source else 'click'
            before = len([e for e in events(artifacts / 'source.log') if e['event'] == kind])
            assert command(f"pointer {source['x'] + 50} {source['y'] + 100}")['ok']
            assert command('button 272 1')['ok']
            until(lambda: len([e for e in events(artifacts / 'source.log') if e['event'] == kind]) > before,
                  'source receives the button press')
            motion = 0
            def begin_drag():
                nonlocal motion
                if command('drag-state')['active']: return True
                # GTK needs movement after its minimum drag hold time.
                assert command(f"pointer {source['x'] + 90 + motion % 20} {source['y'] + 140}")['ok']
                motion += 1
                return False
            until(begin_drag, 'serial-authorized compositor pointer drag')
        try:
            assert select.select([server.stdout], [], [], 10)[0], 'No compositor socket'
            line = server.stdout.readline().strip()
            assert line.startswith('WAYLAND_DISPLAY='), line
            env['WAYLAND_DISPLAY'] = line.split('=', 1)[1]
            if negative_origin:
                head = command('outputs')[0]['name']
                assert command(f'output-position {head} -1600 -200')['ok']
            drag_file = Path(runtime) / 'NextSpace drag日本語.txt'
            if file_drag: drag_file.write_text('original drag fixture\n')
            if pasteboard_server and (native_source or native_target):
                with (artifacts / 'storage.log').open('w') as log:
                    storage = subprocess.Popen([pasteboard_server, '--no-fork'], env=env, stdout=log, stderr=log)
                    clients.append(storage)
                def storage_ready():
                    assert storage.poll() is None, f'Storage exited {storage.returncode}: ' + (artifacts / 'storage.log').read_text()
                    # Cold distributed-object startup can exceed five seconds
                    # in the software-rendering container; transfers keep their own deadlines.
                    result = subprocess.run([pasteboard_probe, '--ping'], env=env, capture_output=True, timeout=15)
                    (artifacts / 'storage-ping.log').write_bytes(result.stdout + result.stderr)
                    return result.returncode == 0
                until(storage_ready, 'session storage is ready')
            if registry_probe:
                result = subprocess.run([registry_probe, '--invalid-drag'], env=env,
                                        capture_output=True, text=True, timeout=10)
                (artifacts / 'invalid-drag.log').write_text(result.stdout + result.stderr)
                assert result.returncode == 0, result.stdout + result.stderr
                assert not command('drag-state')['active']
                with (artifacts / 'empty-drag.log').open('w') as log:
                    empty = subprocess.Popen([registry_probe, '--empty-drag'], env=env, stdout=log, stderr=log)
                    clients.append(empty)
                empty_window = until(lambda: window('EmptyDragProbe'), 'source-less drag client maps')
                assert command(f"pointer {empty_window['x'] + 10} {empty_window['y'] + 10}")['ok']
                assert command('button 272 1')['ok']
                until(lambda: command('drag-state')['active'], 'valid source-less drag starts')
                assert command('key 1 1')['ok']
                assert command('key 1 0')['ok']
                until(lambda: not command('drag-state')['active'], 'source-less drag cancels without a source object')
                assert command('button 272 0')['ok']
                assert command(f"close {empty_window['id']}")['ok']
                empty.wait(timeout=5)
                assert empty.returncode == 0, (artifacts / 'empty-drag.log').read_text()
            for mode in ('source', 'target'):
                if same_client and mode == 'target':
                    (artifacts / 'target.log').unlink(missing_ok=True)
                    (artifacts / 'target.log').symlink_to('source.log')
                    continue
                with (artifacts / f'{mode}.log').open('w') as log:
                    native = native_source if mode == 'source' else native_target
                    arguments = [native_probe, '-DragSource', 'YES' if mode == 'source' else 'NO',
                        '-GSTheme', 'NextSpace', '-NSUseRunningCopy', 'NO', '-GSSuppressAppIcon', 'YES'] if native else [client, f'--drag-{mode}']
                    if native and framed: arguments += ['-FramedDrag', 'YES']
                    if mode == 'target' and reject_target: arguments += ['-RejectDrop', 'YES'] if native else ['--reject-drop']
                    if same_client: arguments += ['-SameClient', 'YES']
                    if file_drag and mode == 'source': arguments += ['-DragFile' if native else '--drag-file', str(drag_file)]
                    if repeat != 1 and mode == 'source':
                        arguments += ['-DragRepeat' if native else '--drag-repeat', str(repeat)]
                    if delayed_drop: arguments += ['-TextWithFile', 'YES']
                    if invalid_files and mode == 'source':
                        payload = {'remote-host': 'file://remote.invalid/tmp/file.txt\r\n',
                                   'web-uri': 'https://example.invalid/file.txt\r\n',
                                   'malformed': 'file:///tmp/%FF.txt\r\n',
                                   'nul': 'file:///tmp/part%00file.txt\r\n'}[invalid_files]
                        arguments += ['--drag-uri', payload]
                    if move: arguments += ['-MoveDrag', 'YES'] if native else ['--drag-move']
                    if local_move and native and mode == 'source': arguments += ['-LocalMove', 'YES']
                    if legacy_source and native and mode == 'source': arguments += ['-LegacySource', 'YES']
                    if reentrant_move and mode == 'source': arguments += ['-ReentrantMove', 'YES']
                    process = subprocess.Popen(arguments, env=env, stdout=log, stderr=log)
                    clients.append(process)
                    toolkit_clients[source_title if mode == 'source' else target_title] = process
                    if mode == 'target': target_process = process
            source = until(lambda: window(source_title, True), 'drag source')
            target = until(lambda: window(target_title, True), 'drop target')
            (artifacts/'runtime.json').write_text(json.dumps(dict(
                compositor=process_runtime(server.pid),
                clients={title: process_runtime(process.pid) for title, process in toolkit_clients.items()}), indent=2)+'\n')
            for item in (source, target):
                assert command(f"resize {item['id']} 401 301")['ok']
            until(lambda: all(window(title)['width'] == 401 for title in (source_title, target_title)),
                  'odd-size drag test windows')
            trials = []
            for source_scale, target_scale in ((120, 240), (150, 180), (180, 240), (210, 150), (240, 120), (180, 210)):
                outputs = command('outputs')
                for output, scale in zip(outputs, (source_scale, target_scale)):
                    assert command(f"test-scale {output['name']} {scale} 10000")['ok']
                    assert command('confirm')['ok']
                outputs = command('outputs')
                for item, output in zip((source, target), outputs):
                    assert command(f"move {item['id']} {output['x'] + 80} {output['y'] + 80}")['ok']
                for title, output in zip((source_title, target_title), outputs):
                    until(lambda: (w := window(title))['x'] == output['x'] + 80 and
                          w['y'] == output['y'] + 80, 'client placement after output transition')
                for title, scale in zip((source_title, target_title), (source_scale, target_scale)):
                    if framed and protocol_mode == 'native' and (
                            (title == source_title and native_source) or (title == target_title and native_target)):
                        until(lambda: (w := window(title))['server_decorated'] and
                              w['surface_width'] < w['width'] and w['surface_height'] < w['height'],
                              'native server frame and content-only drag surface')
                    density = backing_scale(scale)
                    until(lambda: (w := window(title))['preferred_scale'] == scale and
                          abs(w['buffer_width'] - 401 * density / 120) < 1,
                          'client renders the new density')
                source, target = window(source_title), window(target_title)
                before = len([e for e in events(artifacts / 'target.log') if e['event'] == 'drop'])
                before_end = len([e for e in events(artifacts / 'source.log') if e['event'] == 'drag-end'])
                before_cancel = len([e for e in events(artifacts / 'source.log') if e['event'] == 'drag-cancel'])
                start_drag()
                target = window(target_title)
                assert command(f"pointer {target['x'] + 120} {target['y'] + 140}")['ok']
                action = 0 if invalid_files else 2 if move or (same_client and local_move and protocol_mode != 'no-placement') else 1
                state = until(lambda: (d if negotiated((d := command('drag-state')), target, action) else None),
                              'target negotiates the requested action')
                if not trials:
                    output = command('outputs')[0]
                    assert command(f"pointer {output['x'] + 550} {output['y'] + 450}")['ok']
                    until(lambda: command('drag-state')['target'] == 0, 'drag leaves the target')
                    assert command(f"pointer {target['x'] + 120} {target['y'] + 140}")['ok']
                    until(lambda: negotiated((d := command('drag-state')), target, action),
                          'same gesture reenters and renegotiates')
                assert state['icon'], state
                if native_source:
                    state = until(lambda: (d if (d := command('drag-state')).get('buffer_width') ==
                        (33 * backing_scale(target_scale) + 60) // 120 and d.get('buffer_height') ==
                        (31 * backing_scale(target_scale) + 60) // 120 else None), 'drag image adopts the destination density')
                    assert (state['width'], state['height']) == (33, 31), state
                    assert state['samples'] == [0xffff0000] * 4, state
                assert command(f"hit {target['x'] + 120} {target['y'] + 140}")['id'] == target['id'], 'drag image intercepts input'
                if delayed_drop and not trials: time.sleep(5.2)
                assert command('button 272 0')['ok']
                endings = until(lambda: (d if len(d := [e for e in events(artifacts / 'source.log') if e['event'] == 'drag-end']) > before_end else None),
                                'source completes the drop')
                if rejected:
                    assert len([e for e in events(artifacts / 'target.log') if e['event'] == 'drop']) == before
                    if native_source: assert endings[-1]['action'] == 0, endings[-1]
                    else: assert len([e for e in events(artifacts / 'source.log') if e['event'] == 'drag-cancel']) == before_cancel + 1
                    drop = None
                else:
                    drops = until(lambda: (d if len(d := [e for e in events(artifacts / 'target.log') if e['event'] == 'drop']) > before else None),
                                  'Unicode drop arrives in target toolkit')
                    drop = drops[-1]
                    if file_drag:
                        files = drop.get('files') or [base64.b64decode(value).decode() for value in drop['file_base64']]
                        assert files == [str(drag_file)], drop
                        assert drag_file.read_text() == 'original drag fixture\n'
                        if delayed_drop: assert base64.b64decode(drop['base64']).decode() == 'NextSpace日本語'
                    else: assert base64.b64decode(drop['base64']).decode() == 'NextSpace日本語' * repeat
                    assert (drop['x'], drop['y']) == (120, target['height'] - 140 if native_target else 140), drop
                    assert endings[-1]['action'] == (16 if native_source and action == 2 else action), endings[-1]
                    if native_target: assert drop['local'] == (same_client and protocol_mode != 'no-placement'), drop
                    if drop.get('local'):
                        assert (drop['image_x'], drop['image_y']) == (112, target['height'] - 148), drop
                    if not trials and native_target and protocol_mode != 'no-placement':
                        entries = [event for event in events(artifacts / 'target.log') if
                                   event['event'] == 'drag-enter' and event['window'] == target_title]
                        assert len(entries) == 2 and all(event['sequence'] == drop['sequence'] for event in entries), entries
                    if legacy_source: assert endings[-1]['legacy'], endings[-1]
                if native_source and protocol_mode != 'no-placement':
                    bottom = max(output['y'] + output['height'] for output in command('outputs'))
                    assert (endings[-1]['x'], endings[-1]['y']) == (target['x'] + 112, bottom - target['y'] - 148), endings[-1]
                if not native_source:
                    assert endings[-1]['delete'] == (move and not rejected), endings[-1]
                until(lambda: not command('drag-state')['active'] and not command('drag-state')['icon'],
                      'drag and image resources released')
                trials.append(dict(source_scale=source_scale, target_scale=target_scale, state=state, drop=drop,
                    source=window(source_title), target=window(target_title), outputs=command('outputs')))
            # A drop on the empty desktop cancels without transferring data.
            completed = len([e for e in events(artifacts / 'source.log') if e['event'] == 'drag-end'])
            cancelled = len([e for e in events(artifacts / 'source.log') if e['event'] == 'drag-cancel'])
            start_drag()
            output = command('outputs')[0]
            assert command(f"pointer {output['x'] + 600} {output['y'] + 500}")['ok']
            until(lambda: command('drag-state')['target'] == 0, 'empty desktop has no drop target')
            assert command('button 272 0')['ok']
            endings = until(lambda: (d if len(d := [e for e in events(artifacts / 'source.log') if e['event'] == 'drag-end']) > completed else None),
                            'source receives cancelled drop completion')
            cancellations = [e for e in events(artifacts / 'source.log') if e['event'] == 'drag-cancel']
            # wl_data_source.cancelled carries no detailed reason; GTK may
            # classify the same wire cancellation as an unspecified error.
            if native_source: assert endings[-1]['action'] == 0, endings[-1]
            else: assert len(cancellations) == cancelled + 1, cancellations
            assert len([e for e in events(artifacts / 'target.log') if e['event'] == 'drop']) == (0 if rejected else len(trials))
            until(lambda: not command('drag-state')['active'] and not command('drag-state')['icon'], 'cancelled drag resources released')
            # Escape also cancels over a valid target, before any data is dropped.
            start_drag()
            target = window(target_title)
            assert command(f"pointer {target['x'] + 120} {target['y'] + 140}")['ok']
            until(lambda: negotiated(command('drag-state'), target, action), 'escape cancellation has a valid target')
            completed = len([e for e in events(artifacts / 'source.log') if e['event'] == 'drag-end'])
            cancelled = len([e for e in events(artifacts / 'source.log') if e['event'] == 'drag-cancel'])
            assert command('key 1 1')['ok']
            assert command('key 1 0')['ok']
            until(lambda: not command('drag-state')['active'] and not command('drag-state')['icon'], 'escape releases the drag grab')
            assert command('button 272 0')['ok']
            endings = until(lambda: (d if len(d := [e for e in events(artifacts / 'source.log') if e['event'] == 'drag-end']) > completed else None),
                            'escape reports source cancellation')
            if native_source: assert endings[-1]['action'] == 0, endings[-1]
            else: assert len([e for e in events(artifacts / 'source.log') if e['event'] == 'drag-cancel']) == cancelled + 1
            assert len([e for e in events(artifacts / 'target.log') if e['event'] == 'drop']) == (0 if rejected else len(trials))
            if not same_client and not invalid_files:
                # Stop the receiver before releasing the button so it cannot
                # finish before its connection disappears during the drop.
                start_drag()
                assert command(f"pointer {target['x'] + 120} {target['y'] + 140}")['ok']
                until(lambda: negotiated((d := command('drag-state')), target, action),
                      'receiver accepts before closing during the drop')
                completed = len([e for e in events(artifacts / 'source.log') if e['event'] == 'drag-end'])
                cancelled = len([e for e in events(artifacts / 'source.log') if e['event'] == 'drag-cancel'])
                finished_before = len([e for e in events(artifacts / 'source.log') if e['event'] == 'xdnd-finished'])
                os.kill(target_process.pid, signal.SIGSTOP)
                assert command('button 272 0')['ok']
                target_process.kill(); target_process.wait(timeout=5)
                until(lambda: window(target_title) is None, 'closed receiver is removed')
                endings = until(lambda: (d if len(d := [e for e in events(artifacts / 'source.log') if e['event'] == 'drag-end']) > completed else None),
                                'closed receiver cancels the source')
                if native_source: assert endings[-1]['action'] == 0, endings[-1]
                else: assert len([e for e in events(artifacts / 'source.log') if e['event'] == 'drag-cancel']) == cancelled + 1
                until(lambda: not command('drag-state')['active'] and not command('drag-state')['icon'], 'closed receiver frees the drag')
            if native_source:
                for operation in ('present', 'shade') if source['title_height'] else ('present',):
                    start_drag()
                    completed = len([e for e in events(artifacts / 'source.log') if e['event'] == 'drag-end'])
                    assert command(f"{operation} {source['id']} {int(operation == 'shade')}")['ok']
                    endings = until(lambda: (d if len(d := [e for e in events(artifacts / 'source.log') if e['event'] == 'drag-end']) > completed else None),
                                    'suppressing the retained source cancels its gesture')
                    assert endings[-1]['action'] == 0
                    until(lambda: not command('drag-state')['active'] and not command('drag-state')['icon'], 'suppressed source frees its grab and image')
                    assert command('button 272 0')['ok']
                    assert command(f"{operation} {source['id']} {int(operation == 'present')}")['ok']
                    until(lambda: window(source_title), 'retained source returns for another gesture')
            start_drag()
            completed = len([e for e in events(artifacts / 'source.log') if e['event'] == 'drag-end'])
            assert command(f"close {source['id']}")['ok']
            until(lambda: window(source_title) is None, 'source window closes during its gesture')
            until(lambda: not command('drag-state')['active'] and not command('drag-state')['icon'], 'closed source frees its grab and image')
            if native_source:
                endings = until(lambda: (d if len(d := [e for e in events(artifacts / 'source.log') if e['event'] == 'drag-end']) > completed else None),
                                'closed native source reports cancellation')
                assert endings[-1]['action'] == 0, endings[-1]
            if same_client: assert window(target_title), 'closing one window must preserve its peer'
            assert command('button 272 0')['ok']
            (artifacts / 'results.json').write_text(json.dumps(dict(pair=pair, rejected=rejected, same_client=same_client,
                file_drag=file_drag, move=move, local_move=local_move, legacy_source=legacy_source,
                protocol_mode=protocol_mode, repeat=repeat, invalid_files=invalid_files, delayed_drop=delayed_drop, trials=trials,
                retained_source_cancellation=native_source, reentrant_move=reentrant_move,
                negative_origin=negative_origin,
                passed=['toolkit transfers across outputs', 'logical drop coordinates at five densities',
                        'drag icon hit-test exclusion', 'source completion and icon teardown', 'desktop and escape cancellation',
                        'invalid pointer serial rejected' if registry_probe else 'no negative serial probe requested']), indent=2) + '\n')
            print(f'{pair} drag, drop, rejection and cleanup: PASS')
        except BaseException:
            try:
                (artifacts / 'failure.json').write_text(json.dumps(dict(windows=command('windows'),
                    drag=command('drag-state'), clients={title: process.poll()
                        for title, process in toolkit_clients.items()}), indent=2) + '\n')
            except (OSError, ValueError): pass
            raise
        finally:
            for process in reversed(clients):
                if process.poll() is None: process.terminate(); process.wait(timeout=5)
            if server.poll() is None: server.terminate(); server.wait(timeout=5)
            server.stdout.close(); control.close()


def run_matrix(compositor, client, artifacts, registry_probe, native_probe, pasteboard_server, pasteboard_probe,
               framed=False, negative_origin=False):
    cases = [(pair, dict(pair=pair)) for pair in ('gtk-gtk', 'gtk-native', 'native-gtk', 'native-native')]
    cases += [('same-client', dict(pair='native-native', same_client=True)),
              ('reentrant-source-move', dict(pair='native-native', reentrant_move=True)),
              ('gtk-rejected', dict(pair='gtk-native', reject_target=True)),
              ('native-rejected-move', dict(pair='native-native', reject_target=True, move=True))]
    cases += [(pair + '-files', dict(pair=pair, file_drag=True)) for pair in ('gtk-native', 'native-gtk')]
    cases += [('native-files-move', dict(pair='native-native', file_drag=True, move=True)),
              ('same-client-files-move', dict(pair='native-native', same_client=True, file_drag=True, move=True))]
    cases += [(pair + '-move', dict(pair=pair, move=True)) for pair in ('gtk-native', 'native-gtk')]
    cases += [(mode, dict(pair='native-native', protocol_mode=mode))
              for mode in ('no-fractional', 'no-viewporter', 'no-placement')]
    cases += [('local-actions', dict(pair='native-native', same_client=True, local_move=True)),
              ('external-actions', dict(pair='native-gtk', local_move=True)),
              ('legacy-source', dict(pair='native-native', legacy_source=True))]
    cases += [('uri-' + kind, dict(pair='gtk-native', invalid_files=kind))
              for kind in ('remote-host', 'web-uri', 'malformed', 'nul')]
    cases += [('delayed-mixed', dict(pair='native-native', file_drag=True, delayed_drop=True))]
    for index, (name, configuration) in enumerate(cases):
        run(compositor, client, artifacts / name, registry_probe=registry_probe if index == 0 else None,
            native_probe=native_probe, pasteboard_server=pasteboard_server, pasteboard_probe=pasteboard_probe,
            framed=framed, negative_origin=negative_origin,
            **configuration)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--compositor', required=True)
    parser.add_argument('--client', required=True)
    parser.add_argument('--registry-probe')
    parser.add_argument('--native-probe')
    parser.add_argument('--pair', choices=['gtk-gtk', 'gtk-native', 'native-gtk', 'native-native'], default='gtk-gtk')
    parser.add_argument('--reject-target', action='store_true')
    parser.add_argument('--same-client', action='store_true')
    parser.add_argument('--file-drag', action='store_true')
    parser.add_argument('--move', action='store_true')
    parser.add_argument('--local-move', action='store_true')
    parser.add_argument('--legacy-source', action='store_true')
    parser.add_argument('--pasteboard-server')
    parser.add_argument('--pasteboard-probe')
    parser.add_argument('--protocol-mode', choices=['native', 'no-fractional', 'no-viewporter', 'no-placement'], default='native')
    parser.add_argument('--matrix', action='store_true')
    parser.add_argument('--repeat', type=int, default=1)
    parser.add_argument('--invalid-files', choices=['remote-host', 'web-uri', 'malformed', 'nul'])
    parser.add_argument('--delayed-drop', action='store_true')
    parser.add_argument('--reentrant-move', action='store_true')
    parser.add_argument('--framed', action='store_true', help='Require native server frames for the GNUstep drag participants')
    parser.add_argument('--negative-origin', action='store_true')
    parser.add_argument('--artifacts', type=Path, required=True)
    args = parser.parse_args()
    arguments = vars(args)
    if arguments.pop('matrix'):
        run_matrix(**{key: arguments[key] for key in ('compositor', 'client', 'artifacts', 'registry_probe',
            'native_probe', 'pasteboard_server', 'pasteboard_probe', 'framed', 'negative_origin')})
    else: run(**arguments)
