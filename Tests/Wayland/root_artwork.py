#!/usr/bin/env python3
"""Check the real root-path icon in an existing isolated Workspace session."""
import hashlib
import json
from pathlib import Path
import subprocess
from PIL import Image
from application_artwork import representations
from artwork_reference import assert_svg_representations
from folder_artwork import compare_icon
from integration import until
from vector_art import Artwork


def run(command, env, probe, density_probe, desktopkit_resources, theme, artifacts):
    artifacts.mkdir()
    source = Path(__file__).resolve().parents[2]/'Applications/Artwork/Root.svg'
    art = Artwork(source);resources = {};images = None
    for component,directory in (('desktopkit',desktopkit_resources),('theme',theme/'Resources/ThemeImages')):
        for filename in art.symbols['root'].get('data-'+component+'-files').split():
            path = directory/filename;sample = artifacts/'resources'/component/Path(filename).stem;sample.mkdir(parents=True)
            assert_svg_representations(art,'root',path,(48,48))
            frames,metadata = representations(density_probe,path,sample,(48,48))
            resources[component+'/'+filename] = dict(source=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),metadata=metadata)
            if component == 'desktopkit' and filename == 'NXRoot.tiff': images = frames
    assert {'desktopkit/NXRoot.tiff','theme/common_Root_PC.tiff','theme/common_Root_Apple.tiff'} <= resources.keys()

    def query(directory):
        result = subprocess.run([str(probe),'--workspace-root'],env=env,capture_output=True,text=True,timeout=15)
        (directory/'query.log').write_text(result.stdout+result.stderr)
        assert result.returncode == 0, result.stderr
        state = json.loads(result.stdout)
        assert state['root'] == '/' and len(state['images']) == 1 and state['images'][0]['name'] == 'Root'
        return state

    initial = until(lambda: query(artifacts),'actual root-path icon')
    owner = next(w['pid'] for w in command('windows') if w['client_id'] == initial['window'])
    target = command('outputs')[0];cases = []
    for index,density in enumerate((120,150,180,210,240)):
        directory = artifacts/str(density);directory.mkdir()
        assert command(f"test-scale {target['name']} {density} 10000")['ok'] and command('confirm')['ok']
        window = next(w for w in command('windows') if w['pid'] == owner and w['client_id'] == initial['window'])
        assert command(f"move {window['id']} {target['x']+10} {target['y']+10}")['ok']
        path = Path(env['NEXTSPACE_WAYLAND_CAPTURE_DIR'])/f"window-{initial['window']}-{density}.png"
        path.unlink(missing_ok=True);state = query(directory)

        def captured():
            window = next(w for w in command('windows') if w['pid'] == owner and w['client_id'] == state['window'])
            (directory/'capture-status.json').write_text(json.dumps(dict(window=window,path=str(path),exists=path.exists()),indent=2)+'\n')
            if window['preferred_scale'] != density: return False
            try:
                with Image.open(path) as image: full = image.convert('RGBA')
            except OSError: return False
            expected = tuple((window[k]*density+60)//120 for k in ('width','height'))
            return (window,full) if full.size == expected == (window['buffer_width'],window['buffer_height']) else False

        window,full = until(captured,'native Workspace root-icon buffer')
        assert not window['legacy'];full.save(directory/'window.png')
        view = state['images'][0]
        assert Path(view['resource']).resolve() == (desktopkit_resources/'NXRoot.tiff').resolve()
        comparison = compare_icon(art,images[index],'root',view,window,full,density,directory/'image')
        cases.append(dict(scale=density,state=state,window=window,comparison=comparison))
    result = dict(passed=True,resources=resources,cases=cases,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        resource_representation_selections=len(resources)*5,native_image_comparisons=len(cases),
        full_current_source_build=False,full_package_lifecycle_qualified=False,full_plan_complete=False)
    (artifacts/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'Workspace root computer: {len(resources)*5} resource selections and five native Path-view comparisons PASS')
    return result
