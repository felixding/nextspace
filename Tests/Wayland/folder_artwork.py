#!/usr/bin/env python3
"""Qualify folder resources and production hover states in Workspace's Icon viewer."""
import argparse
import array
import hashlib
import json
import math
import os
from pathlib import Path
import plistlib
import shutil
import socket
import subprocess
import sys
import tempfile
from PIL import Image, ImageChops, ImageFilter
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'Packaging/Sources'))
from vector_art import Artwork, backing_size
from artwork_reference import assert_svg_representations
from application_artwork import placed_reference, representations, image_view_clip
from gnustep import headless_session, pasteboard_storage, process_runtime, capture_process_failure
from integration import until, read_json_lines


def compare_icon(art, reference, name, view, window, actual, density, directory, background=None, scan_aligned=False, resource=None, selected=False):
    logical = tuple(map(float, art.symbols[name].get('data-logical-size', '48 48').split()))
    assert tuple(view['logical']) == logical and view['selected'] == selected and not view['dimmed']
    assert not selected or background is not None, 'Selected icons require an independently rendered backdrop'
    assert_svg_representations(art, name, resource or Path(view['resource']), logical)
    assert view['representations'] == [[backing_size(points,d) for points in logical]
        for d in (120, 150, 180, 210, 240)]
    x, y, width, height = view['base']
    factor = density / 120
    if scan_aligned:
        assert all(math.isclose(value*factor,backing_size(points,density),abs_tol=1e-5)
            for value,points in zip((width,height),logical)), 'Image-cell destination must match its backing pixels'
    else:
        assert math.isclose(width, logical[0], abs_tol=1e-8) and math.isclose(height, logical[1], abs_tol=1e-8)
    origin = x*factor, (window['height']-y-height)*factor
    left, top = map(math.floor, origin)
    size = math.ceil(width*factor+origin[0]-left), math.ceil(height*factor+origin[1]-top)
    vx, vy, vw, vh = view['visible']
    box = reference.getchannel('A').getbbox()
    assert box is not None
    ink = (box[0]*width*factor/reference.width,box[1]*height*factor/reference.height,
        box[2]*width*factor/reference.width,box[3]*height*factor/reference.height)
    ink_fits = (ink[0] >= (vx-x)*factor-.00001 and ink[2] <= (vx+vw-x)*factor+.00001 and
        ink[1] >= (y+height-vy-vh)*factor-.00001 and ink[3] <= (y+height-vy)*factor+.00001)
    if not scan_aligned:assert ink_fits
    directory.mkdir()
    crop = actual.crop((left, top, left+size[0], top+size[1]))
    crop.save(directory / 'actual.png')
    # NSImage clips the destination as well as its enclosing view.
    destination = origin[0], origin[1], origin[0]+width*factor, origin[1]+height*factor
    visible_clip = (vx*factor,(window['height']-vy-vh)*factor,
        (vx+vw)*factor,(window['height']-vy)*factor)
    if scan_aligned and density % 120 and all(value==math.floor(value) for value in (vx,vy,vw,vh)):
        # NSImageCell's integral view clip uses CairoGState's native pixel
        # rectangle, independently of its center-scanned image destination.
        visible_clip = image_view_clip((vx,vy,vw,vh),window['height'],density)
    clip_left = max(destination[0],visible_clip[0])-left
    clip_top = max(destination[1],visible_clip[1])-top
    clip_right = min(destination[2],visible_clip[2])-left
    clip_bottom = min(destination[3],visible_clip[3])-top
    clip = clip_left, clip_top, clip_right-clip_left, clip_bottom-clip_top
    placement = dict(size=(width*factor, height*factor), pad=True, clip=clip)
    if view.get('native_composite', view.get('pixel_aligned_destination_clip', False)):
        # Keep compositeToPoint's device scale and intermediate image group.
        # Flattening them can change alpha rounding at fractional positions.
        placement['native_rep_size'] = logical
    point = origin[0]-left, origin[1]-top
    backdrop = background.crop((left, top, left+size[0], top+size[1])) if background is not None else Image.new('RGBA', size, crop.getpixel((0, 0)))
    expected = placed_reference(reference, point, backdrop,
        directory, density, **placement)
    expected.save(directory / 'expected.png')
    mask_dir = directory / 'mask'
    mask_dir.mkdir()
    ink = placed_reference(reference, point, Image.new('RGBA', size), mask_dir, density,
        **placement).getchannel('A')
    mask = ink.point(lambda value: 255 if value else 0).filter(ImageFilter.MaxFilter(3))
    mask.save(directory / 'mask.png')
    difference = Image.composite(ImageChops.difference(crop, expected), Image.new('RGBA', size), mask)
    maximum = max(hi for lo, hi in difference.getextrema())
    assert maximum <= 1, (density, name, maximum)
    return dict(state=name, key=view['name'], maximum_channel_difference=maximum,
        symbol_and_halo_pixels=sum(mask.histogram()[1:]), halo_pixels=1,
        source_ink_fits_visible_rect=ink_fits,scan_aligned_destination=scan_aligned)


def run(compositor, application, probe, density_probe, desktopkit_resources, theme,
        pasteboard_server, pasteboard_probe, artifacts, artwork=None, drag_probe=None, workspace_artwork=None, root_artwork=False):
    artifacts.mkdir(parents=True)
    source = Path(__file__).resolve().parents[2] / 'Applications/Artwork/Folder.svg'
    art = artwork or Artwork(source)
    if artwork is not None:
        source = artwork.source
    names = ('closed', 'bad', 'open') if 'open' in art.symbols else ('closed', 'bad')
    directories = dict(workspace=application.parent/'Resources', desktopkit=desktopkit_resources,
        theme=theme/'Resources/ThemeImages')
    records, images = {}, {}
    for name in names:
        for component, directory in directories.items():
            for filename in art.symbols[name].get('data-'+component+'-files', '').split():
                path = directory / filename
                case = artifacts / 'resources' / component / path.stem
                case.mkdir(parents=True)
                assert_svg_representations(art, name, path, (48, 48))
                frames, metadata = representations(density_probe, path, case, (48, 48))
                records[component+'/'+filename] = dict(state=name, source=str(path),
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest(), metadata=metadata)
                if component == 'workspace' and filename in ('common_Folder.tiff', 'badFolder.tiff', 'openFolder.tiff'):
                    images[name] = frames
    assert len(records) == 17+('open' in names) and set(images) == set(names)
    # Host-shared filesystems can report chmod(0) directories as readable.
    scratch = tempfile.TemporaryDirectory(prefix='nextspace-folder-')
    content = Path(scratch.name) / 'content'
    content.mkdir()
    closed = content / 'ClosedFolder'
    closed.mkdir()
    unavailable = content / 'UnavailableFolder'
    unavailable.mkdir()
    unavailable.chmod(0)
    fixture = dict(path=str(unavailable), mode=unavailable.stat().st_mode & 0o777,
        owner=unavailable.stat().st_uid)
    (artifacts/'permission-fixture.json').write_text(json.dumps(fixture, indent=2)+'\n')
    drag_source = artifacts / 'folder日本語.txt'
    drag_bytes = b'Native folder hover fixture\n'
    drag_source.write_bytes(drag_bytes)
    broker, broker_child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    profile = Path.home() / 'Library/Preferences/.NextSpace/WaylandDisplays.plist'
    previous_profile = profile.read_bytes() if profile.exists() else None
    try:
        with headless_session(compositor, artifacts/'native', application.parent.parent,
                shell_broker=broker_child) as (env, command):
            broker_child.close()
            env.pop('NEXTSPACE_SHELL_SOCKET', None)
            neighbors = Path(scratch.name)/'users/Neighbors'
            neighbors.mkdir(parents=True)
            # Exercise the real users-directory role without touching /Users.
            if workspace_artwork is not None:
                config = Path(env['GNUSTEP_CONFIG_FILE'])
                with config.open('a') as stream:
                    stream.write(f'\nGNUSTEP_SYSTEM_USERS_DIR={neighbors}\n')
                (artifacts/'native/GNUstep.conf').write_bytes(config.read_bytes())
            with pasteboard_storage(pasteboard_server, pasteboard_probe, env, artifacts/'native') as storage:
                dock = artifacts / 'dock.plist'
                dock.write_bytes(plistlib.dumps(dict(Applications=[dict(Name='Workspace.GNUstep',
                    Command='', Position='0,0', Lock='Yes', AutoLaunch='Yes')], Collapsed='No')))
                saved = subprocess.run([str(probe), '--write-dock', str(dock)], env=env,
                    text=True, capture_output=True, check=True, timeout=15)
                assert json.loads(saved.stdout)['saved']
                endpoint, client = socket.socketpair()
                broker.sendmsg([b'C'], [(socket.SOL_SOCKET, socket.SCM_RIGHTS,
                    array.array('i', [endpoint.fileno()]))])
                endpoint.close()
                prefix = [shutil.which('setpriv'), '--bounding-set=-dac_override,-dac_read_search', '--'] if os.geteuid() == 0 else []
                assert not prefix or prefix[0]
                readable = subprocess.run([*prefix, sys.executable, '-c',
                    'import os,sys; sys.exit(os.access(sys.argv[1], os.R_OK))',
                    str(unavailable)], check=False)
                assert readable.returncode == 0, 'Unavailable folder fixture is readable to Workspace'
                fixture['readable_to_workspace'] = False
                (artifacts/'permission-fixture.json').write_text(json.dumps(fixture, indent=2)+'\n')
                arguments = [*prefix, str(application), '-GSBackend', 'libgnustep-wayland',
                    '-GSTheme', str(theme), '-NSUseRunningCopy', 'NO', '--nextspace-shell-fd', str(client.fileno())]
                (artifacts/'workspace-command.json').write_text(json.dumps(arguments, indent=2)+'\n')
                with (artifacts/'workspace.log').open('w') as log:
                    app = subprocess.Popen(arguments, env=env, pass_fds=[client.fileno()], stdout=log, stderr=log)
                client.close()
                drag_app = None
                try:
                    def ready():
                        assert app.poll() is None, (artifacts/'workspace.log').read_text()[-8000:]
                        return 'Workspace is ready' in (artifacts/'workspace.log').read_text()
                    until(ready, 'Workspace ready', timeout=30)
                    status = Path(f'/proc/{app.pid}/status').read_text()
                    (artifacts/'workspace-status.txt').write_text(status)
                    for key in ('CapEff:', 'CapPrm:'):
                        capabilities = int(next(line.split()[1] for line in status.splitlines() if line.startswith(key)), 16)
                        assert capabilities & 6 == 0, 'Permission fixture retained filesystem override capabilities'
                    (artifacts/'workspace-runtime.json').write_text(json.dumps(process_runtime(app.pid), indent=2)+'\n')
                    def query(directory, phase='closed'):
                        result = subprocess.run([str(probe), '--workspace-folders', str(content.resolve()),
                            phase], env=env, text=True, capture_output=True, timeout=15)
                        (directory/'query.log').write_text(result.stdout+result.stderr)
                        assert result.returncode == 0, result.stderr
                        return json.loads(result.stdout)
                    initial = artifacts / 'initial'
                    initial.mkdir()
                    state = until(lambda: (lambda r: r if len(r['images']) == 2 else False)(query(initial)), 'actual folder icons')
                    assert {v['name'] for v in state['images']} == {'ClosedFolder', 'UnavailableFolder'}
                    target, cases = command('outputs')[0], []
                    phases = ('closed', 'open', 'restored', 'drop-open', 'dropped') if 'open' in names else ('closed',)
                    drags, drops = [], []
                    if 'open' in names:
                        drag_probe = drag_probe or probe.with_name('DragProbe')
                        assert drag_probe.is_file(), 'Open-folder qualification requires the native DragProbe'
                        with (artifacts/'drag-source.log').open('w') as log, (artifacts/'drag-source.stderr').open('w') as errors:
                            drag_app = subprocess.Popen([str(drag_probe), '-GSBackend', 'libgnustep-wayland',
                                '-GSTheme', str(theme), '-GSSuppressAppIcon', 'YES', '-DragSource', 'YES',
                                '-DragFile', str(drag_source.resolve())], env=env, stdout=log, stderr=errors)
                        def find_source_window():
                            assert drag_app.poll() is None, (artifacts/'drag-source.stderr').read_text()
                            return next((w for w in command('windows') if w['pid'] == drag_app.pid and
                                w['title'] == 'NativeDragSource'), None)
                        source_window = until(find_source_window, 'native file-drag source')
                        other = next(o for o in command('outputs') if o['name'] != target['name'])
                        assert command(f"move {source_window['id']} {other['x']+400} {other['y']+300}")['ok']
                        source_window = until(lambda: (lambda w: w if w['x'] == other['x']+400 and w['y'] == other['y']+300 else False)(
                            next(w for w in command('windows') if w['id'] == source_window['id'])), 'drag source placement')
                        (artifacts/'drag-runtime.json').write_text(json.dumps(process_runtime(drag_app.pid), indent=2)+'\n')
                    def start_file_drag(directory, snapshot, w):
                        ended = len([v for v in read_json_lines(artifacts/'drag-source.log') if v['event'] == 'drag-end'])
                        began = len([v for v in read_json_lines(artifacts/'drag-source.log') if v['event'] == 'drag-begin'])
                        assert command(f"focus {source_window['id']}")['ok']
                        assert command(f"pointer {source_window['x']+50} {source_window['y']+100}")['ok']
                        hit = command(f"hit {source_window['x']+50} {source_window['y']+100}")
                        (directory/'source-start.json').write_text(json.dumps(dict(window=source_window, hit=hit), indent=2)+'\n')
                        assert hit['id'] == source_window['id']
                        assert command('button 272 1')['ok']
                        until(lambda: len([v for v in read_json_lines(artifacts/'drag-source.log') if v['event'] == 'drag-begin']) > began,
                            'native source receives the button press')
                        until(lambda: command('drag-state')['active'], 'native file drag starts')
                        view = next(v for v in snapshot['images'] if v['name'] == 'ClosedFolder')
                        x, y, width, height = view['base']
                        assert command(f"pointer {int(w['x']+x+width/2)} {int(w['y']+w['height']-y-height/2)}")['ok']
                        expected = ((33*density+60)//120, (31*density+60)//120)
                        def accepted():
                            value = command('drag-state')
                            return value if value['target'] == w['id'] and value['action'] == 1 and (
                                value.get('buffer_width'), value.get('buffer_height')) == expected else False
                        hover = until(accepted, 'Workspace accepts the native file drag at the target density')
                        assert hover['samples'] == [0xffff0000]*4
                        return ended, hover
                    for at, density in enumerate((120, 150, 180, 210, 240)):
                        scale_dir = artifacts / str(density)
                        scale_dir.mkdir()
                        assert command(f"test-scale {target['name']} {density} 10000")['ok'] and command('confirm')['ok']
                        def window():
                            return next(w for w in command('windows') if w['pid'] == app.pid and w['client_id'] == state['window'])
                        assert command(f"move {window()['id']} {target['x']+10} {target['y']+10}")['ok']
                        for phase in phases:
                            directory = scale_dir if phase == 'closed' else scale_dir / phase
                            if phase != 'closed':
                                directory.mkdir()
                            path = artifacts/'native/captures'/f"window-{state['window']}-{density}.png"
                            path.unlink(missing_ok=True)
                            if phase in ('open', 'drop-open'):
                                ended, hover = start_file_drag(directory, state, window())
                            elif phase == 'restored':
                                assert command(f"pointer {other['x']+1100} {other['y']+900}")['ok']
                                until(lambda: command('drag-state')['target'] == 0, 'file drag leaves Workspace')
                                assert command('key 1 1')['ok'] and command('key 1 0')['ok']
                                until(lambda: not command('drag-state')['active'], 'file drag cancels')
                                assert command('button 272 0')['ok']
                                endings = until(lambda: (lambda e: e if len(e) > ended else False)([
                                    v for v in read_json_lines(artifacts/'drag-source.log') if v['event'] == 'drag-end']), 'drag source observes cancellation')
                                assert endings[-1]['action'] == 0
                                drags.append(dict(scale=density, hover=hover, end=endings[-1]))
                            elif phase == 'dropped':
                                assert command('button 272 0')['ok']
                                endings = until(lambda: (lambda e: e if len(e) > ended else False)([
                                    v for v in read_json_lines(artifacts/'drag-source.log') if v['event'] == 'drag-end']), 'source completes the file drop')
                                assert endings[-1]['action'] == 1
                                copied = closed / drag_source.name
                                until(lambda: copied.is_file() and copied.read_bytes() == drag_bytes, 'Workspace copies the dropped Unicode file')
                                assert drag_source.read_bytes() == drag_bytes
                                (directory/'copied-file.bin').write_bytes(copied.read_bytes())
                                drops.append(dict(scale=density, hover=hover, end=endings[-1],
                                    target=str(copied), sha256=hashlib.sha256(copied.read_bytes()).hexdigest()))
                            path.unlink(missing_ok=True)
                            def transitioned():
                                value = query(directory, phase)
                                image = next(v for v in value['images'] if v['name'] == 'ClosedFolder')
                                return value if (Path(image['resource']).name == 'openFolder.tiff') == (phase in ('open', 'drop-open')) else False
                            state = until(transitioned, 'folder hover image follows the native drag')
                            assert phase not in ('open', 'drop-open') or state['drag_mask'] != 0
                            def capture():
                                assert app.poll() is None
                                w = window()
                                if w['preferred_scale'] != density or w['buffer_width'] != (w['width']*density+60)//120:
                                    return False
                                try:
                                    with Image.open(path) as image:
                                        actual = image.convert('RGBA')
                                except OSError:
                                    return False
                                return (w, actual) if actual.size == (w['buffer_width'], w['buffer_height']) else False
                            w, actual = until(capture, 'native Workspace folder buffer')
                            assert not w['legacy']
                            actual.save(directory/'window.png')
                            comparisons = []
                            for view in state['images']:
                                if view['name'] == 'UnavailableFolder':
                                    if phase != 'closed':
                                        continue
                                    name = 'bad'
                                else:
                                    name = 'open' if phase in ('open', 'drop-open') else 'closed'
                                comparisons.append(compare_icon(art, images[name][at], name, view, w,
                                    actual, density, directory/name))
                            cases.append(dict(scale=density, phase=phase, state=state, window=w, comparisons=comparisons))
                            if phase == 'dropped':
                                copied.unlink()
                    assert drag_source.read_bytes() == drag_bytes and not any(closed.iterdir())
                    large_icons = None
                    if workspace_artwork is not None:
                        from nextspirit_workspace import run as workspace_icons
                        large_icons = workspace_icons(command, env, application, probe, density_probe,
                            workspace_artwork, desktopkit_resources, theme, artifacts/'large-icons')
                    from permissions_artwork import run as permission_artwork
                    permissions = permission_artwork(command, env, probe, density_probe, app.pid, artifacts / "permissions")
                    embedded = None
                    if workspace_artwork is not None:
                        from embedded_button_artwork import run as embedded_buttons
                        embedded = embedded_buttons(command, env, application, probe, density_probe,
                            workspace_artwork, app.pid, artifacts/'embedded-buttons')
                    from operation_artwork import run as operation_artwork
                    operations = operation_artwork(command, env, application, probe, density_probe,
                        app.pid, artifacts/'background-operations')
                    from preference_artwork import run as preference_artwork
                    preference_images = preference_artwork(command, env, application, probe, density_probe,
                        app.pid, artifacts/'preference-images')
                    directory_states = None
                    if workspace_artwork is not None:
                        from directory_artwork import run as directory_artwork
                        assert drag_app is not None
                        directory_states = directory_artwork(command, env, application, probe, density_probe,
                            workspace_artwork, app.pid, artifacts/'directory-states', neighbors,
                            source_window, artifacts/'drag-source.log', drag_source, desktopkit_resources)
                    from selection_artwork import run as selection_artwork
                    selection = selection_artwork(command,env,application,probe,density_probe,app.pid,
                        artifacts/'multiple-selection')
                    from document_icons import run as document_icons
                    documents = document_icons(command,env,application,probe,density_probe,app.pid,
                        desktopkit_resources,theme,artifacts/'documents',Path(scratch.name)/'documents')
                    root_icon = None
                    if root_artwork:
                        from root_artwork import run as root_icon_artwork
                        root_icon = root_icon_artwork(command, env, probe, density_probe,
                            desktopkit_resources, theme, artifacts/'root-icon')
                    (artifacts/'workspace-runtime.json').write_text(json.dumps(process_runtime(app.pid), indent=2)+'\n')
                    (artifacts/'workspace-maps.txt').write_text(Path(f'/proc/{app.pid}/maps').read_text())
                    if drag_app is not None:
                        (artifacts/'drag-runtime.json').write_text(json.dumps(process_runtime(drag_app.pid), indent=2)+'\n')
                        tools = {}
                        for name in ('FileMover', 'Sizer'):
                            tool = application.parent/'Resources'/(name+'.tool')
                            linkage = subprocess.run(['ldd', str(tool)], env=env, capture_output=True, text=True, check=True)
                            tools[name] = dict(path=str(tool), sha256=hashlib.sha256(tool.read_bytes()).hexdigest(),
                                linked_libraries=linkage.stdout, linkage_observed=True, child_maps_captured=False)
                        (artifacts/'file-operation-tools.json').write_text(json.dumps(tools, indent=2)+'\n')
                    result = dict(complete=True, cases=cases, resources=records, resource_paths=len(records),
                        resource_representation_selections=len(records)*5,
                        native_image_comparisons=sum(len(c['comparisons']) for c in cases),
                        actual_permission_failure=True, hover_handlers_tested='open' in names,
                        drag_transport_tested='open' in names, file_drop_tested='open' in names,
                        copied_file_drags=drops,
                        cancelled_file_drags=drags, drag_source_unchanged=True,
                        large_icons=large_icons, permissions_artwork=permissions, embedded_button_artwork=embedded,
                        operation_artwork=operations, preference_artwork=preference_images,
                        directory_artwork=directory_states,
                        root_icon=root_icon,selection_artwork=selection,document_icons=documents,
                        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), full_plan_complete=False)
                finally:
                    failed = sys.exc_info()[0] is not None
                    if drag_app is not None and drag_app.poll() is None:
                        command('key 1 1')
                        command('key 1 0')
                        command('button 272 0')
                        drag_app.terminate()
                        drag_app.wait(timeout=5)
                    if app.poll() is None:
                        app.terminate()
                        try:
                            app.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            capture_process_failure(app, artifacts, 'workspace-cleanup-stall')
                            app.kill()
                            app.wait(timeout=5)
                            if not failed:
                                raise AssertionError('Workspace cleanup stalled')
            assert storage.poll() is not None
            result.update(owned_pasteboard_pid=storage.pid, owned_pasteboard_reaped=True,
                workspace_returncode=app.returncode)
            (artifacts/'results.json').write_text(json.dumps(result, indent=2)+'\n')
            print(f"Workspace folders: {result['resource_representation_selections']} resource selections and "
                f"{result['native_image_comparisons']} actual Icon-view image comparisons PASS")
    finally:
        broker.close()
        broker_child.close()
        unavailable.chmod(0o755)
        scratch.cleanup()
        if previous_profile is None:
            profile.unlink(missing_ok=True)
        else:
            profile.parent.mkdir(parents=True, exist_ok=True)
            profile.write_bytes(previous_profile)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    paths = ('compositor', 'application', 'probe', 'density-probe', 'desktopkit-resources', 'theme',
        'pasteboard-server', 'pasteboard-probe', 'artifacts')
    for name in paths:
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--nextspirit', type=Path, help='Verify personal-use NeXTSpirit resources against the complete source sets')
    parser.add_argument('--drag-probe', type=Path)
    parser.add_argument('--root-artwork', action='store_true', help='Also verify the original-style root computer')
    args = parser.parse_args()
    artwork = None
    if args.nextspirit:
        from nextspirit_art import NextSpiritFolders
        artwork = NextSpiritFolders(Path(__file__).resolve().parents[2]/'Applications/Artwork/Folder.svg', args.nextspirit)
    run(*(getattr(args, name.replace('-', '_')).resolve() for name in paths), artwork=artwork,
        drag_probe=args.drag_probe.resolve() if args.drag_probe else None, root_artwork=args.root_artwork)
