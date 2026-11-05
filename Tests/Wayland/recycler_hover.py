"""Check real Recycler hover with NeXTSpirit's first pose and faithful SVG poses."""
import hashlib
import json
from pathlib import Path
import subprocess
import time
from PIL import Image
from application_artwork import representations
from artwork_reference import artwork_original
from artwork_reference import assert_svg_representations
from folder_artwork import compare_icon
from gnustep import process_runtime, capture_process_failure
from integration import until, read_json_lines
from recycler_pose_fidelity import run as pose_fidelity, POSES
from vector_art import Artwork


def run(command,query,env,probe,art,images,tiles,owner,storage,target,artifacts,theme,density_probe):
    artifacts.mkdir()
    pose_source = Path(__file__).resolve().parents[2]/'Applications/Workspace/Artwork.svg'
    fidelity = pose_fidelity(artifacts/'source-fidelity',pose_source);pose_art = Artwork(pose_source)
    resource_directory = Path(query('--workspace-recycler',artifacts)['image']['resource']).parent
    resources,pose_images = {},{}
    for name in POSES:
        path = resource_directory/(name+'.tiff');sample = artifacts/'resources'/name;sample.mkdir(parents=True)
        assert_svg_representations(pose_art,name,path,(64,64))
        pose_images[name],metadata = representations(density_probe,path,sample,(64,64))
        resources['workspace/'+path.name] = dict(name=name,source=str(path),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),metadata=metadata)
    source = artifacts/'owned-recycler-hover.txt';payload = b'Owned Recycler hover fixture\n';source.write_bytes(payload)
    arguments = [str(probe.with_name('DragProbe')),'-GSBackend','libgnustep-wayland','-GSTheme',str(theme),
        '-NSUseRunningCopy','NO','-GSSuppressAppIcon','YES','-DragSource','YES','-MoveDrag','YES','-DragFile',str(source)]
    (artifacts/'command.json').write_text(json.dumps(arguments,indent=2)+'\n')
    log_path = artifacts/'source.log'
    with log_path.open('w') as log, (artifacts/'source.stderr').open('w') as errors:
        app = subprocess.Popen(arguments,env=env,stdout=log,stderr=errors)
    cases = [];static_comparisons = [];static_cases = [];pose_comparisons = []

    def window(state):
        return next(w for w in command('windows') if w['pid']==owner and w['client_id']==state['window'])

    try:
        def started():
            assert app.poll() is None,(artifacts/'source.stderr').read_text()
            return next((w for w in command('windows') if w['pid']==app.pid and w['title']=='NativeDragSource'),None)
        drag_window = until(started,'Recycler move-drag source')
        other = next(o for o in command('outputs') if o['name']!=target['name'])
        assert command(f"move {drag_window['id']} {other['x']+400} {other['y']+300}")['ok']
        drag_window = until(lambda: (lambda w:w if (w['x'],w['y'])==(other['x']+400,other['y']+300) else False)(
            next(w for w in command('windows') if w['id']==drag_window['id'])), 'Recycler drag-source placement')
        originals = {}
        for index in range(1,5):originals['recycler-'+str(index)] = artwork_original('recycler','pose-'+str(index))
        for at,density in enumerate((120,150,180,210,240)):
            sample = artifacts/str(density);sample.mkdir()
            assert command(f"test-scale {target['name']} {density} 10000")['ok'] and command('confirm')['ok']
            previous = None

            def capture(state,directory):
                nonlocal previous
                path = Path(env['NEXTSPACE_WAYLAND_CAPTURE_DIR'])/f"window-{state['window']}-{density}.png"
                path.unlink(missing_ok=True);state = query('--workspace-recycler',directory)
                def ready():
                    current = window(state)
                    if current['preferred_scale']!=density:return False
                    try:
                        with Image.open(path) as image:actual = image.convert('RGBA')
                    except OSError:return False
                    expected = tuple((current[k]*density+60)//120 for k in ('width','height'))
                    if actual.size!=expected or actual.size!=(current['buffer_width'],current['buffer_height']):return False
                    if previous is not None and actual.tobytes()==previous.tobytes():return False
                    return current,actual
                current,actual = until(ready,'Recycler hover buffer')
                assert not current['legacy'];actual.save(directory/'window.png');previous = actual
                return state,current,actual

            initial = sample/'initial';initial.mkdir();state = query('--workspace-recycler',initial)
            state,current,actual = capture(state,initial)
            assert state['items_count']==0 and Path(state['image']['resource']).name=='recycler.tiff'
            static_comparisons.append(compare_icon(art,images['RecyclerEmpty'][at],'RecyclerEmpty',state['image'],current,actual,density,initial/'image',background=tiles[at]))
            static_cases.append(dict(scale=density,phase='initial',state=state,window=current,comparison=static_comparisons[-1]))
            began = len([r for r in read_json_lines(log_path) if r['event']=='drag-begin'])
            ended = len([r for r in read_json_lines(log_path) if r['event']=='drag-end'])
            assert command(f"focus {drag_window['id']}")['ok']
            assert command(f"pointer {drag_window['x']+50} {drag_window['y']+100}")['ok']
            assert command('button 272 1')['ok']
            until(lambda:len([r for r in read_json_lines(log_path) if r['event']=='drag-begin'])>began,'move drag begins')
            until(lambda:command('drag-state')['active'],'Recycler move drag is active')
            poses = {};start = time.monotonic();step = 0
            while len(poses)<4:
                assert time.monotonic()-start<8,'Recycler did not expose all four hover poses'
                current = window(state)
                assert command(f"pointer {current['x']+31+step%2} {current['y']+32}")['ok'];step+=1
                time.sleep(.12)
                hovered = query('--workspace-recycler',sample)
                name = Path(hovered['image']['resource']).stem
                if name not in originals or name in poses:continue
                drag = command('drag-state');assert drag['active'] and drag['target']==current['id'] and drag['action']==2
                directory = sample/name;directory.mkdir();previous = None
                hovered,current,actual = capture(hovered,directory)
                original,fixture = originals[name];view = hovered['image']
                if name == 'recycler-1':
                    resource = Path(view['resource'])
                    assert resource.read_bytes() == resource.with_name('recycler.tiff').read_bytes()
                    comparison = compare_icon(art,images['RecyclerEmpty'][at],'RecyclerEmpty',view,current,
                        actual,density,directory/'image',background=tiles[at])
                    poses[name] = dict(state=hovered,window=current,drag=drag,
                        source_sha256=hashlib.sha256(resource.read_bytes()).hexdigest(),
                        maximum_channel_difference=comparison['maximum_channel_difference'],legacy_low_resolution=False,
                        artwork='NeXTSpirit RecyclerEmpty',same_resource_pixels_as_static=True)
                    pose_comparisons.append(dict(scale=density,name=name,maximum=comparison['maximum_channel_difference']))
                    continue
                resource = Path(view['resource']);record = resources['workspace/'+resource.name]
                assert resource.stem==name and hashlib.sha256(resource.read_bytes()).hexdigest()==record['sha256']
                assert view['base']==[0,0,64,64] and actual.size==tiles[at].size
                comparison = compare_icon(pose_art,pose_images[name][at],name,view,current,actual,
                    density,directory/'image',background=tiles[at])
                poses[name] = dict(state=hovered,window=current,drag=drag,source_sha256=record['sha256'],
                    original_source_sha256=fixture['source_sha256'],original_bounds=original.getchannel('A').getbbox(),
                    maximum_channel_difference=comparison['maximum_channel_difference'],legacy_low_resolution=False,
                    artwork='original-style SVG '+name)
                pose_comparisons.append(dict(scale=density,name=name,maximum=comparison['maximum_channel_difference']))
            assert command('key 1 1')['ok'] and command('key 1 0')['ok']
            until(lambda:not command('drag-state')['active'],'Recycler drag cancels')
            assert command('button 272 0')['ok']
            endings = until(lambda:(lambda r:r if len(r)>ended else False)([r for r in read_json_lines(log_path) if r['event']=='drag-end']),'Recycler source observes cancellation')
            assert endings[-1]['action']==0 and source.read_bytes()==payload
            restored = sample/'restored';restored.mkdir();previous = None
            state = until(lambda:(lambda r:r if Path(r['image']['resource']).name=='recycler.tiff' else False)(
                query('--workspace-recycler',restored)),'Recycler fitted icon restores')
            state,current,actual = capture(state,restored)
            static_comparisons.append(compare_icon(art,images['RecyclerEmpty'][at],'RecyclerEmpty',state['image'],current,actual,density,restored/'image',background=tiles[at]))
            static_cases.append(dict(scale=density,phase='restored',state=state,window=current,comparison=static_comparisons[-1]))
            assert state['items_count']==0 and not any(p.name!='.recycler.db' for p in storage.iterdir())
            cases.append(dict(scale=density,poses=poses,end=endings[-1],source_unchanged=True))
        (artifacts/'source-runtime.json').write_text(json.dumps(process_runtime(app.pid),indent=2)+'\n')
        (artifacts/'source-maps.txt').write_text(Path(f'/proc/{app.pid}/maps').read_text())
    except BaseException:
        capture_process_failure(app,artifacts,'failure-source');raise
    finally:
        command('key 1 1');command('key 1 0')
        if app.poll() is None:app.terminate();app.wait(timeout=5)
        command('button 272 0')
    result = dict(passed=True,resources=resources,source_fidelity=fidelity,cases=cases,static_cases=static_cases,
        static_comparisons=static_comparisons,pose_comparisons=pose_comparisons,
        fitted_native_comparisons=len(static_comparisons),legacy_native_comparisons=0,
        hidpi_pose_native_comparisons=len(pose_comparisons),
        cancelled_drags=5,source_unchanged=source.read_bytes()==payload,owned_source_pid=app.pid,owned_source_reaped=app.poll() is not None,
        animation_hidpi_qualified=True,personal_preview_only=True,full_plan_complete=False)
    (artifacts/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Recycler hover: five cancelled move drags, 10 static and 20 HiDPI animation-pose captures PASS')
    return result
