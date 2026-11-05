"""Actual Review multipage selection, zoom and density transitions."""
import json
import hashlib
from pathlib import Path
import subprocess
import time
from PIL import Image, ImageChops
from gnustep import capture_frame, capture_process_failure
from integration import until

COLORS=((255,0,0),(0,255,0),(0,0,255))
ACTIONS=(('next',1,'100%'),('zoom-in',1,'200%'),('zoom-out',1,'100%'),
         ('next',2,'100%'),('previous',1,'100%'),('previous',0,'100%'))


def document(artifacts):
    pages=[Image.new('RGB',(512,384),color) for color in COLORS]
    source=artifacts/'three-pages.tiff'
    pages[0].save(source,save_all=True,append_images=pages[1:])
    return source


def request(probe,env,artifacts,action,*extra):
    if action == 'open':
        # The app icon may map before the distributed-object connection exists.
        until(lambda: request(probe,env,artifacts,'ready')['ready'], 'Review application connection',timeout=20)
    arguments=[str(probe),'--review',action,*extra]
    started=time.monotonic();failure=None
    process=subprocess.Popen(arguments,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        stdout,stderr=process.communicate(timeout=12)
        elapsed=time.monotonic()-started
    except subprocess.TimeoutExpired as error:
        failure=error;elapsed=time.monotonic()-started
        try:capture_process_failure(process,artifacts,'failure-review-request')
        except Exception as diagnostic_error:
            (artifacts/'failure-review-request-diagnostic.txt').write_text(repr(diagnostic_error)+'\n')
        finally:
            if process.poll() is None:process.kill()
            stdout,stderr=process.communicate(timeout=5)
    with (artifacts/'requests.jsonl').open('a') as log:
        log.write(json.dumps(dict(action=action,returncode=process.returncode,stdout=stdout,stderr=stderr,
            elapsed_seconds=elapsed,timed_out=failure is not None))+'\n')
    if failure:raise failure
    assert process.returncode==0,(stdout,stderr)
    return json.loads(stdout)


def document_window(command,pid,source):
    # Review can keep same-named documents from different directories open.
    title=f'{source.name}  --  {source.parent}'
    return next((w for w in command('windows') if w['pid']==pid and
        w['title']==title and w['width']>300 and w['visible']),None)


def check_state(state,index,zoom):
    assert state['frames']==3 and state['index']==index and state['zoom']==zoom,state
    factor=int(zoom[:-1])/100
    assert state['image_size']=='{width = %d; height = %d}'%(512*factor,384*factor),state


def runtime(pid,artifacts):
    libraries=sorted({line.split()[-1] for line in Path(f'/proc/{pid}/maps').read_text().splitlines()
        if any(token in line for token in ('libgnustep-','libobjc.so.','libDesktopKit','libSystemKit'))})
    assert any('libgnustep-wayland' in path for path in libraries),libraries
    assert not any('libgnustep-x11' in path for path in libraries),libraries
    (artifacts/'runtime.json').write_text(json.dumps(dict(
        executable=str(Path(f'/proc/{pid}/exe').resolve()),libraries=libraries),indent=2)+'\n')


def frame(window,captures):
    current=window()
    if not current:return None
    path=captures/f"window-{current['client_id']}-{current['preferred_scale']}.png"
    return capture_frame(path,(current['buffer_width'],current['buffer_height']),'RGB')


def run(command,env,artifacts,pid,probe):
    artifacts.mkdir(parents=True)
    source=document(artifacts)
    records=[]
    def query(action,*extra):return request(probe,env,artifacts,action,*extra)
    query('open',str(source))
    def window():
        return document_window(command,pid,source)
    w=until(window,'Review multipage document');assert not w['legacy']
    runtime(pid,artifacts)
    captures=Path(env['NEXTSPACE_WAYLAND_CAPTURE_DIR']);outputs=command('outputs')
    heads=[o['name'] for o in outputs]
    def capture(color,previous=None):
        value=frame(window,captures)
        if value and value['data']!=previous:
            image=value['image']
            if image.getpixel((image.width//2,image.height//2))==color:return value['data']
    try:
        assert command(f"focus {w['id']}")['ok']
        before=until(lambda:capture(COLORS[0]),'Review first page pixels')
        def move(i,scale):
            head=heads[i%len(heads)]
            assert command(f'test-scale {head} {scale} 10000')['ok'];assert command('confirm')['ok']
            output=next(o for o in command('outputs') if o['name']==head)
            assert command(f"move {w['id']} {output['x']+10} {output['y']+10}")['ok']
            until(lambda:window()['preferred_scale']==scale and window()['buffer_width']==
                  (window()['width']*scale+60)//120,'Review multipage density')
            assert command(f"focus {w['id']}")['ok']
        def record(scale,action,index,zoom,previous=None):
            state=query(action);check_state(state,index,zoom)
            data=until(lambda:capture(COLORS[index],previous),'Review selected page pixels after '+action)
            path=artifacts/f'{len(records):02d}-{scale}-{action}.png';path.write_bytes(data)
            records.append(dict(scale=scale,action=action,state=state,window=window(),capture=path.name))
            return data
        for i,scale in enumerate((120,150,180,210,240,120)):
            move(i,scale)
            before=record(scale,'state',0,'100%')
            for action,index,zoom in ACTIONS:before=record(scale,action,index,zoom,before)
        before=record(120,'next',1,'100%',before)
        before=record(120,'zoom-in',1,'200%',before)
        for i,scale in enumerate((150,180,210,240,120)):
            move(i,scale)
            before=record(scale,'state',1,'200%')
        (artifacts/'results.json').write_text(json.dumps(dict(cases=records,complete=True),indent=2)+'\n')
        print('Review TIFF pages, zoom and mixed-output density changes:49 checks PASS')
        return [dict(application='Review multipage',**row) for row in records]
    except BaseException:
        (artifacts/'failure.json').write_text(json.dumps(dict(cases=records,windows=command('windows'),state=query('state')),indent=2)+'\n')
        raise
    finally:
        for output in outputs:
            assert command(f"test-scale {output['name']} {output['scale']} 10000")['ok']
            assert command('confirm')['ok']


def run_scroll(command,env,artifacts,pid,probe,source=None):
    """Returning to the same origin must restore image and scroller pixels."""
    artifacts.mkdir(parents=True)
    if source is None:
        image=Image.new('RGB',(1600,1200));pixels=image.load()
        for y in range(image.height):
            for x in range(image.width):
                pixels[x,y]=((x//7*31+y//11*17)%256,(x//13*19+y//5*23)%256,(x//3*11+y//17*29)%256)
        source=artifacts/'scroll-pattern.png';image.save(source)
    with Image.open(source) as image:width,height=image.size
    records=[];outputs=command('outputs');captures=Path(env['NEXTSPACE_WAYLAND_CAPTURE_DIR'])
    def query(action,*extra):return request(probe,env,artifacts,action,*extra)
    def window():return document_window(command,pid,source)
    def path(scale=None):
        current=window()
        return captures/f"window-{current['client_id']}-{scale or current['preferred_scale']}.png"
    def snapshot():
        value=frame(window,captures)
        return value['image'] if value else None
    try:
        query('open',str(source))
        w=until(window,'Review large scrolling image');assert not w['legacy']
        runtime(pid,artifacts)
        assert command(f"focus {w['id']}")['ok']
        until(lambda:(state:=query('state'))['frames']==1 and state['image_path']==str(source),
            'Review scrolling document active')
        while int(query('state')['zoom'][:-1])<200:
            previous=path().stat().st_mtime_ns if path().exists() else 0
            query('zoom-in')
            until(lambda:path().exists() and path().stat().st_mtime_ns>previous,'Review zoom redraw')
        assert query('state')['image_size']=='{width = %d; height = %d}'%(2*width,2*height)
        for index,scale in enumerate((120,150,180,210,240)):
            before_window=window();target=outputs[index%len(outputs)]
            previous=path(scale).stat().st_mtime_ns if path(scale).exists() else 0
            assert command(f"test-scale {target['name']} {scale} 10000")['ok'];assert command('confirm')['ok']
            target=next(head for head in command('outputs') if head['name']==target['name'])
            assert command(f"move {w['id']} {target['x']+10} {target['y']+10}")['ok']
            until(lambda:window()['preferred_scale']==scale and window()['buffer_width']==
                (window()['width']*scale+60)//120,'Review scrolling density')
            if before_window['preferred_scale']!=scale:
                until(lambda:path().exists() and path().stat().st_mtime_ns>previous,'Review density redraw')
            assert command(f"focus {w['id']}")['ok'];current=window()
            assert command(f"pointer {current['x']+100} {current['y']+100}")['ok']
            initial=query('state');before=until(snapshot,'Review initial scroll frame')
            before.save(artifacts/f'before-{scale}.png')
            assert command('scroll 1')['ok']
            state=until(lambda:(value:=query('state')) and value['visible']!=initial['visible'] and value,
                'Review wheel changes document origin')
            scrolled=until(lambda:(value:=snapshot()) and value.tobytes()!=before.tobytes() and value,
                'Review wheel changes image pixels')
            scrolled.save(artifacts/f'scrolled-{scale}.png')
            assert command('scroll -1')['ok']
            until(lambda:query('state')['visible']==initial['visible'],'Review wheel restores document origin')
            try:
                until(lambda:(value:=snapshot()) and value.tobytes()==before.tobytes(),
                    'Review image and scroller repaint identically')
            finally:
                value=snapshot()
                if value:value.save(artifacts/f'returned-{scale}.png')
            records.append(dict(scale=scale,before=initial,scrolled=state,window=window()))
            (artifacts/'results.json').write_text(json.dumps(dict(cases=records,complete=False),indent=2)+'\n')
        (artifacts/'results.json').write_text(json.dumps(dict(cases=records,complete=True),indent=2)+'\n')
        print('Review wheel input and exact retained frame at five densities: PASS')
        return [dict(application='Review '+source.suffix[1:]+' scrolling',**row) for row in records]
    except BaseException:
        (artifacts/'failure.json').write_text(json.dumps(dict(cases=records,windows=command('windows'),
            outputs=command('outputs'),state=query('state')),indent=2)+'\n')
        raise
    finally:
        for output in outputs:
            assert command(f"test-scale {output['name']} {output['scale']} 10000")['ok'];assert command('confirm')['ok']


def run_formats(command,env,artifacts,pid,probe,source):
    """Advertised bitmap formats must retain the same scroll/density behavior."""
    from image_formats import save_formats
    artifacts.mkdir(parents=True)
    records=[]
    def close(path):
        assert request(probe,env,artifacts,'close',str(path))['closed']
        until(lambda:not any(w['pid']==pid and path.name in w['title'] and w['width']>300 and w['visible']
            for w in command('windows')),'Review document closes')
    close(source)
    for path in save_formats(source,artifacts):
        records.extend(run_scroll(command,env,artifacts/path.suffix[1:],pid,probe,path))
        close(path)
    (artifacts/'results.json').write_text(json.dumps(dict(cases=records,complete=True),indent=2)+'\n')
    return records


def panel_action(command,env,artifacts,pid,probe,action,output,scale,destination=None,cancel=False,capture_ready=None):
    """Drive the existing modal panel with native keyboard and pointer input."""
    artifacts.mkdir(parents=True)
    captures=Path(env['NEXTSPACE_WAYLAND_CAPTURE_DIR'])
    with (artifacts/'action.stderr').open('w') as errors:
        actor=subprocess.Popen([str(probe),'--review',action],env=env,
            stdout=subprocess.PIPE,stderr=errors,text=True)
        try:
            title='Save' if action=='save' else 'Open'
            def panel():
                assert actor.poll() is None,(artifacts/'action.stderr').read_text()
                return next((w for w in command('windows') if w['pid']==pid and
                    w['title']==title and w['visible'] and w['width']>300),None)
            current=until(panel,'Review real '+title+' panel')
            assert not current['legacy']
            assert command(f"move {current['id']} {output['x']+40} {output['y']+40}")['ok']
            def density():
                w=panel()
                return w if w and w['preferred_scale']==scale and tuple(w[k] for k in
                    ('buffer_width','buffer_height'))==tuple((w[k]*scale+60)//120 for k in
                    ('width','height')) else None
            current=until(density,'Review '+title+' panel density')
            assert command(f"focus {current['id']}")['ok']
            def click(x,y):
                assert command(f"pointer {current['x']+x} {current['y']+y}")['ok']
                assert command('button 272')['ok']
            def key(code,pressed):assert command(f'key {code} {int(pressed)}')['ok']
            if destination is not None:
                click(current['width']-100,current['height']-58)
                codes=dict(zip('qwertyuiopasdfghjklzxcvbnm',
                    [*range(16,26),*range(30,39),*range(44,51)]))
                codes.update(dict(zip('1234567890',range(2,12))))
                codes.update({'-':12,'/':53,'.':52,' ':57})
                # Open's browser selects an existing leaf by its basename.
                entries=(str(destination.parent)+'/',destination.name) if action=='open-panel' else (str(destination),)
                for entry in entries:
                    key(56,True);key(30,True);key(30,False);key(56,False)
                    for character in entry:
                        shifted=character.isupper() or character=='_'
                        code=codes['-' if character=='_' else character.lower()]
                        if shifted:key(42,True)
                        key(code,True);key(code,False)
                        if shifted:key(42,False)
            def captured():
                value=frame(lambda:current,captures)
                if value and (cancel or destination is None):
                    return value if capture_ready is None or capture_ready(value,current,artifacts) else None
                if value:
                    # The Save label turns black after the Name field validates.
                    bounds=tuple(v*scale//120 for v in (current['width']-72,
                        current['height']-36,current['width']-42,current['height']-20))
                    if min(lo for lo,hi in value['image'].crop(bounds).getextrema())<50:return value
            value=until(captured,'Review '+title+' panel renders its controls')
            (artifacts/'panel.png').write_bytes(value['data'])
            click(current['width']-(123 if cancel else 44),current['height']-28)
            stdout,_=actor.communicate(timeout=15)
            (artifacts/'action.log').write_text(stdout)
            assert actor.returncode==0,(stdout,(artifacts/'action.stderr').read_text())
            until(lambda:not any(w['pid']==pid and w['id']==current['id'] and w['visible']
                for w in command('windows')),'Review modal panel closes')
            state=json.loads(stdout)
            if action=='open-panel' and destination is not None and not cancel:
                # The new window's Wayland focus event can follow the modal reply.
                def opened_state():
                    value=request(probe,env,artifacts,'state')
                    return value if value['image_path']==str(destination) else None
                state=until(opened_state,'Review opened document receives native focus')
            return dict(action=action,cancelled=cancel,window=current,
                state=state,modal_reply_state=json.loads(stdout),
                native_keyboard=destination is not None,native_pointer=True)
        finally:
            if actor.poll() is None:actor.kill()
            actor.wait(timeout=5)


def saved_image(source,destination):
    """Compare every exported TIFF page against the independent source decoder."""
    errors=[]
    with Image.open(source) as original,Image.open(destination) as saved:
        assert saved.format=='TIFF',(destination,saved.format)
        pages=getattr(original,'n_frames',1)
        assert saved.n_frames==pages,(source,pages,saved.n_frames)
        for index in range(pages):
            original.seek(index);saved.seek(index)
            assert saved.size==original.size,(source,index,original.size,saved.size)
            difference=ImageChops.difference(saved.convert('RGBA'),original.convert('RGBA'))
            error=max(hi for lo,hi in difference.getextrema())
            assert error<=(1 if original.format=='JPEG' else 0),(source,index,error)
            errors.append(error)
    return dict(source=str(source),destination=str(destination),pages=len(errors),
        maximum_channel_errors=errors,header=destination.read_bytes()[:8].hex(),
        sha256=hashlib.sha256(destination.read_bytes()).hexdigest())


def run_saves(command,env,artifacts,pid,probe):
    """Save the source image, including all pages, independently of zoom or DPI."""
    from image_formats import save_formats
    artifacts.mkdir(parents=True)
    original=artifacts/'original.png'
    image=Image.new('RGB',(513,387))
    for color,box in zip(((255,0,0),(0,255,0),(0,0,255),(255,255,0)),
            ((0,0,256,193),(256,0,513,193),(0,193,256,387),(256,193,513,387))):image.paste(color,box)
    image.save(original)
    sources=[original,*save_formats(original,artifacts)]
    multipage=artifacts/'three-pages.tiff'
    pages=[Image.new('RGB',image.size,color) for color in COLORS]
    pages[0].save(multipage,save_all=True,append_images=pages[1:])
    sources.append(multipage)
    hashes={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    records=[];outputs=command('outputs')
    def query(action,*extra):return request(probe,env,artifacts,action,*extra)
    def window(source):
        return document_window(command,pid,source)
    def focus(source):
        assert command(f"focus {window(source)['id']}")['ok']
        return until(lambda:(state:=query('state'))['image_path']==str(source) and state,
            'Review source document becomes main')
    try:
        runtime(pid,artifacts)
        for index,scale in enumerate((120,150,180,210,240)):
            target=outputs[index%len(outputs)]
            assert command(f"test-scale {target['name']} {scale} 10000")['ok'] and command('confirm')['ok']
            target=next(o for o in command('outputs') if o['name']==target['name'])
            for source in sources:
                query('open',str(source));w=until(lambda:window(source),'Review source to export')
                assert command(f"move {w['id']} {target['x']+10} {target['y']+10}")['ok']
                until(lambda:window(source)['preferred_scale']==scale,'Review document export density')
                focus(source)
                if source==multipage:
                    assert query('next')['index']==1
                    assert query('zoom-in')['zoom']=='200%'
                before=query('state')
                case=artifacts/f"{scale}-{source.stem}-{source.suffix[1:]}"
                destination=artifacts/f"export-{scale}-{source.stem}-{source.suffix[1:]}.tiff"
                row=panel_action(command,env,case,pid,probe,'save',target,scale,destination)
                row.update(scale=scale,export=saved_image(source,destination))
                assert row['state']==before,(row['state'],before)
                reopened=panel_action(command,env,case/'reopen',pid,probe,'open-panel',target,scale,destination)
                assert reopened['state']['image_path']==str(destination),reopened
                assert reopened['state']['frames']==row['export']['pages'] and reopened['state']['index']==0
                assert reopened['state']['zoom']=='100%' and reopened['state']['image_size']==\
                    '{width = 513; height = 387}',reopened
                opened=until(lambda:window(destination),'Review opens the saved TIFF')
                assert command(f"move {opened['id']} {target['x']+10} {target['y']+10}")['ok']
                until(lambda:window(destination)['preferred_scale']==scale,'Review saved TIFF density')
                assert command(f"focus {opened['id']}")['ok']
                readback=[]
                for page in range(row['export']['pages']):
                    if page:assert query('next')['index']==page
                    with Image.open(source) as reference:
                        reference.seek(page);reference=reference.convert('RGB')
                    expected=[reference.getpixel((reference.width*x//4,reference.height*y//4))
                        for y in (1,3) for x in (1,3)]
                    def rendered():
                        value=frame(lambda:window(destination),Path(env['NEXTSPACE_WAYLAND_CAPTURE_DIR']))
                        if value:
                            pixels=value['image'];actual=[pixels.getpixel((pixels.width*x//4,pixels.height*y//4))
                                for y in (1,3) for x in (1,3)]
                            if all(abs(a-b)<=1 for color,ref in zip(actual,expected)
                                for a,b in zip(color,ref)):return value
                    value=until(rendered,'Review saved TIFF page pixels')
                    capture=case/f'reopened-{page}.png';capture.write_bytes(value['data'])
                    readback.append(dict(page=page,window=window(destination),capture=str(capture),samples=expected))
                row['readback']=dict(panel=reopened,pages=readback)
                assert query('close',str(destination))['closed']
                assert focus(source)==before
                records.append(row)
                if source==multipage:
                    for exists in (False,True):
                        destination=artifacts/f"cancel-{scale}-{'existing' if exists else 'new'}.tiff"
                        if exists:destination.write_bytes(b'Existing file must survive Cancel.\n')
                        payload=destination.read_bytes() if exists else None
                        row=panel_action(command,env,artifacts/f'cancel-{scale}-{int(exists)}',pid,probe,
                            'save',target,scale,destination,cancel=True)
                        assert (destination.read_bytes() if destination.exists() else None)==payload
                        assert row['state']==before
                        records.append(dict(scale=scale,existing_file=exists,destination=str(destination),**row))
                    row=panel_action(command,env,artifacts/f'open-cancel-{scale}',pid,probe,
                        'open-panel',target,scale,cancel=True)
                    assert row['state']==before
                    records.append(dict(scale=scale,**row))
                assert query('close',str(source))['closed']
            assert hashes=={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
        (artifacts/'results.json').write_text(json.dumps(dict(cases=records,source_sha256=hashes,
            complete=True,physical_display=False,full_plan_complete=False),indent=2)+'\n')
        print('Review real Save/Open panels:30 TIFF exports and reopens,10 save cancellations,5 open cancellations PASS')
        return [dict(application='Review save workflow',**row) for row in records]
    except BaseException:
        (artifacts/'failure.json').write_text(json.dumps(dict(cases=records,windows=command('windows')),
            indent=2)+'\n')
        raise
    finally:
        for output in outputs:
            assert command(f"test-scale {output['name']} {output['scale']} 10000")['ok'] and command('confirm')['ok']
