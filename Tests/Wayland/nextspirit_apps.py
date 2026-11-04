#!/usr/bin/env python3
"""Check NeXTSpirit logos in the actual Terminal and Preferences Info panels."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from nextspirit_art import NextSpiritArtwork
from artwork_reference import assert_svg_representations
from application_artwork import representations
from folder_artwork import compare_icon
from gnustep import headless_session, pasteboard_storage, process_runtime, capture_process_failure
from integration import until


def run(compositor, terminal, preferences, probe, density_probe, pasteboard_server,
        pasteboard_probe, pack, artifacts, theme=Path('NextSpace')):
    artifacts.mkdir(parents=True)
    art = NextSpiritArtwork(pack)
    applications = dict(Terminal=terminal, Preferences=preferences)
    resources, images = {}, {}
    for name, application in applications.items():
        for filename in art.entries[name]['targets'][name.lower()]:
            path = application.parent/'Resources'/filename
            directory = artifacts/'resources'/name/Path(filename).parent
            directory.mkdir(parents=True, exist_ok=True)
            assert_svg_representations(art, name, path, (48, 48))
            frames, metadata = representations(density_probe, path, directory)
            resources[name+'/'+filename] = dict(source=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), metadata=metadata)
            images.setdefault(name, frames)
    assert len(resources) == 3
    cases = []
    with headless_session(compositor, artifacts/'native', terminal.parent.parent) as (env, command):
        with pasteboard_storage(pasteboard_server, pasteboard_probe, env, artifacts/'native') as storage:
            for name, application in applications.items():
                directory = artifacts/name
                directory.mkdir()
                arguments = [str(application), '-GSBackend', 'libgnustep-wayland', '-GSTheme', str(theme), '-NSUseRunningCopy', 'NO']
                if name == 'Terminal':
                    arguments.extend(['-Shell', '/bin/cat'])
                (directory/'command.json').write_text(json.dumps(arguments, indent=2)+'\n')
                with (directory/'application.log').open('w') as log:
                    app = subprocess.Popen(arguments, env=env, stdout=log, stderr=log)
                children = []
                try:
                    def started():
                        assert app.poll() is None, (directory/'application.log').read_text()[-8000:]
                        return any(w['pid'] == app.pid and w['width'] > 300 for w in command('windows'))
                    until(started, name+' starts natively', timeout=30)
                    def query(target):
                        result = subprocess.run([str(probe), '--application-logo', name], env=env,
                            text=True, capture_output=True, timeout=15)
                        (target/'query.log').write_text(result.stdout+result.stderr)
                        assert result.returncode == 0, result.stderr
                        return json.loads(result.stdout)
                    initial = query(directory)
                    target = command('outputs')[0]
                    for at, density in enumerate((120, 150, 180, 210, 240)):
                        sample = directory/str(density)
                        sample.mkdir()
                        assert command(f"test-scale {target['name']} {density} 10000")['ok'] and command('confirm')['ok']
                        def window():
                            return next(w for w in command('windows') if w['pid'] == app.pid and w['client_id'] == initial['window'])
                        assert command(f"move {window()['id']} {target['x']+10} {target['y']+10}")['ok']
                        if name == 'Preferences':
                            clock = next(w for w in command('windows') if w['pid'] == app.pid and w['client_id'] == initial['clock_window'])
                            assert command(f"move {clock['id']} {target['x']+200} {target['y']+10}")['ok']
                        path = artifacts/'native/captures'/f"window-{initial['window']}-{density}.png"
                        path.unlink(missing_ok=True)
                        state = query(sample)
                        assert state['logical'] == [48, 48] and state['representations'] == [[48*d//120]*2 for d in (120,150,180,210,240)]
                        def captured():
                            assert app.poll() is None
                            current = window()
                            if current['preferred_scale'] != density or current['buffer_width'] != (current['width']*density+60)//120:
                                return False
                            try:
                                with Image.open(path) as image:
                                    actual = image.convert('RGBA')
                            except OSError:
                                return False
                            return (current, actual) if actual.size == (current['buffer_width'], current['buffer_height']) else False
                        w, actual = until(captured, name+' Info panel density')
                        assert not w['legacy']
                        actual.save(sample/'window.png')
                        installed = application.parent/'Resources'/art.entries[name]['targets'][name.lower()][0]
                        if state['resource']:
                            assert hashlib.sha256(Path(state['resource']).read_bytes()).hexdigest() == hashlib.sha256(installed.read_bytes()).hexdigest()
                        view = dict(state, name=name, selected=False, dimmed=False, resource=str(installed))
                        comparison = compare_icon(art, images[name][at], name, view, w, actual, density, sample/'logo')
                        clock_state = None
                        if name == 'Preferences':
                            assert state['clock_class'] == 'NXTClockView' and state['clock_alive'] and state['clock_logical'] == [64,64]
                            def clock_ready():
                                current = next(w for w in command('windows') if w['pid'] == app.pid and w['client_id'] == state['clock_window'])
                                pixels = (64*density+60)//120
                                return current if current['preferred_scale'] == density and (
                                    current['buffer_width'], current['buffer_height']) == (pixels, pixels) else False
                            clock_state = until(clock_ready, 'live Preferences clock follows density')
                            assert clock_state['width'] == clock_state['height'] == 64
                        cases.append(dict(name=name, scale=density, state=state, window=w, comparison=comparison, clock=clock_state))
                    (directory/'runtime.json').write_text(json.dumps(process_runtime(app.pid), indent=2)+'\n')
                    (directory/'maps.txt').write_text(Path(f'/proc/{app.pid}/maps').read_text())
                    if name == 'Terminal':
                        identifiers = set()
                        for task in Path(f'/proc/{app.pid}/task').iterdir():
                            identifiers.update(map(int, (task/'children').read_text().split()))
                        children = [process_runtime(pid) for pid in sorted(identifiers)]
                        assert len(children) == 1 and Path(children[0]['executable']).name == 'cat'
                        (directory/'children.json').write_text(json.dumps(children, indent=2)+'\n')
                except BaseException:
                    capture_process_failure(app, directory, 'failure-application')
                    raise
                finally:
                    if app.poll() is None:
                        app.terminate()
                        app.wait(timeout=5)
                    until(lambda: all(not Path('/proc',str(child['pid'])).exists() for child in children), 'owned Terminal PTY child exits')
        assert storage.poll() is not None
    result = dict(complete=True, cases=cases, resources=resources, native_image_comparisons=10,
        resource_representation_selections=15, preferences_live_clock_preserved=True,
        terminal_animation_geometry_preserved=True, terminal_animation_strips_hidpi_qualified=False,
        owned_pasteboard_pid=storage.pid, owned_pasteboard_reaped=True,
        owned_terminal_child_reaped=True,
        personal_preview_only=True, unrestricted_redistribution_qualified=False,
        full_current_source_build=False, full_package_lifecycle_qualified=False, full_plan_complete=False)
    (artifacts/'results.json').write_text(json.dumps(result, indent=2)+'\n')
    print('NeXTSpirit application logos: 15 resource selections, 10 actual Info-panel comparisons and live clock geometry PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    paths = ('compositor','terminal','preferences','probe','density-probe','pasteboard-server','pasteboard-probe','pack','artifacts')
    for name in paths:
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--theme', type=Path, default=Path('NextSpace'))
    args = parser.parse_args()
    run(*(getattr(args, name.replace('-','_')).resolve() for name in paths), theme=args.theme)
