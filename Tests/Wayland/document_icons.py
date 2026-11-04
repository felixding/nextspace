"""Check generic and unreadable files in the real Workspace Icon viewer."""
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


def run(command,env,application,probe,density_probe,owner,desktopkit_resources,theme,artifacts,fixture):
    artifacts.mkdir();repository=Path(__file__).resolve().parents[2]
    artwork_source=repository/'Applications/Artwork/Documents.svg';art=Artwork(artwork_source)
    workspace=application.parent/'Resources';resources={};frames={};submitted={}
    for component,folder in [('workspace',workspace),('desktopkit',desktopkit_resources),
            ('theme',theme/'Resources/ThemeImages')]:
        for name,symbol in art.symbols.items():
            for filename in symbol.get('data-'+component+'-files','').split():
                source=folder/filename;directory=artifacts/'resources'/component/name
                directory.mkdir(parents=True)
                assert_svg_representations(art,name,source,(48,48))
                images,metadata=representations(density_probe,source,directory)
                resources[component+'/'+filename]=dict(source=str(source),
                    sha256=hashlib.sha256(source.read_bytes()).hexdigest(),selections=metadata)
                frames[name]=images;submitted[name]=source
    assert len(resources)==5
    from document_fidelity import run as fidelity
    fidelity(artifacts/'source-fidelity',images=submitted)
    fixture.mkdir()
    (fixture/'unknown.mystery').write_bytes(bytes(range(256))*2)
    (fixture/'text.mystery').write_text('Plain-text artwork fixture.\n')
    unreadable=fixture/'unreadable.mystery';unreadable.write_bytes(bytes(range(255,-1,-1))*2)
    unreadable.chmod(0)
    permission=dict(path=str(unreadable),mode=unreadable.stat().st_mode&0o777,owner=unreadable.stat().st_uid)
    cases=[];target=command('outputs')[0]
    try:
        # The surrounding fixture removes DAC override/read-search capabilities.
        status=Path(f'/proc/{owner}/status').read_text()
        (artifacts/'workspace-capabilities.txt').write_text(status)
        for line in status.splitlines():
            if line.startswith(('CapEff:','CapPrm:')):assert int(line.split()[1],16)&6==0,line
        for index,density in enumerate((120,150,180,210,240)):
            directory=artifacts/str(density);directory.mkdir()
            assert command(f"test-scale {target['name']} {density} 10000")['ok'] and command('confirm')['ok']
            def query():
                p=subprocess.run([str(probe),'--workspace-folders',str(fixture)],env=env,
                    capture_output=True,text=True,timeout=15)
                (directory/'query.log').write_text(p.stdout+p.stderr)
                assert p.returncode==0,p.stderr
                state=json.loads(p.stdout)
                return state if {v['name'] for v in state['images']}=={'unknown.mystery','unreadable.mystery','text.mystery'} else None
            state=until(query,'actual document file icons')
            window=next(w for w in command('windows') if w['pid']==owner and w['client_id']==state['window'])
            assert command(f"move {window['id']} {target['x']+10} {target['y']+10}")['ok']
            capture=Path(env['NEXTSPACE_WAYLAND_CAPTURE_DIR'])/f"window-{state['window']}-{density}.png"
            capture.unlink(missing_ok=True);state=until(query,'document icons after move')
            def rendered():
                window=next(w for w in command('windows') if w['pid']==owner and w['client_id']==state['window'])
                if window['preferred_scale']!=density:return False
                try:
                    with Image.open(capture) as image:pixels=image.convert('RGBA')
                except OSError:return False
                return (window,pixels) if pixels.size==(window['buffer_width'],window['buffer_height']) else False
            window,pixels=until(rendered,'native document icon buffer')
            assert not window['legacy'];pixels.save(directory/'window.png');comparisons=[]
            for view in state['images']:
                name={'unknown.mystery':'Unknown','unreadable.mystery':'BadFile','text.mystery':'TextFile'}[view['name']]
                expected=submitted[name]
                assert Path(view['resource']).resolve()==expected.resolve(),view
                comparisons.append(compare_icon(art,frames[name][index],name,view,window,
                    pixels,density,directory/name,resource=expected))
            cases.append(dict(density=density,state=state,window=window,comparisons=comparisons))
    finally:unreadable.chmod(0o600)
    result=dict(passed=True,resources=resources,cases=cases,native_image_comparisons=15,
        resource_representation_selections=25,actual_permission_failure=True,
        permission_fixture=permission,source_sha256=hashlib.sha256(artwork_source.read_bytes()).hexdigest(),full_plan_complete=False)
    (artifacts/'results.json').write_text(json.dumps(result,indent=2)+'\n');return result
