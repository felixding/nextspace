#!/usr/bin/env python3
"""Check NeXTSpirit directory, application and Recycler icons in real Workspace."""
import hashlib
import json
import plistlib
from pathlib import Path
import shutil
import subprocess
import uuid
from PIL import Image
from application_artwork import representations
from artwork_reference import assert_svg_representations
from folder_artwork import compare_icon
from integration import until


def run(command, env, application, probe, density_probe, art, desktopkit_resources, theme, artifacts):
    artifacts.mkdir()
    directories = dict(workspace=application.parent/'Resources', desktopkit=desktopkit_resources,
        theme=theme/'Resources/ThemeImages',
        inspectors=application.parent/'Resources/Inspectors.bundle/Resources/English.lproj')
    resources, images = {}, {}
    for name, entry in art.entries.items():
        for component, targets in entry['targets'].items():
            for target in targets:
                path = directories[component]/target
                sample = artifacts/'resources'/component/Path(target).with_suffix('')
                sample.mkdir(parents=True)
                assert_svg_representations(art, name, path, entry['logical'])
                frames, metadata = representations(density_probe, path, sample, entry['logical'])
                resources[component+'/'+target] = dict(name=name, source=str(path),
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest(), metadata=metadata)
                images.setdefault(name, frames)
    assert len(resources) == sum(len(targets) for entry in art.entries.values()
        for targets in entry['targets'].values())
    with Image.open(directories['theme']/'common_Tile.tiff') as source:
        assert source.n_frames == 11
        tiles = []
        for index in range(5):
            source.seek(index)
            tiles.append(source.convert('RGBA'))

    def query(mode, directory, *arguments):
        value = subprocess.run([str(probe), mode, *map(str, arguments)], env=env, capture_output=True, text=True, timeout=15)
        (directory/(mode[2:]+'.log')).write_text(value.stdout+value.stderr)
        assert value.returncode == 0, value.stderr
        return json.loads(value.stdout)

    initial = until(lambda: (lambda state: state if len(state['images']) == 1 else False)(
        query('--workspace-home', artifacts)), 'actual Home directory icon')
    application_directory = artifacts/'applications'
    application_names = {'Generic.'+extension for extension in ('app', 'debug', 'profile')}
    for name in application_names:
        resources_directory = application_directory/name/'Resources'
        resources_directory.mkdir(parents=True)
        (resources_directory/'Info-gnustep.plist').write_bytes(plistlib.dumps(dict(
            NSExecutable='Generic', NSPrincipalClass='NSApplication')))
    generic = until(lambda: (lambda state: state if {v['name'] for v in state['images']} == application_names else False)(
        query('--workspace-folders', artifacts, application_directory)), 'three application wrappers without custom icons')
    screen_directory = artifacts/'monitor-screens'
    screen_directory.mkdir()
    screen_names = {'Unknown.'+extension:'UnknownApplication' for extension in ('app','debug','profile')}
    for name in screen_names:
        (screen_directory/name).write_bytes(b'Not an application wrapper\n')
    tool = screen_directory/'NativeTool'
    shutil.copy2(shutil.which('true'),tool)
    tool.chmod(0o755)
    screen_names[tool.name] = 'UnixTool'
    bundle_directory=artifacts/'bundle-wrappers';bundle_directory.mkdir()
    bundle_names={'Wrapper.'+extension for extension in ('bundle','preferences','inspector','service')}
    for name in bundle_names:
        (bundle_directory/name).mkdir()
    screens = until(lambda: (lambda state: state if {v['name'] for v in state['images']} == set(screen_names) else False)(
        query('--workspace-folders', artifacts, screen_directory)), 'unknown application and executable file icons')
    bundles = until(lambda: (lambda state: state if {v['name'] for v in state['images']} == bundle_names else False)(
        query('--workspace-folders', artifacts, bundle_directory)), 'four visible bundle-wrapper icons')
    folder_arguments={'applications':application_directory,'monitor-screens':screen_directory,'bundles':bundle_directory}
    folder_phases=('home',*folder_arguments)
    recycler = query('--workspace-recycler', artifacts)
    owner = next(w['pid'] for w in command('windows') if w['client_id'] == recycler['window'] and w['title'] == 'Recycler')
    def current_window(state):
        return next(w for w in command('windows') if w['pid'] == owner and w['client_id'] == state['window'])
    storage = Path(recycler['storage'])
    assert storage.name == '.Recycler' and storage.is_dir()
    assert recycler['items_count'] == 0 and not any(p.name != '.recycler.db' for p in storage.iterdir())
    fixture = storage/('nextspirit-'+uuid.uuid4().hex+'-日本語.txt')
    payload = b'Owned NeXTSpirit Recycler state fixture\n'
    cases = []
    dock = current_window(recycler)
    target = next(output for output in command('outputs') if
        output['x'] <= dock['x']+32 < output['x']+output['width'] and
        output['y'] <= dock['y']+32 < output['y']+output['height'])
    try:
        for at, density in enumerate((120, 150, 180, 210, 240)):
            sample = artifacts/str(density)
            sample.mkdir()
            assert command(f"test-scale {target['name']} {density} 10000")['ok'] and command('confirm')['ok']
            for state in (initial, generic, screens, bundles):
                window = current_window(state)
                assert command(f"move {window['id']} {target['x']+10} {target['y']+10}")['ok']
            for phase in ('home', 'empty', 'full', 'restored', 'applications', 'monitor-screens', 'bundles'):
                directory = sample/phase
                directory.mkdir()
                if phase == 'full':
                    with fixture.open('xb') as stream:
                        stream.write(payload)
                elif phase == 'restored':
                    assert fixture.read_bytes() == payload
                    fixture.unlink()
                mode = '--workspace-home' if phase=='home' else ('--workspace-folders' if phase in folder_arguments else '--workspace-recycler')
                arguments = (folder_arguments[phase],) if phase in folder_arguments else ()
                def transitioned():
                    result = query(mode, directory, *arguments)
                    return result if phase in folder_phases or result['items_count'] == int(phase == 'full') else False
                state = until(transitioned, 'Recycler filesystem state and badge')
                if phase == 'home':
                    assert len(state['images']) == 1
                elif phase == 'applications':
                    assert {v['name'] for v in state['images']} == application_names
                elif phase == 'monitor-screens':
                    assert {v['name'] for v in state['images']} == set(screen_names)
                elif phase == 'bundles':
                    assert {v['name'] for v in state['images']} == bundle_names
                else:
                    view, name = state['image'], 'RecyclerFull' if phase == 'full' else 'RecyclerEmpty'
                    assert view['name'] == name and state['badge'] == ('1' if phase == 'full' else '')
                path = Path(env['NEXTSPACE_WAYLAND_CAPTURE_DIR'])/f"window-{state['window']}-{density}.png"
                path.unlink(missing_ok=True)
                state = query(mode, directory, *arguments)
                def captured():
                    window = current_window(state)
                    status = dict(window=window, path=str(path), exists=path.exists(), outputs=command('outputs'))
                    (directory/'capture-status.json').write_text(json.dumps(status, indent=2)+'\n')
                    if window['preferred_scale'] != density:
                        return False
                    expected = tuple((window[k]*density+60)//120 for k in ('width','height'))
                    try:
                        with Image.open(path) as source:
                            image = source.convert('RGBA')
                    except OSError:
                        return False
                    return (window, image) if image.size == expected == (window['buffer_width'],window['buffer_height']) else False
                window, actual = until(captured, 'native Workspace large-icon buffer')
                assert not window['legacy']
                actual.save(directory/'window.png')
                (directory/'case.json').write_text(json.dumps(dict(state=state, window=window), indent=2)+'\n')
                if phase == 'monitor-screens':
                    views = [(screen_names[view['name']],view) for view in state['images']]
                elif phase == 'bundles':
                    views = [('Bundle',view) for view in state['images']]
                elif phase in ('home','applications'):
                    name = 'Home' if phase == 'home' else 'DefaultApplication'
                    views = [(name,view) for view in state['images']]
                else:
                    views = [(state['image']['name'],state['image'])]
                comparisons = []
                for name, view in views:
                    installed = [record for record in resources.values() if record['name'] == name]
                    assert view['resource'] and any(record['sha256'] == hashlib.sha256(Path(view['resource']).read_bytes()).hexdigest() for record in installed)
                    comparisons.append(compare_icon(art, images[name][at], name, view, window, actual,
                        density, directory/('image-'+view['name']), background=None if phase in folder_phases else tiles[at]))
                cases.append(dict(scale=density, phase=phase, state=state, window=window, comparisons=comparisons))
        assert not fixture.exists()
        from recycler_hover import run as recycler_hover
        hover = recycler_hover(command,query,env,probe,art,images,tiles,owner,storage,target,
            artifacts/'recycler-hover',theme,density_probe)
    finally:
        if fixture.exists():
            assert fixture.read_bytes() == payload
            fixture.unlink()
    tile = directories['theme']/'common_Tile.tiff'
    volumes = None
    if 'VolumeDisk' in art.entries:
        from volume_icons import run as volume_icons
        volumes = volume_icons(command,env,application,probe,density_probe,art,owner,artifacts/'volume-icons')
    processes = None
    if 'KillApplication' in art.entries:
        from process_artwork import run as process_artwork
        processes = process_artwork(command,env,application,probe,density_probe,art,owner,artifacts/'processes')
    result = dict(passed=True, resources=resources, cases=cases, tile_source=str(tile),
        tile_sha256=hashlib.sha256(tile.read_bytes()).hexdigest(),
        resource_representation_selections=len(resources)*5,
        native_image_comparisons=sum(len(case['comparisons']) for case in cases),
        recycler_hover=hover,volume_icons=volumes,process_artwork=processes,
        generic_application_wrappers=sorted(application_names),
        bundle_wrappers=sorted(bundle_names),bundle_native_comparisons=len(bundle_names)*5,
        recycler_original_animation_frames_preserved=False,
        recycler_retained_low_resolution_animation_frames=0,
        recycler_animation_hidpi_qualified=hover['animation_hidpi_qualified'], owned_fixture_removed=True,
        personal_preview_only=True, unrestricted_redistribution_qualified=False,
        full_current_source_build=False, full_package_lifecycle_qualified=False, full_plan_complete=False)
    (artifacts/'results.json').write_text(json.dumps(result, indent=2)+'\n')
    print(f"NeXTSpirit Workspace: {result['resource_representation_selections']} resource selections and {result['native_image_comparisons']} actual image comparisons PASS")
    return result
