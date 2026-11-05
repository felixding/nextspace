"""Check the real Processes panel's imported NeXTSpirit button image."""
import hashlib
import json
from pathlib import Path
import subprocess

from PIL import Image
from application_artwork import representations
from artwork_reference import assert_svg_representations
from folder_artwork import compare_icon
from gnustep import process_runtime
from integration import until


def run(command, env, workspace, probe, density_probe, art, owner, artifacts):
    artifacts.mkdir()
    name = 'KillApplication'
    baseline_root = Path(__file__).with_name('artwork-originals')/'workspace-processes'
    baseline = json.loads((baseline_root/'reference.json').read_text())
    assert hashlib.sha256((baseline_root/baseline['image']).read_bytes()).hexdigest() == baseline['image_sha256']
    logical = tuple(baseline['logical'])
    assert art.entries[name]['logical'] == baseline['logical']
    assert art.entries[name]['content_bounds'] == baseline['occupied']
    resources, images = {}, None
    for filename in art.entries[name]['targets']['workspace']:
        source = workspace.parent/'Resources'/filename
        directory = artifacts/'resources'/filename; directory.mkdir(parents=True)
        assert_svg_representations(art, name, source, logical)
        images, metadata = representations(density_probe,source,directory,logical)
        resources[filename] = dict(source=str(source),
            sha256=hashlib.sha256(source.read_bytes()).hexdigest(),selections=metadata)
    assert len({r['sha256'] for r in resources.values()}) == 1
    with (artifacts/'timemon.log').open('w') as log:
        app = subprocess.Popen(['/Applications/TimeMon.app/TimeMon','-GSBackend','libgnustep-wayland',
            '-GSTheme','/Library/Themes/NextSpace.theme','-NSUseRunningCopy','NO'],
            env=env,stdout=log,stderr=log)
    cases = []
    try:
        target = command('outputs')[0]
        for index,density in enumerate((120,150,180,210,240)):
            directory = artifacts/str(density); directory.mkdir()
            assert command(f"test-scale {target['name']} {density} 10000")['ok'] and command('confirm')['ok']

            def query():
                result = subprocess.run([str(probe),'--workspace-processes','TimeMon',str(directory/'live-image.tiff')],
                    env=env,capture_output=True,text=True,timeout=15)
                (directory/'query.log').write_text(result.stdout+result.stderr)
                (directory/'query-status.json').write_text(json.dumps(dict(returncode=result.returncode))+'\n')
                assert result.returncode in (0,1), (result.returncode,result.stderr)
                assert app.poll() is None, (artifacts/'timemon.log').read_text()[-4000:]
                return json.loads(result.stdout) if result.returncode == 0 else False

            state = until(query,'registered native application in Processes panel')
            if index == 0:
                (artifacts/'timemon-runtime.json').write_text(json.dumps(process_runtime(app.pid),indent=2)+'\n')
            assert state['enabled'] and not state['hidden']
            window = next(w for w in command('windows') if w['pid']==owner and w['client_id']==state['window'])
            assert command(f"move {window['id']} {target['x']+10} {target['y']+10}")['ok']
            capture = Path(env['NEXTSPACE_WAYLAND_CAPTURE_DIR'])/f"window-{state['window']}-{density}.png"
            capture.unlink(missing_ok=True); state = query()

            def rendered():
                window = next(w for w in command('windows') if w['pid']==owner and w['client_id']==state['window'])
                if window['preferred_scale'] != density:return False
                try:
                    with Image.open(capture) as image:pixels = image.convert('RGBA')
                except OSError:return False
                return (window,pixels) if pixels.size==(window['buffer_width'],window['buffer_height']) else False

            window,pixels = until(rendered,'Processes panel at current backing density')
            (directory/'case.json').write_text(json.dumps(dict(state=state,window=window),indent=2)+'\n')
            pixels.save(directory/'window.png')
            resource = state['image']['resource']
            if resource:
                assert hashlib.sha256(Path(resource).read_bytes()).hexdigest() == resources['Kill.tiff']['sha256']
            # NSButton's in-memory image need not retain fileName. Keep that
            # metadata and compare its representations and submitted pixels.
            comparison = compare_icon(art,images[index],name,state['image'],window,pixels,density,
                directory/'image',scan_aligned=True,resource=workspace.parent/'Resources/Kill.tiff')
            cases.append(dict(density=density,state=state,window=window,comparison=comparison))
    finally:
        app.terminate()
        try:app.wait(timeout=10)
        except subprocess.TimeoutExpired:
            app.kill();app.wait(timeout=5)
    result = dict(passed=True,resources=resources,cases=cases,
        resource_selections=len(resources)*5,native_image_comparisons=len(cases),kill_button_invoked=False,
        fixture_exit=app.returncode,personal_preview_only=True,full_plan_complete=False)
    (artifacts/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
