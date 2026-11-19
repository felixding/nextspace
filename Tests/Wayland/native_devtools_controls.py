"""Exercise original Firefox DevTools fields and popup coordinate conversion."""
import argparse
import json
import math
from pathlib import Path
import sys
import time

from desktop_input import Desktop
from native_context_menus import ContextFixture
from native_number_fields import ChromiumNumbers
from PIL import Image, ImageChops


class DevTools(Desktop):
    capture = ContextFixture.capture
    until = staticmethod(ChromiumNumbers.until)

    def __init__(self, root, port, report='devtools-checks.json'):
        super().__init__(root)
        self.report_path = self.root/report
        assert not self.report_path.exists(), 'Preserve the earlier report; use a fresh fixture or report name'
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'Experiments/FirefoxNativeUI'))
        from marionette import Marionette
        self.driver = Marionette(port, timeout=30)
        self.driver.command('WebDriver:NewSession', {})
        self.driver.command('Marionette:SetContext', {'value': 'chrome'})
        assert self.js('return !Services.prefs.getBoolPref("focusmanager.testmode")')
        self.window = next(w['id'] for w in self.command('windows') if w['level'] == 0 and w['app_id'] == 'firefox-esr')
        self.results = []

    def js(self, script):
        return self.driver.command('WebDriver:ExecuteScript', dict(script=script, args=[]))['value']

    def button(self):
        return self.js('''let w=document.querySelector("iframe.rdm-toolbar")?.contentWindow;
          let e=w?.document.getElementById("network-throttling");if(!e)return null;
          let b=e.getBoundingClientRect(),r=w.windowUtils.toScreenRect(b.x,b.y,b.width,b.height),s=w.desktopToDeviceScale;
          return {x:r.x/s,y:r.y/s,width:r.width/s,height:r.height/s,scale:w.devicePixelRatio}''')

    def popup_trials(self, scales):
        window = next(w for w in self.command('windows') if w['id']==self.window)
        self.click(window['x']+window['width']-30, window['y']+150)
        self.until(lambda: not self.command('popups'), 'initial popup dismissed by outside click')
        if not self.button():
            self.js('document.getElementById("key_responsiveDesignMode").doCommand();return true')
        self.until(self.button, 'original responsive toolbar')
        name = self.command('outputs')[0]['name']
        for scale in scales:
            self.key(1)
            assert self.command('resize-output %s %d %d' % (name, round(1600*scale), round(1200*scale)))['ok']
            assert self.command('test-scale %s %d 30000' % (name, round(scale*120)))['ok']
            assert self.command('confirm')['ok']
            self.until(lambda: abs(self.button()['scale']-scale)<1/60, 'original browser density')
            rows = []
            for left, top in ((100, 70), (220, 125)):
                self.key(1)
                self.until(lambda: not self.command('popups'), 'previous popup dismissed')
                assert self.command('move %d %d %d' % (self.window, left, top))['ok']
                self.until(lambda: next(w for w in self.command('windows') if w['id']==self.window)['x']==left, 'window translated')
                # Read original geometry after the translated surface commits.
                time.sleep(.3)
                source = self.button()
                self.click(source['x']+source['width']/2,source['y']+source['height']/2)
                popup = self.until(lambda: next((p for p in self.command('popups')
                    if p['width']>1 and p['height']>1), None), 'original DevTools popup')
                self.capture('devtools-popup-%g-%d' % (scale, left))
                rows.append(dict(source=source, popup=popup))
                self.key(1)
                self.until(lambda: not self.command('popups'), 'Escape dismisses original popup')
            delta = [rows[1]['popup'][axis]-rows[0]['popup'][axis] for axis in ('x','y')]
            source_delta = [rows[1]['source'][axis]-rows[0]['source'][axis] for axis in ('x','y')]
            # Pixel rounding is the only tolerance; no field or density offsets.
            passed = all(abs(a-b)<=1 for a,b in zip(delta,source_delta))
            self.results.append(dict(trial='popup-translation', scale=scale, rows=rows,
                                     delta=delta, source_delta=source_delta, passed=passed))
            self.save(False)
            assert passed, self.results[-1]
            self.dimension_pixels(scale)

    def dimension_pixels(self, scale):
        fields = self.js('''let w=document.querySelector('iframe.rdm-toolbar').contentWindow;
          return [...w.document.querySelectorAll('input[type="number"]')].map(e=>{
          let b=e.getBoundingClientRect(),r=w.windowUtils.toScreenRect(b.x,b.y,b.width,b.height),s=w.devicePixelRatio;
          return {x:r.x/s,y:r.y/s,width:b.width,height:b.height,text:e.value,
          native_scale:w.devicePixelRatio}})''')
        assert len(fields)==2
        for index, field in enumerate(fields):
            label = 'devtools-dimension-%g-%d' % (scale,index)
            # Gecko quantizes app units per device pixel. Read its actual
            # density after reflow instead of assuming the nominal preset.
            native_scale = field['native_scale']
            records = [json.loads(line) for line in (self.root/'helper.jsonl').read_text().splitlines()]
            viewport = next(r for r in reversed(records) if r.get('event')=='native-form-control'
                and r.get('kind')==7 and abs(r['width']-field['width']*native_scale)<1
                and abs(r['height']-field['height']*native_scale)<1)
            presentation = next(r['scale'] for r in reversed(records) if r.get('event')=='native-presentation'
                and r['process']==viewport['process'] and r['control']==viewport['control'] and r['kind']==7)
            # Feed the independent original control the exact transported
            # viewport, not DOMRect's float-rounded version of Gecko app units.
            model = dict(id=label, kind=7, title='', enabled=True, state=0,
                         scale=presentation, width=viewport['width']/presentation,
                         height=viewport['height']/presentation, text=field['text'])
            reply = self.command('reference '+json.dumps(dict(name=label+'-reference', controls=[model], focus=False)))
            expected = Image.open(Path(reply['path'])/(label+'.png')).convert('RGB')
            self.capture(label)
            desktop = Image.open(self.root/(label+'.png')).convert('RGB')
            x,y = field['x']*native_scale,field['y']*native_scale
            matched = any(ImageChops.difference(desktop.crop((left,top,left+expected.width,top+expected.height)),expected).getbbox() is None
                for left in {math.floor(x),math.ceil(x)} for top in {math.floor(y),math.ceil(y)})
            evidence=self.root/'native-images/images.jsonl'
            images=[json.loads(line) for line in evidence.read_text().splitlines()] if evidence.exists() else []
            native_matches=[row for row in images if row['kind']==7 and
                abs(row['width']-model['width'])<1e-7 and abs(row['height']-model['height'])<1e-7 and
                abs(row['scale']-model['scale'])<1e-7 and
                Image.open(row['path']).size==expected.size and
                ImageChops.difference(Image.open(row['path']).convert('RGB'),expected).getbbox() is None]
            # CSS/native model and the engine's snapped paint destination can
            # differ. Original DrawSurface then resamples the complete native
            # image. A raw, unresampled reference is not the final-pixel oracle.
            # Require exact outgoing source pixels independently, and retain
            # the actual screen for the ordinary graphical review.
            passed=matched or bool(native_matches)
            self.results.append(dict(trial='native-dimension-pixels', scale=scale, source=field,
                                     native_request=model, direct_screen_pixel_equality=matched,
                                     exact_outgoing_native_images=native_matches, passed=passed))
            self.save(False)
            assert passed, self.results[-1]

    def checkbox(self, action='state'):
        return self.js('''let found=null;function scan(d,n){if(!d||n>5)return;
          let e=d.getElementById("devtools-display-tabbing-order-checkbox");
          if(e)found=e;for(let f of d.querySelectorAll("iframe,browser")){
            try{scan(f.contentDocument,n+1)}catch{}}}scan(document,0);
          if(!found)return null;let e=found,w=e.ownerDocument.defaultView;
          ''' + ('''e.addEventListener('change',event=>e.dataset.nativeTrusted=String(event.isTrusted));''' if action=='watch' else '') + '''
          let b=e.getBoundingClientRect(),r=w.windowUtils.toScreenRect(b.x,b.y,b.width,b.height),s=w.desktopToDeviceScale;
          return {x:r.x/s,y:r.y/s,width:r.width/s,height:r.height/s,checked:e.checked,trusted:e.dataset.nativeTrusted,
          scale:w.devicePixelRatio,appearance:w.getComputedStyle(e).appearance}''')

    def field_trial(self):
        if not self.checkbox():
            self.js('document.getElementById("key_accessibility").doCommand();return true')
        self.until(self.checkbox, 'original Accessibility checkbox')
        previous = None
        stable_since = time.monotonic()
        def settled():
            nonlocal previous, stable_since
            state = self.checkbox()
            if state != previous:
                previous, stable_since = state, time.monotonic()
            return state if time.monotonic()-stable_since >= .5 else None
        self.until(settled, 'original toolbox layout settles')
        before = self.checkbox('watch')
        self.click(before['x']+before['width']/2,before['y']+before['height']/2)
        after = self.until(lambda: (lambda r:r if r['checked']!=before['checked'] else None)(self.checkbox()), 'original checkbox toggles')
        self.capture('devtools-native-checkbox')
        records = [json.loads(line) for line in (self.root/'helper.jsonl').read_text().splitlines()]
        native = [r for r in records if r.get('event')=='native-form-control' and r.get('kind')==2]
        self.results.append(dict(trial='original-devtools-checkbox', before=before, after=after,
                                 native=native, passed=after['trusted']=='true' and bool(native)))
        self.save(False)
        assert self.results[-1]['passed'], self.results[-1]

    def save(self, complete):
        self.report_path.write_text(json.dumps(dict(complete=complete, results=self.results), indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--scales', type=float, nargs='+', default=[1,1.25,1.5,1.75,2])
    parser.add_argument('--report', default='devtools-checks.json')
    args = parser.parse_args()
    test = DevTools(args.root, args.port, report=args.report)
    try:
        test.popup_trials(args.scales)
        test.field_trial()
        test.save(True)
        print(json.dumps(dict(complete=True, trials=len(test.results))))
    except BaseException:
        test.capture('devtools-failure')
        test.save(False)
        raise
    finally:
        test.driver.close()
