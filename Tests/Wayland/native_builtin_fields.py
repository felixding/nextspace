"""Native Firefox shared selection groups and editing at every display scale."""
import argparse
import json
from pathlib import Path
import time
from native_builtin_menus import BuiltinMenus


class BuiltinFields(BuiltinMenus):
    def dropdown(self):
        return self.js('''function scan(r){for(let e of r.querySelectorAll('select'))
          if([...e.options].some(o=>o.value==='serif'))return e;
          for(let e of r.querySelectorAll('*'))if(e.shadowRoot){let f=scan(e.shadowRoot);if(f)return f;}}
          let e=scan(document);if(!e)return null;
          let r=window.windowUtils.getElementBoundingScreenRect(e),s='''+str(self.projection)+''';
          return {x:(r.x+r.width/2)*s,y:(r.y+r.height/2)*s,value:e.value,count:e.options.length}''')

    def run_popups(self, scales):
        from native_popup_fixture import PopupFixture
        self.projection=self.js('return window.devicePixelRatio/window.desktopToDeviceScale')
        self.driver.command('Marionette:SetContext',{'value':'content'})
        self.driver.command('WebDriver:Navigate',{'url':'about:preferences#accessibility'})
        self.wait(self.dropdown,bool,'original Settings dropdown')
        native=PopupFixture(self.root,self.command,None,None,None,None,None)
        output=self.command('outputs')[0]['name']
        for scale in scales:
            assert self.command('resize-output %s %d %d'%(output,round(1600*scale),round(1200*scale)))['ok']
            assert self.command('test-scale %s %d 30000'%(output,round(120*scale)))['ok']
            assert self.command('confirm')['ok']
            self.driver.command('Marionette:SetContext',{'value':'chrome'})
            self.wait(lambda:self.js('return window.devicePixelRatio'),lambda s:abs(s-scale)<1/60,'density')
            self.projection=self.js('return window.devicePixelRatio/window.desktopToDeviceScale')
            self.driver.command('Marionette:SetContext',{'value':'content'})
            field=self.dropdown();self.click(field['x'],field['y']);self.key(57)
            self.wait(self.menus,bool,'native Settings dropdown');self.capture('firefox-settings-native-menu-%g'%scale)
            for target,value in [(1,'serif'),(0,'')]:
                for _ in range(field['count']+2):
                    current=native.native_highlight(field['count'])
                    if current==target:break
                    self.key(103 if current>target else 108)
                assert native.native_highlight(field['count'])==target
                self.key(28);self.wait(self.dropdown,lambda s:s['value']==value,'original font setting')
                self.key(57);self.wait(self.menus,bool,'reopened native dropdown')
            self.key(1);self.wait(self.menus,lambda v:not v,'Escape closes native dropdown')
            self.results.append(dict(scale=scale,native_menu=True,original_values=True,escape=True))
            (self.root/'firefox-settings.json').write_text(json.dumps(self.results,indent=2)+'\n')

    def group(self):
        return self.js('''let g=document.querySelector('moz-visual-picker');
          let e=g?.children[0]?.shadowRoot?.querySelector('input');if(!e||!e.getBoundingClientRect().width)return null;
          let r=window.windowUtils.getElementBoundingScreenRect(e),s='''+str(self.projection)+''';
          return {x:(r.x+r.width/2)*s,y:(r.y+r.height/2)*s,
          members:[...g.children].map(i=>{let r=window.windowUtils.getElementBoundingScreenRect(i.shadowRoot.querySelector('input'));
          return {value:i.value,x:(r.x+r.width/2)*s,y:(r.y+r.height/2)*s}}),
          checked:[...g.children].filter(e=>e.checked).map(e=>e.value)}''')

    def search(self):
        return self.js('''function find(root){for(let e of root.querySelectorAll('input[type=search]'))
          if(e.getBoundingClientRect().width)return e;
          for(let e of root.querySelectorAll('*'))if(e.shadowRoot){let f=find(e.shadowRoot);if(f)return f;}}
          let e=find(document);if(!e)return null;let r=window.windowUtils.getElementBoundingScreenRect(e),s='''+str(self.projection)+''';
          return {x:(r.x+r.width/2)*s,y:(r.y+r.height/2)*s,value:e.value,start:e.selectionStart,end:e.selectionEnd}''')

    def run(self, scales):
        if self.source():self.js('document.getElementById("key_responsiveDesignMode").doCommand();return true')
        self.projection=self.js('return window.devicePixelRatio/window.desktopToDeviceScale')
        self.driver.command('Marionette:SetContext', {'value':'content'})
        self.driver.command('WebDriver:Navigate', {'url':'about:preferences#appearance'})
        self.wait(self.group, bool, 'original selection group')
        output=self.command('outputs')[0]['name']
        for scale in scales:
            assert self.command('resize-output %s %d %d'%(output,round(1600*scale),round(1200*scale)))['ok']
            assert self.command('test-scale %s %d 30000'%(output,round(120*scale)))['ok']
            assert self.command('confirm')['ok']
            self.driver.command('Marionette:SetContext', {'value':'chrome'})
            self.wait(lambda:self.js('return window.devicePixelRatio'),lambda s:abs(s-scale)<1/60,'density')
            self.projection=self.js('return window.devicePixelRatio/window.desktopToDeviceScale')
            self.driver.command('Marionette:SetContext', {'value':'content'})
            # Clearing Firefox's search restores its default category. Reopen
            # the original category before the next independent group trial.
            self.driver.command('WebDriver:Navigate', {'url':'about:preferences#appearance'})
            self.wait(self.group,bool,'visible selection group')
            time.sleep(.3)
            group=self.group();light=next(i for i in group['members'] if i['value']=='light')
            self.click(light['x'],light['y']);self.wait(self.group,lambda s:s['checked']==['light'],'pointer changes original selection')
            self.click(group['x'],group['y'])
            self.wait(self.group,lambda s:s['checked']==['auto'],'pointer original selection')
            self.key(106);self.wait(self.group,lambda s:s['checked']==['light'],'native Right original selection')
            self.capture('builtin-radio-%g'%scale)
            self.key(105);self.wait(self.group,lambda s:s['checked']==['auto'],'native Left original selection')
            search=self.search();self.click(search['x'],search['y'])
            for code in (30,48,46):self.key(code)
            self.wait(self.search,lambda s:s['value']=='abc','original input text')
            assert self.command('key 56 1')['ok']
            try:self.key(30)
            finally:assert self.command('key 56 0')['ok']
            selected=self.wait(self.search,lambda s:s['start']==0 and s['end']==3,'native Select All')
            self.capture('builtin-search-selection-%g'%scale)
            self.key(14);self.wait(self.search,lambda s:s['value']=='','native deletion')
            self.results.append(dict(scale=scale,pointer=True,right=True,left=True,select_all=selected,deletion=True))
            (self.root/'builtin-fields.json').write_text(json.dumps(self.results,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path);parser.add_argument('--port',required=True,type=int)
    parser.add_argument('--scales',type=float,nargs='+',default=[1,1.25,1.5,1.75,2])
    parser.add_argument('--check-popups',action='store_true')
    args=parser.parse_args();test=BuiltinFields(args.root,args.port)
    try:(test.run_popups if args.check_popups else test.run)(args.scales);print(json.dumps(dict(complete=True,densities=len(test.results))))
    except BaseException:test.capture('builtin-field-failure');raise
    finally:test.driver.close()
