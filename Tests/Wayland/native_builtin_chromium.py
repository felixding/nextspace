"""Inspect an owned Chromium built-in target through its fixture connection."""
import json
import time
from pathlib import Path
from desktop_input import Desktop
from native_context_menus import ContextFixture
from native_number_fields import ChromiumNumbers


class ChromiumBuiltins(Desktop):
    cdp = ChromiumNumbers.cdp
    js = ChromiumNumbers.js
    until = staticmethod(ChromiumNumbers.until)
    capture = ContextFixture.capture

    def attach(self, prefix):
        target=next(t for t in self.cdp('Target.getTargets',target=False)['targetInfos']
                    if t['type']=='page' and t['url'].startswith(prefix))
        self.session=self.cdp('Target.attachToTarget',dict(targetId=target['targetId'],flatten=True),False)['sessionId']
        return target

    def control(self, menu=False):
        selector='devtools-button[aria-label="Customize and control DevTools"]' if menu else 'input[data-nextspace-native-input=field]'
        return self.js('''(()=>{let found;function scan(root){for(let e of root.querySelectorAll('''+json.dumps(selector)+'''))
          if(e.getBoundingClientRect().width&&'''+('true' if menu else 'e.placeholder==="Filter"')+''')found=e;
          for(let e of root.querySelectorAll('*'))if(e.shadowRoot)scan(e.shadowRoot)}scan(document);
          if(!found)return null;let e='''+('found.shadowRoot.querySelector("button")||found' if menu else 'found')+''';
          return {rect:e.getBoundingClientRect().toJSON(),value:e.value,start:e.selectionStart,end:e.selectionEnd,
          height:innerHeight,dpr:devicePixelRatio}})()''')

    def point(self, source):
        window=next(w for w in self.command('windows') if w['level']==0 and w['app_id']=='chromium-browser')
        factor=source['dpr']/(self.command('outputs')[0]['scale']/120)
        box=source['rect']
        return (window['x']+window['frame_left']+(box['x']+box['width']/2)*factor,
                window['y']+window['frame_top']+window['surface_height']-source['height']*factor+
                (box['y']+box['height']/2)*factor)

    def menus(self):
        return [w for w in self.command('windows') if w['level']==101 and w['visible'] and
                w['presented'] and w['buffer_width']>1]

    def settings_select(self):
        return self.js('''(()=>{let found;function scan(r){let e=r.querySelector('#colorSchemeModeSelect');
          if(e)found=e;for(let e of r.querySelectorAll('*'))if(e.shadowRoot)scan(e.shadowRoot)}scan(document);
          if(!found)return null;return {rect:found.getBoundingClientRect().toJSON(),value:found.value,
          options:[...found.options].map(o=>o.value),height:innerHeight,dpr:devicePixelRatio}})()''')

    def settings_trials(self, scales):
        self.attach('chrome://settings');self.until(self.settings_select,'original Settings select')
        self.results=[];output=self.command('outputs')[0]['name']
        for scale in scales:
            assert self.command('resize-output %s %d %d'%(output,round(1600*scale),round(1200*scale)))['ok']
            assert self.command('test-scale %s %d 30000'%(output,round(120*scale)))['ok']
            assert self.command('confirm')['ok']
            self.until(lambda:abs(self.settings_select()['dpr']-scale)<1/60,'density')
            point=self.point(self.settings_select());self.click(*point)
            # A native NextStep popup tracks press/drag/release. Space also
            # opens it for the native menu's keyboard navigation.
            self.key(57);self.until(self.menus,'native Settings menu')
            self.capture('chromium-settings-native-menu-%g'%scale)
            self.key(103);self.key(103);self.key(103);self.key(28)
            self.until(lambda:self.settings_select()['value']=='1','original Light setting')
            self.key(57);self.until(self.menus,'reopened Settings menu')
            self.key(108);self.key(108);self.key(108);self.key(28)
            self.until(lambda:self.settings_select()['value']=='0','original Device setting')
            self.key(57);self.until(self.menus,'third Settings menu');self.key(1)
            self.until(lambda:not self.menus(),'Escape closes')
            state=self.settings_select();assert state['options']==['1','2','0'],state
            self.results.append(dict(scale=scale,original_values=True,option_indices_preserved=True,native_menu=True,escape=True))
            (self.root/'chromium-settings.json').write_text(json.dumps(self.results,indent=2)+'\n')

    def devtools_trials(self, scales):
        self.attach('devtools:');self.until(self.control,'native toolbar field')
        self.results=[];output=self.command('outputs')[0]['name']
        for scale in scales:
            assert self.command('resize-output %s %d %d'%(output,round(1600*scale),round(1200*scale)))['ok']
            assert self.command('test-scale %s %d 30000'%(output,round(120*scale)))['ok']
            assert self.command('confirm')['ok']
            self.until(lambda:abs(self.control()['dpr']-scale)<1/60,'density')
            time.sleep(.3);self.click(*self.point(self.control()))
            for code in (50,30,19,34,23,49):self.key(code)
            self.until(lambda:self.control()['value']=='margin','native filter text')
            matches=self.until(lambda:self.js('''(()=>{let n=0;function scan(r){n+=r.querySelectorAll('.filter-match').length;
              for(let e of r.querySelectorAll('*'))if(e.shadowRoot)scan(e.shadowRoot)}scan(document);return n})()'''),'original filter highlights')
            self.capture('chromium-native-filter-%g'%scale)
            assert self.command('key 56 1')['ok']
            try:self.key(30)
            finally:assert self.command('key 56 0')['ok']
            self.until(lambda:self.control()['start']==0 and self.control()['end']==6,'native Select All')
            self.capture('chromium-native-filter-selection-%g'%scale)
            self.key(14);self.until(lambda:self.control()['value']=='','native deletion')
            for cancel in ('caption','Escape'):
                point=self.point(self.control(True));self.click(*point)
                self.until(self.menus,'native DevTools menu')
                self.capture('chromium-native-menu-%g-%s'%(scale,cancel))
                if cancel=='caption':self.click(*point)
                else:self.key(1)
                self.until(lambda:not self.menus(),'native DevTools menu closes')
            self.results.append(dict(scale=scale,original_filter_matches=matches,select_all=True,
                                     deletion=True,native_menu=True,repeat_caption=True,escape=True))
            (self.root/'chromium-builtins.json').write_text(json.dumps(self.results,indent=2)+'\n')


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path);parser.add_argument('--target',default='devtools:')
    parser.add_argument('--check-devtools',action='store_true')
    parser.add_argument('--check-settings',action='store_true')
    args=parser.parse_args();test=ChromiumBuiltins(args.root)
    if args.check_devtools or args.check_settings:
        try:
            (test.settings_trials if args.check_settings else test.devtools_trials)([1,1.25,1.5,1.75,2])
            print(json.dumps(dict(complete=True,densities=len(test.results))))
        except BaseException:test.capture('chromium-builtin-failure');raise
    else:
        test.attach(args.target)
        print(json.dumps(test.js('({url:location.href,title:document.title,x:screenX,y:screenY,innerWidth,innerHeight,outerWidth,outerHeight,dpr:devicePixelRatio})')))
