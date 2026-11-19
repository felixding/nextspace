"""Real-seat Firefox shared DevTools menus and original application commands."""
import argparse
import json
from pathlib import Path
import sys
import time
from desktop_input import Desktop
from native_context_menus import ContextFixture


class BuiltinMenus(Desktop):
    capture = ContextFixture.capture

    def __init__(self, root, port):
        super().__init__(root)
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'Experiments/FirefoxNativeUI'))
        from marionette import Marionette
        self.driver = Marionette(port)
        self.driver.command('WebDriver:NewSession', {})
        self.driver.command('Marionette:SetContext', {'value': 'chrome'})
        assert self.js('return !Services.prefs.getBoolPref("focusmanager.testmode")')
        self.results = []

    def js(self, script):
        return self.driver.command('WebDriver:ExecuteScript', dict(script=script, args=[]))['value']

    @staticmethod
    def wait(read, predicate, label):
        deadline = time.monotonic()+10
        while True:
            value = read()
            if predicate(value): return value
            assert time.monotonic()<deadline, (label, value)
            time.sleep(.05)

    def source(self):
        return self.js('''let w=document.querySelector('iframe.rdm-toolbar')?.contentWindow;
          let e=w?.document.getElementById('network-throttling');if(!e)return null;
          let b=e.getBoundingClientRect(),r=w.windowUtils.toScreenRect(b.x,b.y,b.width,b.height),s=w.desktopToDeviceScale;
          return {x:r.x/s,y:r.y/s,width:r.width/s,height:r.height/s,label:e.textContent.trim(),
          expanded:e.getAttribute('aria-expanded'),scale:w.devicePixelRatio}''')

    def menus(self):
        return [w for w in self.command('windows') if w['level']==101 and w['visible'] and
                w['presented'] and w['buffer_width']>1]

    def run(self, scales):
        self.driver.command('Marionette:SetContext', {'value': 'content'})
        self.driver.command('WebDriver:Navigate', {'url': Path('/workspace/.build/native-ui/desktop-demo/native-controls.html').as_uri()})
        self.driver.command('Marionette:SetContext', {'value': 'chrome'})
        if not self.source(): self.js('document.getElementById("key_responsiveDesignMode").doCommand();return true')
        self.wait(self.source, bool, 'responsive toolbar')
        output = self.command('outputs')[0]['name']
        offset = None
        for scale in scales:
            assert self.command('resize-output %s %d %d'%(output, round(1600*scale), round(1200*scale)))['ok']
            assert self.command('test-scale %s %d 30000'%(output, round(120*scale)))['ok']
            assert self.command('confirm')['ok']
            self.wait(self.source, lambda s: abs(s['scale']-scale)<1/60, 'density')
            time.sleep(.3)
            source = self.source()
            point = (source['x']+source['width']/2, source['y']+source['height']/2)
            self.click(*point)
            menu = self.wait(self.menus, bool, 'native menu')[-1]
            self.capture('builtin-menu-%g'%scale)
            rows = [json.loads(line) for line in (self.root/'helper.jsonl').read_text().splitlines()]
            opened = next(r for r in reversed(rows) if r.get('event')=='native-context-menu-open')
            label = 'Offline' if source['label']=='No Throttling' else 'No Throttling'
            item = next(r for r in reversed(rows) if r.get('event')=='native-context-menu-item' and
                        r['control']==opened['control'] and r['title']==label)
            x,y,width,height = item['rect']
            self.click(x+width/2, y+height/2)
            self.wait(self.menus, lambda v: not v, 'selection closes')
            self.wait(self.source, lambda v: v['label']==label, 'original throttling command')
            native_point = opened['point']
            assert abs(native_point[0]-point[0])<=2, (opened,source)
            assert abs(native_point[1]-source['y']-source['height'])<=2, (opened,source)
            assert abs(menu['x']+menu['width']/2-native_point[0])<=1, (menu,opened)
            delta = menu['y']-native_point[1]
            if offset is None: offset=delta
            # Native context menus retain NSMenu's own placement offset. Two
            # browser/GTK conversions permit two pixels of snapping, followed
            # by native window placement's separate integral-coordinate snap.
            assert abs(delta-offset)<=1, (menu,opened,offset)
            for cancel in ('caption', 'Escape'):
                self.click(*point); self.wait(self.menus, bool, 'reopens')
                if cancel=='caption': self.click(*point)
                else: self.key(1)
                self.wait(self.menus, lambda v: not v, 'cancel closes')
                self.wait(self.source, lambda v: v['expanded']=='false', 'source collapses')
            self.results.append(dict(scale=scale, source=source, menu=menu, native_point=native_point,
                                     original_action=label, repeated_caption=True, escape=True))
            (self.root/'builtin-menus.json').write_text(json.dumps(self.results,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path);parser.add_argument('--port',required=True,type=int)
    parser.add_argument('--scales',type=float,nargs='+',default=[1,1.25,1.5,1.75,2])
    args=parser.parse_args();test=BuiltinMenus(args.root,args.port)
    try:test.run(args.scales);print(json.dumps(dict(complete=True,densities=len(test.results))))
    except BaseException:test.capture('builtin-menu-failure');raise
    finally:test.driver.close()
