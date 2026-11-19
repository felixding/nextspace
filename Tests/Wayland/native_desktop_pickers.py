"""Ordinary input on the owned 1464x918 preview demo; no client focus helpers."""
import argparse,json,subprocess,threading,time
from pathlib import Path
from PIL import Image
from desktop_input import Desktop
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('root',type=Path)
parser.add_argument('--first-browser',choices=('chromium','firefox'),default='chromium')
args=parser.parse_args();root=args.root;desktop=Desktop(root)
command=desktop.command;click=desktop.click;key=desktop.key;capture=desktop.capture
rows=[];current='setup'
apps={'chromium':('chromium-browser','Chromium'),'firefox':('firefox-esr','firefox-esr')}

def until(read,predicate,label,timeout=12):
    end=time.monotonic()+timeout
    while True:
        value=read()
        if predicate(value):return value
        assert time.monotonic()<end,(label,value)
        time.sleep(.05)

def panel(title):
    return next((w for w in command('windows') if w['visible'] and w['title']==title),None)

def repeat_calendar(family,name):
    # Observe the complete interaction. Waiting only for the final open panel
    # previously allowed a multisecond disappearance to pass unnoticed.
    observed=[];stop=threading.Event();ready=threading.Event()
    def observe():
        try:
            while not stop.is_set():
                w=panel('Date and Time')
                observed.append(dict(at=time.monotonic(),visible=bool(w),focused=bool(w and w['focused'])))
                ready.set();stop.wait(.02)
        except BaseException as error:
            observed.append(dict(error=repr(error)));ready.set()
    worker=threading.Thread(target=observe);worker.start()
    try:
        assert ready.wait(12),'Calendar observer did not start'
        click(*points[family]['calendar'])
        time.sleep(3)
    finally:
        stop.set();worker.join(13)
    assert not worker.is_alive() and observed and all('error' not in r for r in observed),observed
    hidden=None;longest=0
    for r in observed:
        if not r['visible'] and hidden is None:hidden=r['at']
        if r['visible'] and hidden is not None:longest=max(longest,r['at']-hidden);hidden=None
    if hidden is not None:longest=max(longest,observed[-1]['at']-hidden)
    (root/(name+'-timeline.json')).write_text(json.dumps(observed,indent=2)+'\n')
    capture(name)
    save(name+'-native-panel-returns-without-long-disappearance',
         observed[-1]['visible'] and observed[-1]['focused'] and longest<.75,
         longest_hidden_seconds=longest,timeline=name+'-timeline.json')

def save(name,passed=True,**details):
    rows.append(dict(case=name,passed=passed,**details))
    (root/'ordinary-picker-ux.json').write_text(json.dumps(dict(complete=False,checks=rows),indent=2)+'\n')
    assert passed,(name,details)

def committed_paint(name,predicate):
    started=time.monotonic()
    while True:
        image=Image.open(capture(name+'-committed')).resize((1464,918))
        elapsed=time.monotonic()-started
        if predicate(image):return image,elapsed
        assert elapsed<12,(name,'visible native value did not commit',elapsed)
        time.sleep(.05)

def check_open(family,title,name):
    opened=until(lambda:panel(title),bool,name+' mapped')
    opened=until(lambda:panel(title),lambda p:p and p['focused'],name+' real keyboard focus')
    time.sleep(1.2)
    w=panel(title)
    save(name+'-stays-open-and-focused',bool(w and w['focused']),window=w)
    main=next(w for w in command('windows') if w['app_id']==apps[family][0] and w['level']==0)
    save(name+'-native-window-owner',w['parent_id']==main['id'])
    menus=until(lambda:[w for w in command('windows') if w['visible'] and w['level']==20],
                lambda m:len(m)==1 and m[0]['title']==apps[family][1],name+' owning app menu')
    if title=='Colors':
        expose_source(title,points[family]['color'],name)
        w=panel(title);assert w
    screenshot=Path(capture(name))
    if title=='Colors':
        im=Image.open(screenshot);im=im.resize((1464,918))
        box=(1220,492,1464,720) if family=='chromium' else (480,508,750,740)
        # The original shared Colors panel remembers its native placement.
        # Its own color wheel can overlap this region after an owner change.
        pixels=im.load()
        colored=sum(pixels[x,y][2]>pixels[x,y][0]+20 and pixels[x,y][2]>pixels[x,y][1]+5
                    for x in range(box[0],box[2]) for y in range(box[1],box[3])
                    if not (w['x']<=x<w['x']+w['width'] and w['y']<=y<w['y']+w['height']))
        save(name+'-no-browser-gradient-popup',colored<100,colored_pixels_below_well=colored)
    return w

def close_panel(title,method='escape'):
    w=panel(title)
    assert w,title+' exists before close'
    if method=='outside':click(300,254)
    elif method=='close':click(w['x']+w['width']-11,w['y']+11)
    else:key(28 if method=='return' else 1)
    until(lambda:panel(title),lambda w:not w,title+' closes normally')
    time.sleep(.25)

def expose_source(title,point,name):
    w=panel(title);assert w
    def covered(window):
        return (window['x']<=point[0]<window['x']+window['width'] and
                window['y']<=point[1]<window['y']+window['height'])
    head=command('outputs')[0]
    menus=[v for v in command('windows') if v['level']==20 and v['style']==0 and v['width']>1
           and v['x']>=head['x'] and v['x']+v['width']<=head['x']+head['width']]
    def overlaps(menu):
        return (w['x']<menu['x']+menu['width'] and menu['x']<w['x']+w['width'] and
                w['y']<menu['y']+menu['height'] and menu['y']<w['y']+w['height'])
    if covered(w) or any(overlaps(v) for v in menus if v['visible']):
        x=max([head['work_x']]+[v['x']+v['width']+8 for v in menus])
        y=head['work_y']+24
        assert x+w['width']<=head['work_x']+head['work_width']
        assert y+w['height']<=head['work_y']+head['work_height']
        assert command(f"move {w['id']} {x} {y}")['ok']
        until(lambda:panel(title),lambda v:v and v['x']==x and v['y']==y and not covered(v),
              name+' original browser control exposed')
        capture(name+'-source-exposed')
    assert not covered(panel(title)),name+' would click the panel instead of its source control'

def black_swatch(window,name):
    # The shared UI library owns palette layout. Locate its visible filled
    # black swatch instead of copying fixed screen coordinates into the test.
    image=Image.open(root/(name+'.png')).resize((1464,918))
    for y in range(window['y']+window['height']-32,window['y']+window['height']-12):
        for x in range(window['x']+6,window['x']+window['width']-8):
            if all(max(image.getpixel((x+dx,y+dy)))<40
                   for dx in range(-2,3) for dy in range(-2,3)):
                save(name+'-visible-black-swatch',True,point=[x,y])
                return x,y
    raise AssertionError('Original native palette has no visible filled black swatch')

def color_fill_point(image,anchor):
    # The click can land on the well's bevel. Observe the fixture's visible
    # blue fill before selecting black, then sample its interior at either
    # density rather than treating that bevel as an uncommitted model.
    x,y=anchor
    filled=[(px,py) for py in range(max(0,y-40),min(image.height,y+40))
            for px in range(max(0,x-64),min(image.width,x+64))
            if image.getpixel((px,py))[2]>image.getpixel((px,py))[0]+40 and
               image.getpixel((px,py))[2]>image.getpixel((px,py))[1]+20]
    assert len(filled)>10,'Fixture colour well has no visible blue fill'
    return ((min(p[0] for p in filled)+max(p[0] for p in filled))//2,
            (min(p[1] for p in filled)+max(p[1] for p in filled))//2)

points={'chromium':dict(text=(1200,254),color=(1420,475),calendar=(1155,475)),
        'firefox':dict(text=(300,254),color=(525,490),calendar=(245,490))}
try:
    windows=command('windows')
    for family,x in [('firefox',0),('chromium',900)]:
        w=next(w for w in windows if w['app_id']==apps[family][0] and w['level']==0)
        assert command('move %d %d 24'%(w['id'],x))['ok']
    time.sleep(.5)
    # Native intrinsic metrics can move the well within this row. Locate its
    # actual visible fill before the first click, without focusing either app.
    initial=Image.open(capture('ordinary-initial-controls')).resize((1464,918))
    for family in points:
        points[family]['color']=color_fill_point(initial,points[family]['color'])
    (root/'ordinary-control-targets.json').write_text(json.dumps(points,indent=2)+'\n')
    order=['firefox','chromium'] if args.first_browser=='firefox' else ['chromium','firefox']
    for family in order:
        other=next(name for name in order if name!=family)
        for kind,title in [('color','Colors'),('calendar','Date and Time')]:
            for iteration in range(4):
                current='%s-%s-cross-app-%d'%(family,kind,iteration)
                # Actual first click on the exposed control in an inactive app.
                # No compositor focus command, neutral click or DOM focus call.
                click(*points[other]['text']);time.sleep(.4)
                click(*points[family][kind]);check_open(family,title,current)
                close_panel(title,'close' if kind=='color' or iteration==0 else 'return' if iteration==1 else 'outside' if iteration==2 else 'escape')
                save(current+'-ordinary-close',True)
            current=family+'-'+kind+'-immediate-reopen'
            click(*points[family][kind]);check_open(family,title,current)
            if kind=='color':
                opened=(root/(family+'-hook.log')).read_text().count('opened through original')
                for repeated in range(2):
                    current=family+'-color-repeat-while-open-'+str(repeated)
                    expose_source(title,points[family][kind],current)
                    click(*points[family][kind]);check_open(family,title,current)
                    save(current+'-same-original-session',
                         (root/(family+'-hook.log')).read_text().count('opened through original')==opened)
            else:
                for repeated in range(2):
                    current=family+'-calendar-repeat-while-open-'+str(repeated)
                    expose_source(title,points[family][kind],current)
                    repeat_calendar(family,current)
            close_panel(title,'close')
            current=family+'-'+kind+'-from-own-field'
            click(*points[family]['text']);click(*points[family][kind]);check_open(family,title,current)
            close_panel(title,'close' if kind=='color' else 'return')
            current=family+'-'+kind+'-keyboard-open'
            x,y=points[family][kind]
            assert command('pointer %d %d'%(x,y))['ok']
            assert command('button 272 1')['ok'];time.sleep(.08)
            assert command('pointer %d %d'%(x,y+48))['ok']
            assert command('button 272 0')['ok'];time.sleep(.2)
            save(current+'-cancelled-pointer-gesture',not panel(title))
            main=next(w for w in command('windows') if w['app_id']==apps[family][0] and w['level']==0)
            lifecycle=(root/(family+'-hook.log')).read_text()
            save(current+'-browser-keyboard-focus',main['focused'],
                 completed_color_sessions=lifecycle.count('completed through original'),
                 opened_color_sessions=lifecycle.count('opened through original'))
            key(57);check_open(family,title,current)
            close_panel(title,'close' if kind=='color' else 'return')
        current=family+'-native-calendar-selection'
        click(*points[family]['text']);time.sleep(.3)
        before=Image.open(capture(current+'-before')).resize((1464,918))
        click(*points[family]['calendar']);check_open(family,'Date and Time',current)
        key(106);close_panel('Date and Time','return')
        click(*points[family]['text']);time.sleep(.3)
        box=(995,467,1080,482) if family=='chromium' else (95,480,175,496)
        after,elapsed=committed_paint(current,lambda image:before.crop(box).tobytes()!=image.crop(box).tobytes())
        save(current+'-inline-date-reflects-native-calendar',True,paint_wait_seconds=elapsed)
        current=family+'-native-color-selection'
        before=Image.open(capture(current+'-before')).resize((1464,918))
        filled_point=color_fill_point(before,points[family]['color'])
        click(*points[family]['color']);w=check_open(family,'Colors',current)
        click(*black_swatch(w,current));time.sleep(1)
        close_panel('Colors','close')
        im,elapsed=committed_paint(current,lambda image:max(image.getpixel(filled_point))<40)
        rgb=im.getpixel(filled_point)
        save(current+'-well-reflects-native-palette',max(rgb)<40,well_rgb=rgb,point=filled_point,paint_wait_seconds=elapsed)
    # Put the actual source row near the screen bottom. The old clamped
    # native panel covered the caption, so a repeat click selected a day.
    # Check the whole row, not just a convenient uncovered button edge.
    for family in order:
        current=family+'-bottom-edge-calendar-repeat'
        main=next(w for w in command('windows') if w['app_id']==apps[family][0] and w['level']==0)
        assert command('move %d %d 350'%(main['id'],main['x']))['ok']
        dy=350-main['y'];x,y=points[family]['calendar'];x-=24;y+=dy
        time.sleep(.4)
        # Match both focus and panel visibility in the date comparison. An
        # open calendar's native shadow can cross the source row even though
        # its actual window leaves the caption exposed.
        click(points[family]['text'][0],points[family]['text'][1]+dy)
        before=Image.open(capture(current+'-before')).resize((1464,918))
        click(x,y);w=check_open(family,'Date and Time',current)
        save(current+'-source-row-remains-exposed',w['y']+w['height']<=y-8 or w['y']>=y+8,window=w,caption_point=[x,y])
        click(x,y);time.sleep(.4)
        if panel('Date and Time'):close_panel('Date and Time','return')
        click(points[family]['text'][0],points[family]['text'][1]+dy)
        box=(995,467+dy,1080,482+dy) if family=='chromium' else (95,480+dy,175,496+dy)
        # Both pictures now have the same source focus and no open panel.
        after=Image.open(capture(current+'-after')).resize((1464,918))
        save(current+'-caption-click-does-not-edit-date',before.crop(box).tobytes()==after.crop(box).tobytes())
        click(x,y);check_open(family,'Date and Time',current+'-reopen');close_panel('Date and Time','return')
        assert command('move %d %d %d'%(main['id'],main['x'],main['y']))['ok']
        time.sleep(.3)
    for family in ['firefox','chromium','firefox']:
        current=family+'-visible-color-panel-handoff'
        w=panel('Colors');x,y=points[family]['color']
        if w and w['x']<=x<w['x']+w['width'] and w['y']<=y<w['y']+w['height']:
            # Arrange the fixture so the next browser control is exposed.
            # Moving a window does not alter keyboard focus or input serials.
            assert command('move %d 351 106'%w['id'])['ok']
        click(*points[family]['color']);check_open(family,'Colors',current)
        save(current+'-one-shared-panel',sum(w['visible'] and w['title']=='Colors' for w in command('windows'))==1)
    close_panel('Colors','close')
    portal=next(json.loads(line)['pid'] for line in (root/'file-portal.stdout').read_text().splitlines()
                if line.startswith('{') and json.loads(line).get('event')=='ready')
    for family,point in [('chromium',(1010,511)),('firefox',(110,529))]:
        current=family+'-native-file-cancel'
        # Leave the original color session alive while a different native
        # process deactivates its host. Closing Colors first misses AppKit's
        # remembered inactive-panel list.
        click(*points[family]['color'])
        until(lambda:panel('Colors'),lambda w:w and w['focused'],current+' color session before file panel')
        click(*points[family]['text']);click(*point)
        def files():
            return next((w for w in command('windows') if w['pid']==portal and w['visible'] and w['accepts_focus']),None)
        w=until(files,lambda w:w and w['focused'],current+' original modal focus')
        time.sleep(1.2);w=files()
        save(current+'-focus-retained',bool(w and w['focused']),window=w)
        main=next(w for w in command('windows') if w['app_id']==apps[family][0] and w['level']==0)
        save(current+'-original-window-owner',w['parent_id']==main['id'])
        capture(current);click(w['x']+w['width']-126,w['y']+w['height']-29)
        until(files,lambda w:not w,current+' native cancellation')
        save(current+'-cancel-closes',True)
        save(current+'-old-color-panel-hidden',not panel('Colors'))
        other=next(name for name in apps if name!=family)
        current=other+'-calendar-after-foreign-file-cancel'
        click(*points[other]['calendar']);check_open(other,'Date and Time',current)
        save(current+'-does-not-revive-foreign-color-panel',not panel('Colors'))
        close_panel('Date and Time','close')
        click(*points[family]['color'])
        until(lambda:panel('Colors'),lambda w:w and w['focused'],current+' original color session reopens')
        close_panel('Colors','close')
    (root/'ordinary-picker-ux.json').write_text(json.dumps(dict(complete=True,checks=rows),indent=2)+'\n')
    print(json.dumps(dict(complete=True,checks=len(rows))))
except BaseException as error:
    # Preserve the live portal state before session teardown can cancel a
    # pending request. A cancellation printed by cleanup is not evidence that
    # the chooser cancelled itself during the failed interaction.
    diagnostic=dict(case=current,time=time.time(),error=repr(error))
    for name in ('file-portal.stdout','file-portal.stderr','portal-frontend.stderr'):
        try:(root/('ordinary-picker-ux-failure-'+name)).write_bytes((root/name).read_bytes())
        except OSError:pass
    if 'native-file' in current and 'portal' in globals():
        try:
            process=Path('/proc')/str(portal)
            diagnostic['portal_cmdline']=process.joinpath('cmdline').read_bytes().replace(b'\0',b' ').decode()
            diagnostic['portal_status']=process.joinpath('status').read_text()
            trace=subprocess.run(['sudo','-n','gdb','-q','-batch','-p',str(portal),
                '-ex','set pagination off','-ex','thread apply all bt','-ex','detach'],
                capture_output=True,text=True,timeout=8)
            (root/'ordinary-picker-ux-failure-portal-stack.txt').write_text(trace.stdout+trace.stderr)
            diagnostic['portal_stack_exit']=trace.returncode
        except Exception as failure:diagnostic['portal_stack_error']=repr(failure)
    (root/'ordinary-picker-ux-failure-live.json').write_text(json.dumps(diagnostic,indent=2)+'\n')
    try:
        host=next(w['pid'] for w in command('windows') if w['title'] in ('Colors','Date and Time') and w['visible'])
        # Read the owned host's activation state after failure, before teardown
        # can hide the distinction between an inactive presentation and revival.
        queries=['set pagination off','thread apply all bt','set $nxs_app=*(void **)&NSApp',
            'set $nxs_selector=(void *)sel_registerName("isActive")',
            'set $nxs_imp=(void *)objc_msg_lookup($nxs_app,$nxs_selector)',
            'p ((unsigned char(*)(void*,void*))$nxs_imp)($nxs_app,$nxs_selector)',
            'set $nxs_selector=(void *)sel_registerName("keyWindow")',
            'set $nxs_imp=(void *)objc_msg_lookup($nxs_app,$nxs_selector)',
            'set $nxs_window=((void*(*)(void*,void*))$nxs_imp)($nxs_app,$nxs_selector)',
            'p $nxs_window',
            'set $nxs_selector=(void *)sel_registerName("firstResponder")',
            'set $nxs_imp=(void *)objc_msg_lookup($nxs_window,$nxs_selector)',
            'set $nxs_responder=((void*(*)(void*,void*))$nxs_imp)($nxs_window,$nxs_selector)',
            'p (char *)class_getName((void *)object_getClass($nxs_responder))',
            'set $nxs_server=(void *)GSCurrentServer()',
            'set $nxs_class=(void *)objc_getClass("WaylandServer")',
            'set $nxs_ivar=(void *)class_getInstanceVariable($nxs_class,"wlconfig")',
            'set $nxs_offset=(long)ivar_getOffset($nxs_ivar)',
            'set $nxs_config=*(void **)((char *)$nxs_server+$nxs_offset)',
            'p ((WaylandConfig *)$nxs_config)->keyboard_focus',
            'p ((WaylandConfig *)$nxs_config)->deactivation_sync',
            'p (int)WaylandHasPendingActivation($nxs_config)','detach']
        trace=subprocess.run(['sudo','-n','gdb','-q','-batch','-p',str(host),
            *[value for query in queries for value in ('-ex',query)]],
            capture_output=True,text=True,timeout=10)
        (root/'ordinary-picker-ux-failure-native-state.txt').write_text(trace.stdout+trace.stderr)
    except Exception as failure:
        (root/'ordinary-picker-ux-failure-native-state.txt').write_text(repr(failure)+'\n')
    try:(root/'ordinary-picker-ux-failure-windows.json').write_text(json.dumps(command('windows'),indent=2)+'\n')
    except Exception:pass
    try:capture('ordinary-picker-ux-failure')
    except Exception:pass
    rows.append(dict(case=current,passed=False,error=repr(error)))
    (root/'ordinary-picker-ux.json').write_text(json.dumps(dict(complete=False,checks=rows),indent=2)+'\n')
    raise
