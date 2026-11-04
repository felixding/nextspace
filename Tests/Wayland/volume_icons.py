"""Check imported volume artwork in Workspace's actual Icon viewer."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from PIL import Image
from application_artwork import representations
from artwork_reference import assert_svg_representations
from folder_artwork import compare_icon
from gnustep import process_runtime
from integration import until,read_json_lines
from vector_art import Artwork


def run(command, env, application, probe, density_probe, art, owner, artifacts):
    artifacts.mkdir()
    from volume_overlay_fidelity import run as overlay_fidelity
    fidelity=overlay_fidelity(art.pack,artifacts/'source-fidelity')
    from floppy_fidelity import run as floppy_fidelity
    floppy_check=floppy_fidelity(artifacts/'floppy-fidelity')
    floppy=Artwork(Path(__file__).resolve().parents[2]/'Applications/Artwork/Floppy.svg')
    artworks={name:art for name in ('VolumeDisk','CompactDisc','VolumeHighlighted','VolumeNTFS')}
    artworks.update(Floppy=floppy,FloppyOpen=floppy)
    targets={name:art.entries[name]['targets']['workspace'] for name in artworks if artworks[name] is art}
    targets.update(Floppy=['DOS_FD.fs.tiff'],FloppyOpen=['DOS_FD.openfs.tiff'])
    resources, frames, cases = {}, {}, []
    for name,renderer in artworks.items():
        for filename in targets[name]:
            source = application.parent/'Resources'/filename
            sample = artifacts/'resources'/source.stem; sample.mkdir(parents=True)
            assert_svg_representations(renderer,name,source,(48,48))
            selected, metadata = representations(density_probe,source,sample,(48,48))
            resources[filename] = dict(source=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                selections=metadata)
            frames[name] = selected
    assert resources['CDROM.fs.tiff']['sha256'] == resources['CDROM.openfs.tiff']['sha256']
    fixture = artifacts/'fixture'; disc = fixture/'CompactDisc'; disc.mkdir(parents=True)
    shutil.copyfile(application.parent/'Resources/CDROM.fs.tiff',disc/'.dir.tiff')
    ntfs=fixture/'NTFS';ntfs.mkdir()
    shutil.copyfile(application.parent/'Resources/NTFS_HDD.fs.tiff',ntfs/'.dir.tiff')
    floppy_folder=fixture/'Floppy';floppy_folder.mkdir()
    shutil.copyfile(application.parent/'Resources/DOS_FD.fs.tiff',floppy_folder/'.dir.tiff')
    shutil.copyfile(application.parent/'Resources/DOS_FD.openfs.tiff',floppy_folder/'.opendir.tiff')
    custom_folders=dict(CompactDisc=disc,VolumeNTFS=ntfs,Floppy=floppy_folder)
    # /dev/shm is an existing different-device mount in the disposable consumer.
    # No disk, mount, media service or production preferences are changed.
    mount = Path('/dev/shm')
    assert mount.is_dir() and mount.stat().st_dev != mount.parent.stat().st_dev
    definitions = [('VolumeDisk',mount.parent,mount.name),('CompactDisc',fixture,disc.name),
        ('VolumeNTFS',fixture,ntfs.name),('Floppy',fixture,floppy_folder.name)]
    hover_definitions=[('VolumeHighlighted','VolumeDisk',mount.parent,mount.name,'HDD.openfs.tiff','HDD.fs.tiff',None),
        ('FloppyOpen','Floppy',fixture,floppy_folder.name,'.opendir.tiff','.dir.tiff',floppy_folder)]

    def query(directory,path,name):
        process = subprocess.run([str(probe),'--workspace-folders',str(path),'closed',name],
            env=env,capture_output=True,text=True,timeout=15)
        (directory/'query.log').write_text(process.stdout+process.stderr)
        assert process.returncode == 0,process.stderr
        state = json.loads(process.stdout)
        assert len(state['images']) == 1 and state['images'][0]['name'] == name
        return state

    def capture(state,directory,density):
        window=next(w for w in command('windows') if w['pid']==owner and w['client_id']==state['window'])
        assert command(f"move {window['id']} {target['x']+10} {target['y']+10}")['ok']
        path=Path(env['NEXTSPACE_WAYLAND_CAPTURE_DIR'])/f"window-{state['window']}-{density}.png"
        path.unlink(missing_ok=True)
        state=query(directory,Path(state['root']),state['images'][0]['name'])
        def rendered():
            w=next(w for w in command('windows') if w['pid']==owner and w['client_id']==state['window'])
            if w['preferred_scale']!=density:return False
            try:
                with Image.open(path) as image:pixels=image.convert('RGBA')
            except OSError:return False
            return (w,pixels) if pixels.size==(w['buffer_width'],w['buffer_height']) else False
        window,pixels=until(rendered,'Native volume icon at current density');pixels.save(directory/'window.png')
        return state,window,pixels

    target = command('outputs')[0]
    source=artifacts/'owned-volume-hover.txt';payload=b'Owned volume highlight fixture\n';source.write_bytes(payload)
    arguments=[str(probe.with_name('DragProbe')),'-GSBackend','libgnustep-wayland',
        '-GSTheme','/Library/Themes/NextSpace.theme','-GSSuppressAppIcon','YES',
        '-NSUseRunningCopy','NO','-DragSource','YES','-DragFile',str(source)]
    (artifacts/'source-command.json').write_text(json.dumps(arguments,indent=2)+'\n')
    log_path=artifacts/'source.log'
    with log_path.open('w') as log,(artifacts/'source.stderr').open('w') as errors:
        drag=subprocess.Popen(arguments,env=env,stdout=log,stderr=errors)
    drags=[]
    try:
        def started():
            assert drag.poll() is None,(artifacts/'source.stderr').read_text()
            return next((w for w in command('windows') if w['pid']==drag.pid and w['title']=='NativeDragSource'),None)
        drag_window=until(started,'Volume hover source');other=next(o for o in command('outputs') if o['name']!=target['name'])
        assert command(f"move {drag_window['id']} {other['x']+400} {other['y']+300}")['ok']
        drag_window=until(lambda:(lambda w:w if (w['x'],w['y'])==(other['x']+400,other['y']+300) else False)(
            next(w for w in command('windows') if w['id']==drag_window['id'])),'Volume source placement')
        (artifacts/'source-runtime.json').write_text(json.dumps(process_runtime(drag.pid),indent=2)+'\n')
        for at,density in enumerate((120,150,180,210,240)):
            assert command(f"test-scale {target['name']} {density} 10000")['ok'] and command('confirm')['ok']
            for symbol,path,name in definitions:
                directory = artifacts/f'{density}-{symbol}'; directory.mkdir()
                state = query(directory,path,name)
                state,window,pixels=capture(state,directory,density)
                view = state['images'][0]
                if symbol == 'VolumeDisk':assert Path(view['resource']).name == 'HDD.fs.tiff'
                else:
                    custom=custom_folders[symbol]
                    resource=targets[symbol][0]
                    assert hashlib.sha256((custom/'.dir.tiff').read_bytes()).hexdigest()==resources[resource]['sha256']
                # Custom-folder images may not retain fileName. Preserve that native
                # metadata and check the known resource plus actual submitted pixels.
                comparison = compare_icon(artworks[symbol],frames[symbol][at],symbol,view,window,pixels,density,directory/'image',
                    resource=custom/'.dir.tiff' if symbol != 'VolumeDisk' else None)
                cases.append(dict(symbol=symbol,density=density,state=state,window=window,comparison=comparison))
            for opened_symbol,closed_symbol,path,name,opened_filename,closed_filename,custom in hover_definitions:
                suffix='hover' if custom is None else opened_symbol
                directory=artifacts/f'{density}-{suffix}';directory.mkdir();state=query(directory,path,name)
                state,window,pixels=capture(state,directory,density);view=state['images'][0]
                began=len([v for v in read_json_lines(log_path) if v['event']=='drag-begin'])
                ended=len([v for v in read_json_lines(log_path) if v['event']=='drag-end'])
                assert command(f"focus {drag_window['id']}")['ok']
                assert command(f"pointer {drag_window['x']+50} {drag_window['y']+100}")['ok'] and command('button 272 1')['ok']
                until(lambda:len([v for v in read_json_lines(log_path) if v['event']=='drag-begin'])>began,'Volume drag begins')
                until(lambda:command('drag-state')['active'],'Volume drag is active')
                x,y,w,h=view['base'];assert command(f"pointer {int(window['x']+x+w/2)} {int(window['y']+window['height']-y-h/2)}")['ok']
                def image_is(filename):
                    value=query(directory,path,name);resource=value['images'][0]['resource']
                    return value if Path(resource).name==filename or (custom is not None and not resource) else False
                state=until(lambda:image_is(opened_filename),'Mount uses its opened image')
                negotiated=command('drag-state');assert negotiated['active'] and negotiated['target']==window['id'] and negotiated['action']==1
                state,window,pixels=capture(state,directory,density)
                comparison=compare_icon(artworks[opened_symbol],frames[opened_symbol][at],opened_symbol,state['images'][0],window,pixels,density,directory/'image',resource=custom/'.opendir.tiff' if custom is not None else None)
                cases.append(dict(symbol=opened_symbol,density=density,state=state,window=window,comparison=comparison))
                assert command('key 1 1')['ok'] and command('key 1 0')['ok']
                until(lambda:not command('drag-state')['active'],'Volume drag cancels');assert command('button 272 0')['ok']
                endings=until(lambda:(lambda v:v if len(v)>ended else False)([v for v in read_json_lines(log_path) if v['event']=='drag-end']),'Source observes cancelled volume drag')
                assert endings[-1]['action']==0;drags.append(dict(symbol=closed_symbol,density=density,negotiation=negotiated,end=endings[-1]))
                suffix='restored' if custom is None else closed_symbol+'-restored'
                restored=artifacts/f'{density}-{suffix}';restored.mkdir();state=until(lambda:image_is(closed_filename),'Mount restores its closed image')
                state,window,pixels=capture(state,restored,density)
                comparison=compare_icon(artworks[closed_symbol],frames[closed_symbol][at],closed_symbol,state['images'][0],window,pixels,density,restored/'image',resource=custom/'.dir.tiff' if custom is not None else None)
                cases.append(dict(symbol=closed_symbol,phase='restored',density=density,state=state,window=window,comparison=comparison))
    finally:
        if drag.poll() is None:
            command('key 1 1');command('key 1 0');command('button 272 0');drag.terminate();drag.wait(timeout=5)
    assert source.read_bytes()==payload and not (mount/source.name).exists() and not (floppy_folder/source.name).exists()
    result = dict(passed=True,resources=resources,cases=cases,real_generic_mount_icon=True,
        compact_disc_rendered_via_custom_folder=True,physical_optical_media_tested=False,
        ntfs_rendered_via_custom_folder=True,physical_ntfs_media_tested=False,
        real_mount_open_and_restore_tested=True,cancelled_drags=drags,source_unchanged=True,
        owned_source_reaped=drag.poll() is not None,source_fidelity=fidelity,
        floppy_rendered_via_custom_folder=True,physical_fat_media_tested=False,floppy_source_fidelity=floppy_check,
        resource_selections=35,native_image_comparisons=40,personal_preview_only=True,
        full_plan_complete=False)
    (artifacts/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
