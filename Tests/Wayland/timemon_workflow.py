"""Exercise real TimeMon preferences, retained text and native color transfers."""
import json
import math
from pathlib import Path
import subprocess
import time
from PIL import Image
from drag import events
from gnustep import headless_session, pasteboard_storage, process_runtime
from integration import until
from timemon_pause import application_action
from timemon_static_artwork import open_panel


def run(compositor, application, probe, drag_probe, pasteboard, pasteboard_probe, artifacts):
    artifacts.mkdir(parents=True)
    applications=[];actors=[];cases=[];app=None;drag=None;load=None;app_directory=None
    with headless_session(compositor,artifacts/'native') as (env,command), \
            pasteboard_storage(pasteboard,pasteboard_probe,env,artifacts):
        def key(code):
            assert command(f'key {code} 1')['ok'] and command(f'key {code} 0')['ok']
        def shortcut(code):
            assert command('key 56 1')['ok'];key(code);assert command('key 56 0')['ok']
        def query(action='controls'):
            assert app.poll() is None,'TimeMon exited during its workflow'
            return application_action(probe,env,artifacts,action)
        def preferences(state):
            return next(w for w in state['windows'] if w['title']=='Preferences' and w['visible'])
        def window(metadata):
            return next(w for w in command('windows') if w['pid']==app.pid and w['client_id']==metadata['window'])
        def capture(w,density):
            path=app_directory/'native/captures'/f"window-{w['client_id']}-{density}.png"
            try:
                with Image.open(path) as image:pixels=image.convert('RGBA')
            except OSError:return None
            return pixels if pixels.size==(w['buffer_width'],w['buffer_height']) else None
        def ready_frame(metadata,density):
            def ready():
                w=window(metadata)
                if w['preferred_scale']!=density:return False
                pixels=capture(w,density)
                return (w,pixels) if pixels is not None else False
            return until(ready,'TimeMon preferences backing density')
        def launch(label):
            nonlocal app,app_directory
            app_directory=artifacts/label;(app_directory/'native/captures').mkdir(parents=True)
            with (app_directory/'application.log').open('w') as log:
                app=subprocess.Popen([str(application),'-GSBackend','libgnustep-wayland','-GSTheme','NextSpace',
                    '-NSUseRunningCopy','NO'],env=dict(env,NEXTSPACE_WAYLAND_CAPTURE_DIR=str(app_directory/'native/captures')),
                    stdout=log,stderr=log)
            applications.append(app)
            until(lambda:query('state'),'TimeMon registration')
            open_panel(command,app,app_directory,'Preferences',1)
            return query()
        def quit_app(label):
            state=query();w=window(preferences(state));assert command(f"focus {w['id']}")['ok']
            runtime=process_runtime(app.pid);shortcut(16);app.wait(timeout=10);assert app.returncode==0
            until(lambda:not any(w['pid']==app.pid for w in command('windows')),'TimeMon normal quit removes its surfaces')
            actors.append(dict(label=label,exit_code=app.returncode,**runtime))
            return state
        def edit(index,text,expected):
            state=query();pref=preferences(state);w=window(pref)
            fields=sorted(pref['fields'],key=lambda f:f['base'][0]);field=fields[index]
            assert field['has_delegate'] and field['control_editing_delegate']
            x,y,width,height=field['base']
            assert command(f"pointer {int(w['x']+x+width/2)} {int(w['y']+w['height']-y-height/2)}")['ok']
            assert command('button 272')['ok'];shortcut(30)
            codes={str(i):i+1 for i in range(1,10)};codes.update({'0':11,'.':52,'-':12})
            for char in text:key(codes[char])
            key(15)
            setting=('UpdatePeriod','LagFactor','LayerFactor')[index]
            def changed():
                current=query();fields=sorted(preferences(current)['fields'],key=lambda f:f['base'][0])
                return current if math.isclose(float(fields[index]['value']),expected,abs_tol=.000001) and current['saved_defaults'].get(setting)==text else False
            return until(changed,'TimeMon field and saved '+setting)
        def scroll_roundtrip(pref,density):
            scroll,=pref['scroll_views'];entry=scroll['clip'];top=scroll['document'][1]
            x,y,width,height=scroll['base'];w,_=ready_frame(pref,density);factor=density/120
            assert command(f"pointer {int(w['x']+x+width/2)} {int(w['y']+w['height']-y-height/2)}")['ok']
            assert command('scroll 1000')['ok']
            pref=until(lambda:(s if math.isclose((s:=preferences(query()))['scroll_views'][0]['clip'][1],top,abs_tol=.000001) else None),'TimeMon README top boundary')
            w,before=ready_frame(pref,density)
            box=(math.floor(x*factor),math.floor((w['height']-y-height)*factor),
                 math.ceil((x+width)*factor),math.ceil((w['height']-y)*factor))
            expected=before.crop(box);expected.save(artifacts/f'readme-{density}-before.png')
            assert command(f"pointer {int(w['x']+x+width/2)} {int(w['y']+w['height']-y-height/2)}")['ok']
            assert command('scroll -1000')['ok']
            changed=until(lambda:(s if (s:=preferences(query()))['scroll_views'][0]['clip'][1]>top else None),'TimeMon README scrolls')
            def scrolled():
                pixels=capture(window(changed),density)
                return pixels if pixels is not None and pixels.crop(box).tobytes()!=expected.tobytes() else False
            until(scrolled,'TimeMon README submits scrolled pixels').crop(box).save(artifacts/f'readme-{density}-scrolled.png')
            assert command('scroll 1000')['ok']
            until(lambda:math.isclose(preferences(query())['scroll_views'][0]['clip'][1],top,abs_tol=.000001),'TimeMon README returns to top')
            def restored():
                pixels=capture(window(pref),density)
                return pixels if pixels is not None and pixels.crop(box).tobytes()==expected.tobytes() else False
            until(restored,'TimeMon README repaints identical text and scroller').crop(box).save(artifacts/f'readme-{density}-returned.png')
            return dict(crop=box,entry_clip=entry,document=scroll['document'],top=top,
                        scrolled_clip=changed['scroll_views'][0]['clip'],returned_pixels_identical=True)
        def named(title):
            assert drag.poll() is None,'Native color probe exited'
            return next((w for w in command('windows') if w['pid']==drag.pid and w['title']==title and w['visible']),None)
        def drag_events(kind):return [v for v in events(artifacts/'color-drag.log') if v['event']==kind]
        def hover(target,x,y):
            # The AppKit began callback precedes wl_data_device.start_drag.
            # Moving first can leave the later compositor drag at its source.
            until(lambda:command('drag-state')['active'],'Compositor receives the native color drag')
            assert command(f'pointer {x} {y}')['ok']
            return until(lambda:(d if (d:=command('drag-state'))['active'] and d['target']==target['id'] and d['action']==1 else None),
                         'Native color copy negotiation')
        def palette(state):return preferences(state)['colors'][0]['cells']
        def incoming(pref,density,cancel):
            before=query();source=named('NativeDragSource');target=window(pref)
            count=len(drag_events('drag-end'));begins=len(drag_events('drag-begin'))
            assert command(f"pointer {source['x']+50} {source['y']+100}")['ok'] and command('button 272 1')['ok']
            until(lambda:len(drag_events('drag-begin'))>begins,'Color source starts its AppKit drag')
            x,y,width,height=palette(before)[0]['base']
            negotiated=hover(target,int(target['x']+x+width/2),int(target['y']+target['height']-y-height/2))
            if cancel:key(1)
            assert command('button 272 0')['ok']
            completion=until(lambda:(v[-1] if len(v:=drag_events('drag-end'))>count else None),'Color source completes')
            assert completion['action']==(0 if cancel else 1)
            def updated():
                state=query();cells=palette(state)
                if cancel:return state if cells==palette(before) else False
                return state if max(abs(a-b) for a,b in zip(cells[0]['rgba'],(.2,.4,.6,1)))<.00001 else False
            after=until(updated,'TimeMon retains or accepts the color')
            assert palette(after)[1:]==palette(before)[1:]
            if cancel:assert after['saved_defaults'].get('IdleColor')==before['saved_defaults'].get('IdleColor')
            else:
                # TimeMon keeps the dropped alpha in defaults while its swatch
                # deliberately paints an opaque background for the caption.
                assert [float(v) for v in after['saved_defaults']['IdleColor'].split()]==[.2,.4,.6,.5]
                def painted():
                    w=window(pref);pixels=capture(w,density)
                    if pixels is None:return False
                    sample=(math.floor((x+width-5)*density/120+.5),math.floor((w['height']-y-height/2)*density/120+.5))
                    return (pixels,sample) if max(abs(a-b) for a,b in zip(pixels.getpixel(sample),(51,102,153,255)))<=1 else False
                pixels,sample=until(painted,'TimeMon paints its dropped color at native density')
                pixels.save(artifacts/f'color-{density}.png')
            return dict(cancelled=cancel,source=source,target=target,negotiated=negotiated,completion=completion,
                        saved_color=after['saved_defaults'].get('IdleColor'))
        def outgoing(pref):
            state=query();source=window(pref);target=named('NativeDragTarget');cell=palette(state)[0];x,y,width,height=cell['base']
            start=(int(source['x']+x+width/2),int(source['y']+source['height']-y-height/2));count=len(drag_events('drop'))
            assert command(f'pointer {start[0]} {start[1]}')['ok'] and command('button 272 1')['ok']
            assert command(f'pointer {start[0]+12} {start[1]+8}')['ok']
            until(lambda:command('drag-state')['active'],'TimeMon starts its real color drag')
            negotiated=hover(target,target['x']+70,target['y']+100)
            assert command('button 272 0')['ok']
            drop=until(lambda:(v[-1] if len(v:=drag_events('drop'))>count else None),'Native receiver decodes the TimeMon color')
            assert not drop['local'] and max(abs(a-b) for a,b in zip(drop['rgba'],cell['rgba']))<.00001
            until(lambda:not command('drag-state')['active'],'TimeMon color drag ends')
            assert palette(query())==palette(state)
            return dict(source=source,target=target,negotiated=negotiated,drop=drop)
        def icon(paused):
            w=next(w for w in command('windows') if w['pid']==app.pid and w['style'] & 64)
            pixels=capture(w,w['preferred_scale'])
            if pixels is None:return False
            red=any(r>g+50 and r>b+50 for r,g,b,a in pixels.getdata())
            return pixels if red==paused else False
        try:
            initial=launch('initial')
            with (artifacts/'initial-controls.json').open('w') as f:json.dump(initial,f,indent=2)
            pref=preferences(initial);assert len(pref['fields'])==3 and len(pref['colors'])==1
            assert pref['colors'][0]['dragged_types']==['NSColorPboardType']
            target_name=command('outputs')[0]['name'];other_name=command('outputs')[1]['name']
            (artifacts/'color-captures').mkdir()
            with (artifacts/'color-drag.log').open('w') as log,(artifacts/'color-drag.stderr').open('w') as error:
                drag=subprocess.Popen([str(drag_probe),'-GSBackend','libgnustep-wayland','-GSTheme','NextSpace',
                    '-DragSource','YES','-SameClient','YES','-ColorDrag','YES','-GenericDrag','YES'],
                    env=dict(env,NEXTSPACE_WAYLAND_CAPTURE_DIR=str(artifacts/'color-captures')),stdout=log,stderr=error)
            until(lambda:named('NativeDragSource') and named('NativeDragTarget'),'Native color source and target')
            for index,density in enumerate((120,150,180,210,240)):
                for name,value in ((target_name,density),(other_name,120)):
                    assert command(f'test-scale {name} {value} 10000')['ok'] and command('confirm')['ok']
                target=next(o for o in command('outputs') if o['name']==target_name);other=next(o for o in command('outputs') if o['name']==other_name)
                pref=preferences(query());w=window(pref)
                assert command(f"move {w['id']} {target['x']+100} {target['y']+100}")['ok']
                for title,offset in [('NativeDragSource',300),('NativeDragTarget',800)]:
                    p=named(title);assert command(f"move {p['id']} {other['x']+offset} {other['y']+100}")['ok']
                w,_=ready_frame(pref,density);assert not w['legacy'] and (w['width'],w['height'])==(359,414)
                for field,text in enumerate((f'{(index+2)/10:.1f}',str(index+2),str(index+4))):state=edit(field,text,float(text))
                pref=preferences(state);scroll=scroll_roundtrip(pref,density)
                cancelled=incoming(pref,density,True);dropped=incoming(pref,density,False);exported=outgoing(pref)
                cases.append(dict(scale=density,window=w,saved_defaults=query()['saved_defaults'],scroll=scroll,
                                  cancelled_color=cancelled,incoming_color=dropped,outgoing_color=exported))
            drag_runtime=process_runtime(drag.pid);drag.terminate();drag.wait(timeout=5)
            saved=quit_app('saved-settings')
            restored=launch('restart')
            expected=['0.6','6','8'];assert [f['value'] for f in sorted(preferences(restored)['fields'],key=lambda f:f['base'][0])]==expected
            assert max(abs(a-b) for a,b in zip(palette(restored)[0]['rgba'],(.2,.4,.6,1)))<.00001
            w=window(preferences(restored));assert command(f"focus {w['id']}")['ok'];shortcut(25)
            paused=until(lambda:icon(True),'TimeMon pauses through its keyboard shortcut')
            paused.save(artifacts/'paused-before-edit.png')
            edit(0,'0.3',.3)
            load=subprocess.Popen(['yes'],stdout=subprocess.DEVNULL)
            deadline=time.monotonic()+.7;samples=[]
            def frozen():
                pixels=icon(True)
                assert pixels is not False and pixels.tobytes()==paused.tobytes(),'Editing a paused period resumed the graph'
                samples.append(time.monotonic());return time.monotonic()>=deadline
            until(frozen,'TimeMon remains paused after its period is edited under load')
            paused.save(artifacts/'paused-after-edit.png');shortcut(25)
            resumed=until(lambda:icon(False),'TimeMon resumes through its keyboard shortcut')
            resumed.save(artifacts/'resumed-after-edit.png')
            def changed():
                pixels=icon(False)
                return pixels if pixels is not False and pixels.tobytes()!=resumed.tobytes() else False
            until(changed,'TimeMon uses the edited period after resuming').save(artifacts/'updated-after-edit.png')
            paused_period=dict(passed=True,saved_period=query()['saved_defaults']['UpdatePeriod'],
                frozen_seconds=samples[-1]-samples[0],stable_samples=len(samples),load_runtime=process_runtime(load.pid))
            load.terminate();load.wait(timeout=5)
            for field,minimum in enumerate((.1,1,4)):minimum_state=edit(field,'0',minimum)
            minimum_saved=quit_app('minimum-settings');minimum_restored=launch('minimum-restart')
            assert [float(f['value']) for f in sorted(preferences(minimum_restored)['fields'],key=lambda f:f['base'][0])]==[.1,1,4]
            quit_app('minimum-restart')
        except BaseException:
            (artifacts/'failure.json').write_text(json.dumps(dict(windows=command('windows'),
                drag=command('drag-state'),completed_cases=cases),indent=2)+'\n')
            raise
        finally:
            command('button 272 0')
            for process in [load,drag,*applications]:
                if process and process.poll() is None:process.terminate();process.wait(timeout=5)
    result=dict(passed=True,cases=cases,application_actors=actors,drag_runtime=drag_runtime,
        initial_state=initial,saved_state=saved,restored_state=restored,minimum_saved_state=minimum_saved,
        minimum_restored_state=minimum_restored,normal_keyboard_quits=len(actors),all_processes_reaped=True,
        timing_edits=19,cancelled_color_drags=5,incoming_color_drags=5,outgoing_color_drags=5,
        readme_scroll_roundtrips=5,paused_period_update=paused_period,full_plan_complete=False)
    (artifacts/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print('TimeMon workflow: timing edits/restarts, five retained README frames and fifteen real color drags PASS.')
    return result
