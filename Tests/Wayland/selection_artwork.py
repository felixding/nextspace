"""Check multiple-file artwork in the actual selected path row and Inspector."""
import hashlib
import json
import math
from pathlib import Path
import subprocess

from PIL import Image,ImageChops
from application_artwork import placed_reference,representations
from artwork_reference import assert_svg_representations
from folder_artwork import compare_icon
from integration import until
from vector_art import Artwork


def run(command,env,application,probe,density_probe,owner,artifacts):
    artifacts.mkdir();repository=Path(__file__).resolve().parents[2]
    art=Artwork(repository/'Applications/Artwork/Selection.svg')
    from selection_fidelity import run as fidelity
    fidelity(artifacts/'source-fidelity')
    workspace=application.parent/'Resources';theme=Path('/Library/Themes/NextSpace.theme/Resources/ThemeImages')
    resources={};images={}
    for symbol,folder,name,logical in [('MultipleSelection',workspace,'MultipleSelection.tiff',(48,48)),
            ('MultipleSelection',theme,'common_MultipleSelection.tiff',(48,48)),
            ('SelectionHighlight',workspace,'hilite.tiff',(66,52))]:
        source=folder/name;directory=artifacts/'resources'/name;directory.mkdir(parents=True)
        assert_svg_representations(art,symbol,source,logical)
        frames,metadata=representations(density_probe,source,directory,logical)
        resources[name]=dict(source=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest(),selections=metadata)
        images[symbol]=frames
    assert resources['MultipleSelection.tiff']['sha256']==resources['common_MultipleSelection.tiff']['sha256']
    fixture=artifacts/'fixture';fixture.mkdir()
    for name in ['first.txt','second.txt']:(fixture/name).write_text('Multiple selection artwork\n')
    cases=[];target=command('outputs')[0]
    for index,density in enumerate((120,150,180,210,240)):
        assert command(f"test-scale {target['name']} {density} 10000")['ok'] and command('confirm')['ok']
        for phase in ['path','inspector']:
            directory=artifacts/f'{density}-{phase}';directory.mkdir()
            def query():
                p=subprocess.run([str(probe),'--workspace-selection',str(fixture),phase],env=env,
                    capture_output=True,text=True,timeout=15)
                (directory/'query.log').write_text(p.stdout+p.stderr)
                assert p.returncode==0,(p.returncode,p.stderr)
                return json.loads(p.stdout)
            state=query();assert state['selection_count']==2
            window=next(w for w in command('windows') if w['pid']==owner and w['client_id']==state['window'])
            assert command(f"move {window['id']} {target['x']+10} {target['y']+10}")['ok']
            capture=Path(env['NEXTSPACE_WAYLAND_CAPTURE_DIR'])/f"window-{state['window']}-{density}.png"
            capture.unlink(missing_ok=True);state=query()
            def rendered():
                w=next(w for w in command('windows') if w['pid']==owner and w['client_id']==state['window'])
                if w['preferred_scale']!=density:return False
                try:
                    with Image.open(capture) as p:pixels=p.convert('RGBA')
                except OSError:return False
                return (w,pixels) if pixels.size==(w['buffer_width'],w['buffer_height']) else False
            window,pixels=until(rendered,'multiple-selection native buffer');pixels.save(directory/'window.png')
            view=state['image'];assert view['selected']==(phase=='path')
            background=None
            if phase=='path':
                x,y,w,h=state['highlight']['base'];factor=density/120
                origin=x*factor,(window['height']-y-h)*factor
                bounds=(*origin,origin[0]+w*factor,origin[1]+h*factor)
                aligned=tuple(math.floor(v+.5) for v in bounds)
                clip=(max(bounds[0],aligned[0]),max(bounds[1],aligned[1]),
                    min(bounds[2],aligned[2])-max(bounds[0],aligned[0]),
                    min(bounds[3],aligned[3])-max(bounds[1],aligned[1]))
                background=placed_reference(images['SelectionHighlight'][index],origin,
                    Image.new('RGBA',pixels.size,(170,170,170,255)),directory,density,
                    size=(w*factor,h*factor),pad=True,clip=clip,native_rep_size=(w,h))
            comparison=compare_icon(art,images['MultipleSelection'][index],'MultipleSelection',view,window,
                pixels,density,directory/'image',background=background,scan_aligned=phase=='inspector',
                resource=workspace/'MultipleSelection.tiff',selected=phase=='path')
            if phase=='path':
                x,y,w,h=view['base'];factor=density/120;left=math.floor(x*factor);top=math.floor((window['height']-y-h)*factor)
                with Image.open(directory/'image/expected.png') as p:background.paste(p.convert('RGBA'),(left,top))
                x,y,w,h=state['highlight']['base'];box=(math.floor(x*factor),math.floor((window['height']-y-h)*factor),
                    math.ceil((x+w)*factor),math.ceil((window['height']-y)*factor))
                actual=pixels.crop(box);expected=background.crop(box);actual.save(directory/'selected-actual.png');expected.save(directory/'selected-expected.png')
                maximum=max(hi for _,hi in ImageChops.difference(actual,expected).getextrema());assert maximum<=1,('selection backdrop',density,maximum)
                comparison['selected_backdrop_maximum_difference']=maximum
            cases.append(dict(density=density,phase=phase,state=state,window=window,comparison=comparison))
    result=dict(passed=True,cases=cases,resources=resources,native_image_comparisons=10,
        selected_backdrop_comparisons=5,resource_selections=15,actual_path_and_inspector_usage=True,
        actual_theme_lookup_qualified=False,full_plan_complete=False)
    (artifacts/'results.json').write_text(json.dumps(result,indent=2)+'\n');return result
