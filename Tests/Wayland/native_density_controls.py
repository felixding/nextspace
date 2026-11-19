"""Compare browser controls and real native editing at the display density."""
import argparse
import json
import math
from pathlib import Path
import sys
import time

from native_number_fields import ChromiumNumbers


class DensityFixture(ChromiumNumbers):
    def __init__(self, root, family, port, expected_scale=2, page='native-density-controls.html', title='Native density controls', report='density-checks.json'):
        self.root=Path(root);self.family=family;self.results=[];started=time.monotonic()
        self.report_path=self.root/report
        url=(Path('/workspace/Tests/Wayland')/page).resolve().as_uri()+'?trial='+str(time.monotonic_ns())
        if family=='chromium':
            target=next(v for v in self.cdp('Target.getTargets',target=False)['targetInfos'] if v['type']=='page')
            self.session=self.cdp('Target.attachToTarget',dict(targetId=target['targetId'],flatten=True),False)['sessionId']
            self.cdp('Page.navigate',dict(url=url))
            # A preceding command test can leave another owned tab active.
            # Logical DOM focus in a background target is not seat focus.
            self.cdp('Target.activateTarget',dict(targetId=target['targetId']),False)
            window=self.cdp('Browser.getWindowForTarget',dict(targetId=target['targetId']))
            self.browser_window_id=window['windowId']
            self.cdp('Browser.setWindowBounds',dict(windowId=window['windowId'],bounds=dict(width=700,height=500)))
        else:
            sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Experiments/FirefoxNativeUI'))
            from marionette import Marionette
            self.driver=Marionette(port,timeout=90);self.driver.command('WebDriver:NewSession',{})
            self.driver.connection.settimeout(20)
            # WebDriver navigation includes cold native/font initialization;
            # physical editing and interaction assertions keep their own limit.
            self.driver.connection.settimeout(90)
            try:self.driver.command('WebDriver:Navigate',dict(url=url))
            finally:self.driver.connection.settimeout(20)
            self.driver.command('WebDriver:SetWindowRect',dict(width=700,height=500,x=0,y=0))
        self.until(lambda:self.js('location.href=== '+json.dumps(url)+'&&document.readyState==="complete"&&document.title==='+json.dumps(title)),'fresh density document',timeout=90)
        self.until(lambda:self.js('outerWidth<=710&&outerHeight<=510'),'window fits owned display')
        self.pid=json.loads((self.root/'launch.json').read_text())['pids'][-1]
        self.window=next(w for w in self.command('windows') if w['pid']==self.pid and w['level']==0 and title in w['title'])
        assert self.command('focus '+str(self.window['id']))['ok']
        self.scale=self.js('devicePixelRatio')
        self.check('browser-uses-requested-display-density',abs(self.scale-expected_scale)<(1/60 if family=='firefox' else .00001))
        self.output_scale=self.command('outputs')[0]['scale']/120
        # A detached native menu can overlap the fixture's default (0,0)
        # window. Arrange the owned window so physical control trials reach
        # their actual visible targets rather than a covering menu row.
        menus=[w for w in self.command('windows') if w['visible'] and w['level']==20]
        if menus:
            right=max(w['x']+w['width'] for w in menus)+16
            head=self.command('outputs')[0]
            available=head['work_x']+head['work_width']-right
            if self.window['width']>available:
                width=available-(self.window['width']-self.window['surface_width'])
                assert width>=400,'owned test display cannot fit browser beside its native menu'
                if family=='chromium':
                    self.cdp('Browser.setWindowBounds',dict(windowId=self.browser_window_id,bounds=dict(width=width,height=500)))
                else:self.driver.command('WebDriver:SetWindowRect',dict(width=width,height=500))
                self.until(lambda:self.js('outerWidth')<=width+2,'browser fits beside detached menu')
            assert self.command(f"move {self.window['id']} {right} {self.window['y']}")['ok']
        self.update_origin()
        (self.root/'density-setup.json').write_text(json.dumps(dict(family=family,scale=self.scale,elapsed=time.monotonic()-started))+'\n')

    def update_origin(self):
        # Browser chrome can finish a density-driven relayout after the page
        # becomes ready. Read the original content origin at each operation.
        self.window=next(w for w in self.command('windows') if w['id']==self.window['id'] and w['pid']==self.pid)
        # innerHeight rounds to a CSS integer and can lose a device pixel.
        # The original visual viewport preserves its fractional CSS extent;
        # recover its integral device extent before deriving the screen edge.
        self.origin_pixels=((self.window['x']+self.window['frame_left'])*self.output_scale,
            (self.window['y']+self.window['frame_top']+self.window['surface_height'])*self.output_scale
            -math.floor(self.js('visualViewport.height')*self.scale+.5))
        self.origin_pixels=tuple(math.floor(v+.5) for v in self.origin_pixels)
        key=self.origin_key()
        if getattr(self,'registered_origin',None) and self.registered_origin[0]==key:
            self.origin_pixels=self.registered_origin[1]
        if self.family=='firefox':
            # Gecko retains a fractional content origin even when outer
            # surface bounds are integral. Use its original screen accessor.
            self.origin_pixels=tuple(v*self.scale for v in self.js('[mozInnerScreenX,mozInnerScreenY]'))

    def origin_key(self):
        return tuple(self.window[k] for k in ('x','y','width','height','surface_width','surface_height'))+(self.scale,self.output_scale,self.js('visualViewport.height'))

    def register_viewport_origin(self):
        if self.family!='chromium':return
        self.update_origin();key=self.origin_key()
        if getattr(self,'registered_origin',None) and self.registered_origin[0]==key:return
        # Register the original complete browser viewport against the desktop.
        # CSS integer window metrics cannot describe fractional surface phase.
        # This mapping is independent of any control's native reference image.
        import base64,io
        from PIL import Image,ImageChops,ImageStat
        deadline=time.monotonic()+10
        while True:
            data=self.cdp('Page.captureScreenshot',dict(format='png',fromSurface=True,captureBeyondViewport=False))['data']
            viewport=Image.open(io.BytesIO(base64.b64decode(data))).convert('RGB')
            shot=self.command('capture '+self.command('outputs')[0]['name']);event=shot['event']
            desktop=Image.frombytes('RGB',(event['width'],event['height']),Path(shot['path']).read_bytes(),'raw','BGRX',event['stride'])
            left=self.window['x']*self.output_scale
            top=self.window['y']*self.output_scale
            right=left+self.window['width']*self.output_scale
            bottom=top+self.window['height']*self.output_scale
            # Estimate one translation from the complete original viewport.
            # Its scrollbar edge can be clipped differently in browser and
            # compositor captures. That edge cannot define equality here;
            # the independent native-control comparisons below remain exact.
            ranked=[]
            for y in range(math.floor(top),math.ceil(bottom-viewport.height)+1):
                for x in range(math.floor(left),math.ceil(right-viewport.width)+1):
                    crop=desktop.crop((x,y,x+viewport.width,y+viewport.height))
                    score=sum(ImageStat.Stat(ImageChops.difference(crop,viewport)).sum)
                    ranked.append((score,x,y))
            ranked.sort();matches=[(x,y) for score,x,y in ranked if score==ranked[0][0]] if ranked else []
            if matches or time.monotonic()>deadline:break
            time.sleep(.1)
        if len(matches)!=1:
            viewport.save(self.root/'origin-source.png');desktop.save(self.root/'origin-desktop.png')
        assert len(matches)==1,('original viewport has no unique desktop mapping',viewport.size,matches)
        self.registered_origin=(key,matches[0]);self.origin_pixels=matches[0]
        (self.root/'original-viewport-origin.json').write_text(json.dumps(dict(origin=matches[0],size=viewport.size,registration_error=ranked[0][0],next_error=ranked[1][0] if len(ranked)>1 else None,key=key),indent=2)+'\n')

    def js(self, script):
        if self.family=='chromium':return super().js(script)
        return self.driver.command('WebDriver:ExecuteScript',dict(script='return eval(arguments[0]);',args=[script]))['value']

    def check(self, name, value):
        row=dict(case=name,passed=bool(value));self.results.append(row)
        self.report_path.write_text(json.dumps(self.results,indent=2)+'\n')
        print(json.dumps(row),flush=True);assert value,row

    def pixels(self, identifier, field, part=None, label=None, keep_cursor=False, preserve_focus=False, reference_focus=False, _deadline=None):
        deadline=_deadline or time.monotonic()+10
        requested_field=dict(field)
        from PIL import Image,ImageChops
        # Focus/hover are part of the observed state. Blurring before capture
        # can repaint away a retained-display-item defect after a chooser.
        self.js(('' if preserve_focus else 'document.activeElement.blur();')+'document.getElementById('+json.dumps(identifier)+').scrollIntoView({block:"center"})')
        if not keep_cursor:assert self.command('pointer 1500 1100')['ok']
        self.register_viewport_origin()
        def source_bounds():
            box=self.js('document.getElementById('+json.dumps(identifier)+').getBoundingClientRect().toJSON()')
            region=part() if callable(part) else part
            if region is not None:
                box=dict(x=box['x']+region['x'],y=box['y']+region['y'],width=region['width'],height=region['height'])
            return box
        box=source_bounds()
        label=label or identifier
        # Theme paint owns an integral device-pixel viewport. Compare the
        # original native control configured for that viewport, including a
        # fractional CSS width, instead of changing the reference's last edge.
        model=dict(id=label,title='',state=0,enabled=True,scale=self.scale,**self.native_viewport(box))
        if self.family=='firefox':
            # Gecko's JS density is a double; the native presentation is the
            # transported float. Use the exact original request for reference
            # rasterization rather than introducing a second rounding path.
            rows=map(json.loads,(self.root/'helper.jsonl').read_text().splitlines())
            presentations=[r['scale'] for r in rows if r.get('event')=='native-presentation'
                and r.get('kind')==field['kind'] and abs(r['scale']-self.scale)<1/60]
            assert presentations,'original native presentation missing'
            native_scale=presentations[-1]
            model.update(scale=native_scale,width=model['width']*self.scale/native_scale,
                         height=model['height']*self.scale/native_scale)
        if self.family=='firefox' and field['kind']==17:
            # Gecko's snapped paint viewport depends on the fractional edge
            # phase. Use the adapter's actual native view dimensions, rather
            # than guessing that phase by independently rounding the CSS size.
            import re
            dimensions=[tuple(map(float,m)) for m in re.findall(r'native-date-viewport width=([\d.]+) height=([\d.]+)',(self.root/'hook.log').read_text())]
            dimensions=[(w,h) for w,h in dimensions if abs(w/self.scale-box['width'])<2 and abs(h/self.scale-box['height'])<2]
            assert dimensions,'original temporal paint viewport missing'
            model.update(width=dimensions[-1][0]/model['scale'],height=dimensions[-1][1]/model['scale'])
        if self.family=='chromium' and field['kind']==17:
            # Blink passes its own integral theme viewport, which can enclose
            # a fractional CSS date box. Use that recorded viewport for the
            # independent original NativeUI render, rather than rounding the
            # CSS width a second time with a different rule.
            rows=map(json.loads,(self.root/'helper.jsonl').read_text().splitlines())
            viewports=[r for r in rows if r.get('event')=='native-form-control' and r.get('kind')==17
                and abs(r['width']/self.scale-box['width'])<2 and abs(r['height']/self.scale-box['height'])<2]
            assert viewports,'original temporal theme viewport missing'
            model.update(width=viewports[-1]['width']/self.scale,height=viewports[-1]['height']/self.scale)
        model.update(field);field=model
        if field['kind']==9:
            # Scrolling is application model state too. A fresh NSClipView's
            # fractional initial origin can differ from the browser's explicit
            # scroll position; configure both original controls identically.
            field['scroll']=self.js('(()=>{const e=document.getElementById('+json.dumps(identifier)+');return [e.scrollLeft,e.scrollTop]})()')
        reply=self.command('reference '+json.dumps(dict(name=label+'-density-reference',controls=[field],focus=reference_focus)),timeout=60)
        image=Image.open(Path(reply['path'])/(label+'.png')).convert('RGBA')
        expected=Image.new('RGBA',image.size,'white');expected.alpha_composite(image);expected=expected.convert('RGB')
        expected.save(self.root/(label+'-density-expected.png'))
        def pixel_edges(value):
            # The engine owns snapping through its original draw-target
            # transform. A fractional CSS edge can paint at either adjacent
            # device edge; integral edges have one exact position. Pixel
            # values and the complete native viewport remain exact.
            nearest=round(value)
            return [nearest] if abs(value-nearest)<.0001 else list(dict.fromkeys([math.floor(value+.5),math.floor(value),math.ceil(value)]))
        while True:
            self.update_origin()
            # Native intrinsic metrics may finish an ordinary page reflow
            # while the independent reference process initializes. Capture
            # against the current original DOM box, not its earlier position.
            capture_box=source_bounds()
            if self.native_viewport(capture_box)!=self.native_viewport(box):
                assert time.monotonic()<deadline,'original control geometry did not settle: '+identifier
                return self.pixels(identifier,requested_field,part,label,keep_cursor,preserve_focus,reference_focus,_deadline=deadline)
            shot=self.command('capture '+self.command('outputs')[0]['name']);event=shot['event']
            desktop=Image.frombytes('RGB',(event['width'],event['height']),Path(shot['path']).read_bytes(),'raw','BGRX',event['stride'])
            lefts=pixel_edges(math.floor(self.origin_pixels[0]+.5)+capture_box['x']*self.scale)
            tops=pixel_edges(math.floor(self.origin_pixels[1]+.5)+capture_box['y']*self.scale)
            matched=False
            for top in tops:
                for left in lefts:
                    actual=desktop.crop((left,top,left+expected.width,top+expected.height))
                    difference=ImageChops.difference(actual,expected)
                    if difference.getbbox() is None:matched=True;break
                if matched:break
            if difference.getbbox() is None or time.monotonic()>deadline:break
            time.sleep(.1)
        actual.save(self.root/(label+'-density-actual.png'));difference.save(self.root/(label+'-density-diff.png'))
        (self.root/(label+'-density-geometry.json')).write_text(json.dumps(dict(before=box,captured=capture_box,origin=self.origin_pixels,native_request=model,viewport=list(expected.size),paint_origin=[left,top],original_css_pixel_edges=[lefts,tops]),indent=2)+'\n')
        self.check(label+'-whole-original-native-image-at-display-density',difference.getbbox() is None)
        if self.family=='chromium' and identifier in ('date','time') and label==identifier:
            # A byte-exact image can still be a native cell squeezed into the
            # engine's old auto size. Check the original cell's own metric as
            # well; its stepper width depends on the configured height.
            preferred=json.loads((Path(reply['path'])/'results.json').read_text())[0]['preferred']
            wanted=[math.ceil(v*self.scale) for v in preferred]
            self.check(identifier+'-auto-size-uses-original-native-cell-metrics',
                       all(abs(a-b)<=1 for a,b in zip(expected.size,wanted)))
            self.js('document.getElementById('+json.dumps(identifier)+').style.cssText="box-sizing:border-box;width:70px;height:32px"')
            fixed=self.js('document.getElementById('+json.dumps(identifier)+').getBoundingClientRect().toJSON()')
            self.check(identifier+'-explicit-css-size-remains-owned-by-browser',
                       abs(fixed['width']-70)<.01 and abs(fixed['height']-32)<.01)
            self.js('document.getElementById('+json.dumps(identifier)+').removeAttribute("style")')
            self.until(lambda:self.js('(()=>{const b=document.getElementById('+json.dumps(identifier)+').getBoundingClientRect();return Math.abs(b.width-'+str(capture_box['width'])+')<1&&Math.abs(b.height-'+str(capture_box['height'])+')<1})()'),
                identifier+' native auto size restored')

    def chord(self, code, modifier):
        for key,state in ((modifier,1),(code,1),(code,0),(modifier,0)):
            assert self.command(f'key {key} {state}')['ok']

    def key(self, code):
        for state in (1,0):
            assert self.command(f'key {code} {state}')['ok']

    def focus_field(self, name):
        # DOM focus in a background page cannot take the seat from browser
        # chrome. Establish real content focus before independent key trials.
        # A previous address trial can leave the original autocomplete popup
        # above the page after a protocol-driven navigation. Dismiss that UI
        # through its ordinary physical Escape before reaching content.
        self.key(1)
        self.js('document.getElementById('+json.dumps(name)+').scrollIntoView({block:"center"})')
        box=self.js('document.getElementById('+json.dumps(name)+').getBoundingClientRect().toJSON()')
        self.point(box,min(10,box['width']/2),box['height']/2)
        self.button(1);self.button(0)
        self.until(lambda:self.js('document.hasFocus()&&document.activeElement.id==='+json.dumps(name)),
                   'physical field focus '+name)

    def keyboard(self, prefix=''):
        self.focus_field('text')
        for name in ('text','search','password','notes'):
            self.js('(()=>{const e=document.getElementById('+json.dumps(name)+');e.value="Alpha beta";e.focus();e.setSelectionRange(10,10);window.events=[]})()')
            self.chord(30,56)
            self.check(prefix+name+'-native-menu-select-all',self.until(lambda:self.js('document.activeElement.selectionStart===0&&document.activeElement.selectionEnd===10'),'native menu selection'))
            self.chord(30,29)
            self.check(prefix+name+'-native-control-a-moves-to-line-start',self.until(lambda:self.js('document.activeElement.selectionStart===0&&document.activeElement.selectionEnd===0'),'native beginning of line'))
            self.chord(37,29)
            self.check(prefix+name+'-native-control-k-kills-to-line-end',self.until(lambda:self.js('document.activeElement.value')=='','native kill line'))
            self.check(prefix+name+'-native-edit-keeps-trusted-browser-events',self.js('events.some(e=>e.type==="input")&&events.every(e=>e.trusted)'))
            self.chord(44,56)
            self.check(prefix+name+'-native-menu-undo-uses-browser-history',self.until(lambda:self.js('document.activeElement.value')=='Alpha beta','native undo through original history'))
            assert self.command('key 42 1')['ok']
            try:self.chord(44,56)
            finally:assert self.command('key 42 0')['ok']
            self.check(prefix+name+'-native-menu-redo-uses-browser-history',self.until(lambda:self.js('document.activeElement.value')=='','native redo through original history'))

    def clipboard(self):
        self.focus_field('text')
        self.js('text.value="Native clipboard";text.focus();text.setSelectionRange(0,text.value.length);window.events=[]')
        self.chord(46,56)
        self.until(lambda:self.js('events.some(e=>e.id==="text"&&e.type==="copy"&&e.trusted)'),'original trusted copy before changing focus')
        self.js('search.value="";search.focus();search.setSelectionRange(0,0);window.events=[]')
        self.chord(47,56)
        self.check('native-alt-c-alt-v-cross-field-copy-paste',self.until(lambda:self.js('search.value')=='Native clipboard','native paste'))
        self.check('native-paste-keeps-original-trusted-input',self.js('events.some(e=>e.id==="search"&&e.type==="input")&&events.every(e=>e.trusted)'))
        self.pointer_empty_field_clipboard()

    def pointer_empty_field_clipboard(self):
        # Establish focus and selection exclusively through pointer input.
        # Calling focus()/setSelectionRange() here would repair the very Blink
        # frame-selection handoff this regression must exercise.
        for target in ('search','password','notes','text'):
            source='search' if target=='text' else 'text'
            self.js('document.getElementById('+json.dumps(source)+').value="Native clipboard";'
                'document.getElementById('+json.dumps(target)+').value="";window.events=[]')
            # Firefox's original password suggestions can cover the preceding
            # field. Dismiss that visible panel through ordinary cancellation;
            # a retained selection alone does not establish pointer focus.
            self.key(1)
            def point(name,x):
                self.js('document.getElementById('+json.dumps(name)+').scrollIntoView({block:"center"})')
                box=self.js('document.getElementById('+json.dumps(name)+').getBoundingClientRect().toJSON()')
                self.point(box,x,box['height']/2)
                return box
            time.sleep(.65)
            box=point(source,40)
            # Start inside the editor, clear of NSSearchField's leading search
            # button, then drag beyond its text edge to select the whole value.
            self.point(box,box['width']-24,box['height']/2);self.button(1)
            time.sleep(.05);self.point(box,3,box['height']/2);time.sleep(.05);self.button(0)
            self.until(lambda:self.js('(()=>{let e=document.getElementById('+json.dumps(source)+');'
                'return document.activeElement===e&&e.selectionStart===0&&e.selectionEnd===e.value.length})()'),'pointer clipboard source selection')
            self.chord(46,56)
            self.until(lambda:self.js('events.some(e=>e.type==="copy"&&e.id==='+json.dumps(source)+')'),'pointer source copy')
            point(target,40);self.button(1);self.button(0)
            self.chord(47,56)
            self.check(target+'-pointer-focus-empty-editor-native-paste',self.until(lambda:self.js(
                'document.getElementById('+json.dumps(target)+').value')=='Native clipboard','paste into pointer-focused empty '+target))
            self.check(target+'-pointer-paste-keeps-source-and-trusted-events',self.js(
                'document.getElementById('+json.dumps(source)+').value==="Native clipboard"&&'
                'events.filter(e=>e.id==='+json.dumps(target)+').map(e=>e.type).join(",")==="paste,beforeinput,input"&&'
                'events.every(e=>e.trusted)'))

    def point(self, box, x, y):
        # Seat positions are output logical coordinates; DOM boxes are CSS
        # coordinates. Keep the display scale separate from browser zoom.
        self.update_origin()
        px=(self.origin_pixels[0]+(box['x']+x)*self.scale)/self.output_scale
        py=(self.origin_pixels[1]+(box['y']+y)*self.scale)/self.output_scale
        assert self.command(f'pointer {round(px)} {round(py)}')['ok']

    def native_viewport(self, box):
        self.update_origin()
        result={}
        for axis,size in (('x','width'),('y','height')):
            edge=self.origin_pixels[0 if axis=='x' else 1]+box[axis]*self.scale
            result[size]=(math.floor(edge+box[size]*self.scale+.5)-math.floor(edge+.5))/self.scale
        return result

    def pointer_selection(self):
        for name,kind in [('text',7),('search',14),('password',8),('notes',9)]:
            self.js('(()=>{const e=document.getElementById('+json.dumps(name)+');e.value="Alpha beta";e.scrollIntoView({block:"center"});e.blur()})()')
            box=self.js('document.getElementById('+json.dumps(name)+').getBoundingClientRect().toJSON()')
            for case in [dict(name='click',x=25,end_x=25),dict(name='drag',x=25,end_x=65)]:
                # Physical seat positions and Gecko mouse events are quantized.
                # Feed the independent native reference the original DOM event
                # coordinates, rather than pretending the requested CSS point
                # survived those conversions unchanged.
                time.sleep(.65)
                self.js('(()=>{const e=document.getElementById('+json.dumps(name)+');e.focus();e.setSelectionRange(0,0);window.nativePointerEvents=[];for(const type of ["mousedown","mouseup"])e.addEventListener(type,event=>{const b=e.getBoundingClientRect();nativePointerEvents.push({type,x:event.clientX-b.x,y:event.clientY-b.y,trusted:event.isTrusted})},{once:true})})()')
                self.point(box,case['x'],12);self.button(1)
                if case['x']!=case['end_x']:
                    time.sleep(.05);self.point(box,case['end_x'],12);time.sleep(.05)
                self.button(0)
                events=self.until(lambda:self.js('nativePointerEvents.length===2&&nativePointerEvents'),'original trusted pointer sequence '+name)
                assert all(e['trusted'] for e in events),events
                pointer=dict(name=case['name'],x=events[0]['x'],y=events[0]['y'],end_x=events[1]['x'],end_y=events[1]['y'])
                model=dict(id=name,title='',state=0,enabled=True,kind=kind,text='Alpha beta',editable=True,
                    scale=self.scale,pointer_cases=[pointer],**self.native_viewport(box))
                reply=self.command('reference '+json.dumps(dict(name=name+'-pointer-'+case['name']+'-reference',controls=[model],pointers=True)),timeout=60)
                want=json.loads((Path(reply['path'])/'results.json').read_text())[0]['pointers'][0]
                selection=[want['start'],want['end']]
                expression='(()=>{const e=document.getElementById('+json.dumps(name)+');return [e.selectionStart,e.selectionEnd]})()'
                try:
                    matched=self.until(lambda:self.js(expression)==selection,'native pointer selection '+name+' '+json.dumps(want))
                except AssertionError:
                    (self.root/'pointer-selection-failure.json').write_text(json.dumps(dict(
                        field=name,case=case,expected=want,reference=model,box=box,origin=self.origin_pixels,
                        actual=self.js(expression),events=events),indent=2)+'\n')
                    raise
                self.check(name+'-physical-'+case['name']+'-matches-original-native-selection',matched)

    def number_controls(self):
        import re
        self.js('number.value="12";number.scrollIntoView({block:"center"});number.blur()')
        box=self.js('number.getBoundingClientRect().toJSON()')
        self.point(box,box['width']-8,8);time.sleep(.1)
        if self.family=='chromium':
            left,top,right,bottom=self.spin_box('number')
            spin=dict(x=left-box['x'],y=top-box['y'],width=right-left,height=bottom-top)
        else:
            logs='\n'.join(p.read_text(errors='replace') for p in self.root.glob('*hook.log'))
            matches=re.findall(r'native-number .*rect=([\d.]+),([\d.]+) ([\d.]+)x([\d.]+)',logs)
            assert matches,'original Gecko number part geometry missing'
            spin=dict(zip(('x','y','width','height'),[float(v)/self.scale for v in matches[-1]]))
        self.pixels('number',dict(kind=7,text='12',editable=True),
            part=dict(x=0,y=0,width=spin['x'],height=box['height']),label='number-editor')
        # Hover the input, keeping the composited pointer outside the stepper
        # crop. Otherwise the screenshot compares the cursor with NSCell.
        self.point(box,10,10)
        self.pixels('number',dict(kind=15,minimum=-sys.float_info.max,maximum=sys.float_info.max,value=0),
            part=spin,label='number-stepper',keep_cursor=True)
        self.point(box,spin['x']+spin['width']/2,spin['y']+spin['height']/4)
        self.button(1);self.button(0)
        self.check('native-stepper-physical-click-up',self.until(lambda:self.js('number.value')=='13','number increment'))
        self.point(box,spin['x']+spin['width']/2,spin['y']+spin['height']*3/4)
        self.button(1);self.button(0)
        self.check('native-stepper-physical-click-down',self.until(lambda:self.js('number.value')=='12','number decrement'))

    def native_actions(self):
        sizes=[]
        def record_size(stage):
            window=next(w for w in self.command('windows') if w['pid']==self.pid and w['level']==0)
            size=[window['surface_width'],window['surface_height']]
            sizes.append(dict(stage=stage,size=size))
            (self.root/'native-action-window-sizes.json').write_text(json.dumps(sizes,indent=2)+'\n')
            return size
        original_size=record_size('before-native-actions')
        for identifier,condition in [('check','!check.checked'),('radioOne','radioOne.checked&&!radioTwo.checked')]:
            time.sleep(.65)
            self.js('document.getElementById('+json.dumps(identifier)+').scrollIntoView({block:"center"});window.events=[]')
            box=self.js('document.getElementById('+json.dumps(identifier)+').getBoundingClientRect().toJSON()')
            self.point(box,box['width']/2,box['height']/2);self.button(1);self.button(0)
            self.check(identifier+'-physical-native-action-updates-original-model',self.until(lambda:self.js(condition),'native '+identifier+' action'))
            self.check(identifier+'-native-action-keeps-original-trusted-events',self.js('events.some(e=>e.type==="input")&&events.every(e=>e.trusted)'))
        self.js('choice.scrollIntoView({block:"center"});window.events=[]')
        box=self.js('choice.getBoundingClientRect().toJSON()')
        self.point(box,box['width']/2,box['height']/2);self.button(1)
        menu=lambda:next((w for w in self.command('windows') if w['pid']!=self.pid and w['level']==101 and w['visible']),None)
        try:
            self.check('popup-physical-press-opens-original-native-menu',bool(self.until(menu,'native popup menu')))
            import ctypes as C
            import socket
            sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Experiments/ChromiumScrollers'))
            from native_controls import ControlRequest,MAGIC
            from helper import Response
            rows=map(json.loads,(self.root/'helper.jsonl').read_text().splitlines())
            owner=[r for r in rows if r.get('event')=='native-popup-model' and r.get('count')==2][-1]
            request=ControlRequest(magic=MAGIC,operation=12,process=owner['process'],kind=6,control=owner['control'],x=1)
            with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as peer:
                peer.settimeout(5);peer.connect(json.loads((self.root/'native-endpoint.json').read_text())['path'])
                peer.send(bytes(request));response=Response.from_buffer_copy(peer.recv(65536))
            rect=response.parts[6];assert rect.width>0 and rect.height>0
            self.point(box,(rect.x+rect.width/2)/self.scale,(rect.y+rect.height/2)/self.scale)
            time.sleep(.1)
        finally:self.button(0)
        self.check('popup-native-menu-updates-original-selected-option',self.until(lambda:self.js('choice.selectedIndex')==1,'native popup choice'))
        self.check('popup-native-menu-keeps-original-trusted-events',self.js('events.some(e=>e.id==="choice"&&e.type==="input")&&events.every(e=>e.trusted)'))
        self.until(lambda:not menu(),'native popup closes')
        self.check('popup-native-action-preserves-browser-window-size',record_size('after-popup')==original_size)
        self.js('file.scrollIntoView({block:"center"});window.events=[]')
        box=self.js('file.getBoundingClientRect().toJSON()')
        self.point(box,20,box['height']/2);self.button(1);self.button(0)
        # Menu-enabled fixtures have an additional registrar process. Resolve
        # the actual portal role instead of assuming a launch-list position.
        portal_ready=[json.loads(line) for line in (self.root/'file-portal.jsonl').read_text().splitlines()
                      if line.startswith('{') and json.loads(line).get('event')=='ready']
        assert len(portal_ready)==1,'exactly one native file portal must be ready'
        portal_pid=portal_ready[0]['pid']
        panel=lambda:next((w for w in self.command('windows') if w['pid']==portal_pid and w['visible'] and w['level']!=101),None)
        self.check('file-physical-click-opens-shared-original-native-panel',bool(self.until(panel,'original NSOpenPanel')))
        self.check('native-file-panel-opening-preserves-browser-window-size',record_size('file-panel-open')==original_size)
        self.until(lambda:panel() and panel()['focused'],'original file panel keyboard focus')
        for state in (1,0):assert self.command(f'key 1 {state}')['ok']
        self.check('file-native-panel-cancel-retains-empty-original-file-list',self.until(lambda:not panel() and self.js('file.files.length')==0,'native file cancel'))
        self.check('native-file-panel-cancel-preserves-browser-window-size',record_size('file-panel-cancelled')==original_size)

    def color_reactivation(self):
        if self.family!='chromium':return
        def capture(stage):
            from PIL import Image
            shot=self.command('capture '+self.command('outputs')[0]['name']);event=shot['event']
            Image.frombytes('RGB',(event['width'],event['height']),Path(shot['path']).read_bytes(),
                            'raw','BGRX',event['stride']).save(self.root/('color-reactivation-'+stage+'.png'))
            (self.root/('color-reactivation-'+stage+'-windows.json')).write_text(
                json.dumps(self.command('windows'),indent=2)+'\n')
        panel=lambda:next((w for w in self.command('windows')
                           if w['title']=='Colors' and w['visible']),None)
        self.js('window.nxsColor=document.getElementById("color");nxsColor.scrollIntoView({block:"center"})')
        box=self.js('nxsColor.getBoundingClientRect().toJSON()')
        head=self.command('outputs')[0]
        def fits(w):
            return (w['x']>=head['work_x'] and w['y']>=head['work_y'] and
                    w['x']+w['width']<=head['work_x']+head['work_width'] and
                    w['y']+w['height']<=head['work_y']+head['work_height'])
        def activate():
            self.point(box,box['width']/2,box['height']/2);self.button(1);self.button(0)
        def focused():
            w=panel();return w if w and w['focused'] else None
        activate();w=self.until(focused,'physical native color opening')
        # Expose the original well even if the native panel remembers a prior
        # position over it. This arranges geometry without changing focus.
        x=head['work_x']+head['work_width']-w['width']-8;y=head['work_y']+8
        assert self.command(f"move {w['id']} {x} {y}")['ok']
        capture('arranged')
        w=panel();assert w
        self.update_origin()
        point=[(self.origin_pixels[0]+(box['x']+box['width']/2)*self.scale)/self.output_scale,
               (self.origin_pixels[1]+(box['y']+box['height']/2)*self.scale)/self.output_scale]
        self.check('color-panel-and-source-control-remain-visible',fits(w) and
                   not(w['x']<=point[0]<w['x']+w['width'] and w['y']<=point[1]<w['y']+w['height']))
        opened=(self.root/'hook.log').read_text().count('native color chooser opened through original')
        activate()
        self.check('color-repeat-restores-original-focused-native-panel',bool(self.until(focused,'repeated color activation')))
        self.check('color-repeat-keeps-original-browser-session',
                   (self.root/'hook.log').read_text().count('native color chooser opened through original')==opened)
        self.js('window.nxsCancelColor=e=>e.preventDefault();nxsColor.addEventListener("click",nxsCancelColor)')
        activate();self.until(lambda:not panel(),'cancelled click leaves native panel hidden')
        self.check('color-cancelled-click-does-not-reveal-panel',not panel())
        self.js('nxsColor.removeEventListener("click",nxsCancelColor);nxsColor.disabled=true')
        activate();time.sleep(.3)
        self.check('color-disabled-click-does-not-reveal-panel',not panel())
        self.js('nxsColor.disabled=false;nxsColor.dispatchEvent(new Event("DOMActivate",{bubbles:true,cancelable:true}))')
        time.sleep(.3)
        self.check('color-synthetic-activation-does-not-reveal-panel',not panel())
        activate()
        self.check('color-ordinary-activation-recovers-after-cancellation',bool(self.until(focused,'color activation after cancelled input')))
        capture('before-close')
        w=panel();assert w
        assert self.command(f"pointer {w['x']+w['width']-11} {w['y']+11}")['ok']
        self.button(1);self.button(0)
        self.until(lambda:not panel(),'color panel normal close')
        capture('after-close')
        self.until(lambda:'native color chooser completed through original' in (self.root/'hook.log').read_text(),
                   'original color callback completion')
        self.check('color-reactivation-preserves-original-close-callback',True)

    def faults(self):
        marker=self.root/'suppress-native-bitmaps';marker.touch()
        try:self.keyboard('without-snapshots-')
        finally:marker.unlink(missing_ok=True)
        self.check('fault-host-really-withheld-native-snapshots','test-native-bitmap-withheld' in (self.root/'helper.jsonl').read_text())
        self.js('text.value="Alpha beta";text.focus();text.setSelectionRange(10,10)')
        before=sum(row.get('event')=='native-form-key' and row.get('type')==0
            for row in map(json.loads,(self.root/'helper.jsonl').read_text().splitlines()))
        marker=self.root/'drop-one-native-key-reply';marker.touch()
        try:
            self.chord(30,29)
            self.check('lost-native-key-reply-preserves-single-native-cursor-move',self.until(lambda:self.js('text.selectionStart===0&&text.selectionEnd===0&&document.activeElement===text'),'native key receipt'))
            self.check('lost-key-reply-does-not-reexecute-key',not marker.exists())
            rows=list(map(json.loads,(self.root/'helper.jsonl').read_text().splitlines()))
            after=sum(row.get('event')=='native-form-key' and row.get('type')==0 for row in rows)
            self.check('lost-key-reply-executes-exactly-once',after-before==1)
            dropped=next(row for row in reversed(rows) if row.get('event')=='test-native-key-reply-withheld')
            self.check('lost-key-reply-uses-exact-host-receipt',any(row.get('event')=='native-key-receipt' and
                row.get('accepted') and row.get('sequence')==dropped['sequence'] for row in rows))
        finally:marker.unlink(missing_ok=True)
        self.js('text.value="Alpha beta";text.blur()')
        self.pixels('text',dict(kind=7,text='Alpha beta',editable=True),label='text-after-snapshot-recovery')

    def first_snapshot_fault(self):
        marker=self.root/'suppress-native-bitmaps';marker.touch()
        url='file:///workspace/Tests/Wayland/native-density-controls.html?first-image-unavailable'
        try:
            if self.family=='chromium':self.cdp('Page.navigate',dict(url=url))
            else:self.driver.command('WebDriver:Navigate',dict(url=url))
            self.until(lambda:self.js('location.search')=='?first-image-unavailable','fresh control lifetime')
            self.until(lambda:self.js('document.readyState')=='complete','fresh native document')
            self.keyboard('before-first-snapshot-')
        finally:marker.unlink(missing_ok=True)
        self.js('text.value="Alpha beta";text.blur()')
        self.pixels('text',dict(kind=7,text='Alpha beta',editable=True),label='text-first-snapshot-recovery')

    def button_owner_recovery(self):
        # A retained engine glyph must disappear when the original NSButton
        # reacquires painting. Check complete pixels after a real fallback,
        # without changing the title or resizing to repair the display list.
        self.pixels('button',dict(kind=1,title='Native button'),label='button-before-owner-loss')
        marker=self.root/'withhold-button-bitmaps';marker.touch()
        before=(self.root/'helper.jsonl').read_text().count('test-native-button-bitmap-withheld')
        try:
            self.js('button.style.outline="1px solid transparent";button.focus()')
            self.until(lambda:(self.root/'helper.jsonl').read_text().count('test-native-button-bitmap-withheld')>before,
                       'button native snapshot genuinely unavailable')
            self.command('capture '+self.command('outputs')[0]['name'])
        finally:marker.unlink(missing_ok=True)
        self.js('button.blur()')
        self.pixels('button',dict(kind=1,title='Native button'),label='button-after-owner-loss',preserve_focus=True)


def run(t):
    for name,field in [
        ('text',dict(kind=7,text='Alpha beta',editable=True)),
        ('search',dict(kind=14,text='Alpha beta',editable=True,placeholder='Search')),
        ('password',dict(kind=8,text='secret',editable=True)),
        ('notes',dict(kind=9,text='Alpha beta\nLine two\nLine three\nLine four\nLine five\nLine six\nLine seven\nLine eight',editable=True)),
        ('check',dict(kind=2,state=1)),
        ('radioOne',dict(kind=12,items=[dict(id=1,enabled=True),dict(id=2,enabled=True)],selected=2,key_cell=0,member=1)),
        ('radioTwo',dict(kind=12,items=[dict(id=1,enabled=True),dict(id=2,enabled=True)],selected=2,key_cell=0,member=2)),
        ('button',dict(kind=1,title='Native button')),
        ('choice',dict(kind=6,items=[dict(title='First'),dict(title='Second')],selected=0)),
        ('range',dict(kind=4,minimum=0,maximum=100,value=40,step=1)),
        ('progress',dict(kind=5,value=.4)),
        ('color',dict(kind=16,rgba=[40/255,136/255,187/255,1])),
        ('date',dict(kind=17,date_flags=20,date_elements=2,date_style=0,date_value=1794268800)),
        ('time',dict(kind=17,date_flags=52,date_elements=4,date_style=0,date_value=45000)),
        ('list',dict(kind=13,flags=1,items=[dict(id=i+1,title=label,selected=i==0) for i,label in enumerate(['First','Second','Third','Fourth','Fifth','Sixth'])])),
    ]:
        t.pixels(name,field)
    t.keyboard()
    t.clipboard()
    t.pointer_selection()
    t.number_controls()
    t.native_actions()
    t.color_reactivation()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',required=True)
    parser.add_argument('--family',choices=['chromium','firefox'],required=True);parser.add_argument('--port',type=int,default=2866)
    parser.add_argument('--scale',type=float,default=2);parser.add_argument('--faults',action='store_true')
    args=parser.parse_args();fixture=DensityFixture(args.root,args.family,args.port,args.scale)
    try:
        run(fixture)
        if args.faults:
            fixture.faults()
            fixture.first_snapshot_fault()
            if args.family=='firefox':fixture.button_owner_recovery()
    finally:
        if args.family=='firefox':fixture.driver.close()
