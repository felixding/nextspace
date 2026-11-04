#!/usr/bin/env python3
"""Verify reconstructed cursor artwork in actual native Wayland buffers."""
import argparse
import json
from pathlib import Path
import subprocess
import shutil

from cursor_fidelity import run as fidelity
from cursors import observe_asset
from gnustep import capture_process_failure, headless_session, pasteboard_storage, process_runtime
from integration import until
from text_input import stop_process

# Use public AppKit selections where the fixture exposes the standard cursor.
CURSOR_KEYS = {'left_ptr':11,'xterm':23,'cross':46,'hand2':35,
    'sb_h_double_arrow':19,'hand1':24,'grabbing':25,'context-menu':50}


def run(compositor, probe, theme, artifacts, source=None, images=None, original_images=None, pasteboard_server=None):
    theme = theme.resolve()
    artifacts.mkdir(parents=True)
    original = fidelity(theme,artifacts/'fidelity',source)
    themes = artifacts/'themes'
    themes.mkdir()
    records = []
    pasteboard_server = pasteboard_server or shutil.which('gpbs-wayland')
    pasteboard_probe = probe.with_name('PasteboardProbe')
    assert pasteboard_server and pasteboard_probe.is_file(), 'Native cursor fixture needs session storage and PasteboardProbe'
    jobs = [(cursor,mode) for cursor in original['cases']
        for mode in (range(4) if cursor.get('frame_count',1)>1 else (0,))]
    for cursor,mode in jobs:
        name = cursor['name']
        code = CURSOR_KEYS.get(name,11)
        theme_name = theme.name
        route = 'AppKit selection'
        if name not in CURSOR_KEYS:
            # Exercise additional named assets through the same native arrow
            # loading path, preserving their own file metadata and animation.
            theme_name = 'NextSpace-'+name
            derived = themes/theme_name
            if not derived.exists():
                (derived/'cursors').mkdir(parents=True)
                (derived/'cursors/left_ptr').symlink_to((theme/'cursors'/name).resolve())
                (derived/'index.theme').write_text('[Icon Theme]\nName='+theme_name+'\n')
            route = 'named asset through explicit theme'
        case = artifacts/(name if mode==0 else name+'-mode-'+str(mode))
        settings = dict(XCURSOR_THEME=theme_name,
            XCURSOR_PATH=str(themes.resolve())+':'+str(theme.parent))
        with headless_session(compositor,case,extra_env=settings) as (env,command), \
                pasteboard_storage(pasteboard_server,pasteboard_probe,env,case) as storage:
            with (case/'probe.log').open('w') as log:
                client = subprocess.Popen([str(probe),'-GSBackend','libgnustep-wayland',
                    '-GSTheme','NextSpace','-CursorProbe','YES','-CursorRunLoopMode',str(mode)],env=env,stdout=log,stderr=log)
            try:
                def window():
                    assert client.poll() is None,(case/'probe.log').read_text()[-3000:]
                    return next((w for w in command('windows') if w['pid']==client.pid and
                        w['buffer_width']==801),None)
                w = until(window,'native '+name+' cursor probe first buffer')
                target = command('outputs')[0]
                assert command(f"move {w['id']} {target['x']+10} {target['y']+10}")['ok']
                assert command(f"focus {w['id']}")['ok']
                assert command(f"pointer {target['x']+210} {target['y']+310}")['ok']
                assert command(f'key {code} 1')['ok']
                assert command(f'key {code} 0')['ok']
                (case/'runtime.json').write_text(json.dumps(process_runtime(client.pid),indent=2)+'\n')
                for scale in (120,150,180,210,240):
                    assert command(f"test-scale {target['name']} {scale} 10000")['ok']
                    assert command('confirm')['ok']
                    states = observe_asset(command,theme/'cursors'/name,scale,case/(str(scale)+'.json'))
                    records.append(dict(name=name,scale=scale,route=route,states=states,
                        **(dict(mode=mode) if cursor.get('frame_count',1)>1 else {})))
            except AssertionError:
                (case/'failure-windows.json').write_text(json.dumps(command('windows'),indent=2)+'\n')
                capture_process_failure(client,case,'failure-client')
                capture_process_failure(storage,case,'failure-gpbs-server')
                raise
            finally:
                stop_process(client)
    result = dict(passed=True,fidelity=original,cases=records,full_cursor_library_qualified=original['full_cursor_library_qualified'])
    if images:
        from theme_images import run as theme_images
        theme_images(str(probe),images,artifacts/'theme-images',theme,
            ('common_OpenHandCursor','common_ClosedHandCursor','common_copyCursor','common_linkCursor','common_noCursor'),original_images)
        result['theme_images'] = json.loads((artifacts/'theme-images/results.json').read_text())
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f"Reconstructed native cursors: {len(records)} buffer/hotspot cases PASS",flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('compositor','probe','theme','artifacts'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--source',type=Path)
    parser.add_argument('--images',type=Path,help='Verify shared AppKit hand images as well as native cursors')
    parser.add_argument('--original-images',type=Path)
    parser.add_argument('--pasteboard-server',type=Path)
    args = parser.parse_args()
    run(args.compositor.resolve(),args.probe.resolve(),args.theme,args.artifacts.resolve(),
        args.source,args.images,args.original_images,args.pasteboard_server)

