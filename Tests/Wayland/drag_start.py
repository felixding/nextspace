"""Pick a drag target when the pointer stops during the source's began callback."""
import json
import subprocess
from pathlib import Path
from gnustep import headless_session, pasteboard_storage, process_runtime
from integration import until, read_json_lines


def run(compositor, probe, pasteboard_server, pasteboard_probe, artifacts):
    artifacts.mkdir(parents=True)
    cases = []
    for same_client in (False, True):
        root = artifacts / ('same-client' if same_client else 'cross-client')
        root.mkdir()
        clients = []
        with headless_session(compositor, root / 'native') as (env, command), \
                pasteboard_storage(pasteboard_server, pasteboard_probe, env, root):
            def events(name, kind):
                return [e for e in read_json_lines(root / (name + '.log'), '{') if e['event'] == kind]

            def window(title):
                assert all(p.poll() is None for p in clients), 'A drag participant exited'
                return next((w for w in command('windows') if w['title'] == title and w['visible']), None)
            try:
                for source in ((True,) if same_client else (True, False)):
                    name = 'source' if source else 'target'
                    with (root / (name + '.log')).open('w') as log, (root / (name + '.stderr')).open('w') as error:
                        clients.append(subprocess.Popen([str(probe), '-GSBackend', 'libgnustep-wayland',
                            '-GSTheme', 'NextSpace', '-DragSource', 'YES' if source else 'NO',
                            '-SameClient', 'YES' if same_client else 'NO', '-ColorDrag', 'YES',
                            '-GenericDrag', 'YES', '-DragBeginDelay', '.5'], env=env, stdout=log, stderr=error))
                until(lambda: window('NativeDragSource') and window('NativeDragTarget'), 'drag participants')
                receiver = 'source' if same_client else 'target'
                for density in (120, 150, 180, 210, 240):
                    outputs = command('outputs')
                    for output, scale in zip(outputs, (120, density)):
                        assert command(f"test-scale {output['name']} {scale} 10000")['ok']
                        assert command('confirm')['ok']
                    outputs = command('outputs')
                    for title, output in zip(('NativeDragSource', 'NativeDragTarget'), outputs):
                        w = window(title)
                        assert command(f"move {w['id']} {output['x'] + 80} {output['y'] + 80}")['ok']
                    target = until(lambda: (w if (w := window('NativeDragTarget'))['preferred_scale'] == density else None), 'target density')
                    source = window('NativeDragSource')
                    began, dropped, ended = len(events('source', 'drag-begin')), len(events(receiver, 'drop')), len(events('source', 'drag-end'))
                    assert command(f"pointer {source['x'] + 50} {source['y'] + 100}")['ok']
                    assert command('button 272 1')['ok']
                    until(lambda: len(events('source', 'drag-begin')) > began, 'source began callback')
                    early = command('drag-state')
                    assert not early['active'], ('The fixture missed the delayed callback', early)
                    assert command(f"pointer {target['x'] + 70} {target['y'] + 100}")['ok']
                    # No additional motion is sent before negotiation and drop.
                    def accepted():
                        d = command('drag-state')
                        return d if d['active'] and d['target'] == target['id'] and d['action'] == 1 else None
                    negotiated = until(accepted, 'stationary pointer enters the target at drag start')
                    assert command('button 272 0')['ok']
                    drop = until(lambda: (e[-1] if len(e := events(receiver, 'drop')) > dropped else None), 'real color drop')
                    completion = until(lambda: (e[-1] if len(e := events('source', 'drag-end')) > ended else None), 'source completes')
                    assert completion['action'] == 1 and drop['local'] == same_client
                    assert max(abs(a-b) for a,b in zip(drop['rgba'], (.2,.4,.6,.5))) < .00001
                    until(lambda: not command('drag-state')['active'], 'drag reaped')
                    cases.append(dict(same_client=same_client, density=density, early=early,
                        negotiated=negotiated, drop=drop, completion=completion))
                (root / 'actors.json').write_text(json.dumps([process_runtime(p.pid) for p in clients], indent=2) + '\n')
            except BaseException:
                (root / 'failure.json').write_text(json.dumps(dict(windows=command('windows'),
                    drag=command('drag-state'), completed_cases=cases), indent=2) + '\n')
                raise
            finally:
                command('button 272 0')
                for process in clients:
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=5)
    result = dict(passed=True, cases=cases, delayed_source_callback_seconds=.5,
        stationary_pointer_targeting=True, all_processes_reaped=True, full_plan_complete=False)
    (artifacts / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Drag start: ten stationary-pointer color drops across clients and five densities PASS.')
    return result
