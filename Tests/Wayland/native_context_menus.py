"""Physical context-menu actions through the browser's original command model."""
import argparse,json,time
from pathlib import Path
from PIL import Image
from native_density_controls import DensityFixture

class ContextFixture(DensityFixture):
    def __init__(self,root,family,port,scale=2,report='context-checks.json'):
        super().__init__(root,family,port,scale,page='native-context-menus.html',title='Native context menus',report=report)
        self.serial=0
    def records(self):
        rows=[]
        for line in (self.root/'helper.jsonl').read_text().splitlines():
            try:rows.append(json.loads(line))
            except ValueError:pass
        return rows
    def capture(self,label):
        shot=self.command('capture '+self.command('outputs')[0]['name']);e=shot['event']
        Image.frombytes('RGB',(e['width'],e['height']),Path(shot['path']).read_bytes(),'raw','BGRX',e['stride']).save(self.root/(label+'.png'))
    def open(self,name):
        if name in ('text','search','password','notes'):
            if not self.js('document.hasFocus()&&document.activeElement.id==='+json.dumps(name)):self.focus_field(name)
        else:
            self.key(1);self.js('document.getElementById('+json.dumps(name)+').scrollIntoView({block:"center"})')
        box=self.js('document.getElementById('+json.dumps(name)+').getBoundingClientRect().toJSON()')
        self.point(box,min(15,box['width']/2),box['height']/2)
        return self.open_from_pointer(name)
    def open_from_pointer(self,name):
        self.serial+=1;self.label=f'context-{self.serial:02d}-{name}'
        before=max([r['control'] for r in self.records() if r.get('event')=='native-context-menu-open'] or [0])
        assert self.command('button 273 1')['ok'];time.sleep(.12);assert self.command('button 273 0')['ok']
        def read():
            rows=self.records();opened=[r for r in rows if r.get('event')=='native-context-menu-open' and r['control']>before]
            if not opened:return None
            control=opened[-1]['control'];items=[r for r in rows if r.get('event')=='native-context-menu-item' and r['control']==control]
            models=[r for r in rows if r.get('event')=='native-menu-model' and r['control']==control]
            return (control,items) if models and len(items)==models[-1]['count'] else None
        self.control,self.items=self.until(read,self.label+' opens through native menu')
        self.until(lambda:any(w['visible'] and w['presented'] and w['level']==101 for w in self.command('windows')),self.label+' native surface presented')
        self.capture(self.label+'-open');self.check(self.label+'-native-model-opens',True)
        return self.items
    def chrome_js(self,script):
        return self.driver.command('WebDriver:ExecuteScript',dict(script=script,args=[]))['value']
    def address_state(self):
        if self.family=='firefox':return self.chrome_js('const e=gURLBar.inputField;return {value:e.value,start:e.selectionStart,end:e.selectionEnd}')
        rows=[r for r in (self.root/'hook.log').read_text().splitlines() if r.startswith('views-state ')]
        if not rows:return None
        row=dict(v.split('=',1) for v in rows[-1].split()[1:]);row['value']=bytes.fromhex(row['value_hex']).decode()
        return {k:int(v) if k in ('x','y','width','height','start','end') else v for k,v in row.items()}
    def chrome_trials(self):
        self.chord(38,29);self.key(106)
        if self.family=='firefox':self.driver.command('Marionette:SetContext',dict(value='chrome'))
        if self.family=='firefox':
            box=self.chrome_js('const e=gURLBar.inputField;return {rect:e.getBoundingClientRect().toJSON(),origin:[mozInnerScreenX,mozInnerScreenY]}')
            rect=box['rect'];x=(box['origin'][0]+rect['x']+15)*self.scale/self.output_scale;y=(box['origin'][1]+rect['y']+rect['height']/2)*self.scale/self.output_scale
        else:
            state=self.until(self.address_state,'original address geometry');x=state['x']+15;y=state['y']+state['height']/2
        assert self.command('pointer %d %d'%(x,y))['ok'];self.open_from_pointer('address');self.choose('Select all')
        self.until(lambda:(lambda s:s and s['start']==0 and s['end']==len(s['value']))(self.address_state()),'original address context selection')
        self.capture('address-context-selection');self.check('address-context-original-select-all',True)
        if self.family=='firefox':
            # Preserve the mixed sequence found during personal review:
            # context selection, content click, address shortcut, then Return.
            # Use ordinary seat input; inspect the original browser model.
            original=self.address_state()['value']
            assert self.command('pointer %d %d'%(self.window['x']+self.window['width']-30,self.window['y']+160))['ok']
            self.button(1);self.button(0)
            self.chord(38,56)
            self.until(lambda:self.chrome_js('return gURLBar.focused'),'address shortcut after native context selection')
            self.chord(18,29);self.chord(4,42);self.key(2);self.key(28)
            self.until(lambda:not self.chrome_js('return gURLBar.focused'),'address Return restores content after context selection')
            self.check('address-context-selection-preserves-subsequent-native-navigation',self.chrome_js('return gBrowser.currentURI.spec')==original+'#1')
        self.key(1)
        assert self.command('pointer %d %d'%(x,y))['ok'];self.open_from_pointer('address-modal-keys')
        before=self.address_state();self.key(30)
        self.check('address-context-owns-unmodified-input',self.address_state()['value']==before['value'])
        self.capture('address-context-after-unmodified-input')
        self.key(1);self.closed();self.check('address-context-first-escape-closes',True)
        after=self.address_state()
        self.check('address-context-cancel-preserves-source-selection',
                   all(after[k]==before[k] for k in ('value','start','end')))
        if self.family=='firefox':
            box=self.chrome_js('const e=gBrowser.selectedTab;return {rect:e.getBoundingClientRect().toJSON(),origin:[mozInnerScreenX,mozInnerScreenY]}');rect=box['rect'];x=(box['origin'][0]+rect['x']+rect['width']/2)*self.scale/self.output_scale;y=(box['origin'][1]+rect['y']+rect['height']/2)*self.scale/self.output_scale
        else:
            # Observed center of the retained built-in tab, in logical desktop
            # points. Production code contains no tab geometry or controls.
            x=self.window['x']+150;y=self.window['y']+44
        assert self.command('pointer %d %d'%(x,y))['ok'];self.open_from_pointer('tab')
        self.check('first-tab-context-has-complete-source-labels',all(r['title'] for r in self.items if not r['flags']&1))
        if self.family=='firefox':
            submenu=next(r for r in self.items if r['title']=='Open in New Container Tab')
            left,top,width,height=submenu['rect']
            assert self.command('pointer %d %d'%(left+width/2,top+height/2))['ok']
            branch=self.until(lambda:next((r for r in self.records() if r.get('event')=='native-context-menu-branch' and r['control']==self.control and r['branch']==submenu['command'] and r['items']),None),'original lazy submenu model prepared')
            self.check('lazy-submenu-source-labels-complete',all(item['title'] for item in branch['items'] if not item['flags']&1))
            self.capture('tab-lazy-submenu-after-hover')
            child=next(item for item in branch['items'] if not item['flags']&1)
            self.until(lambda:any(r.get('event')=='native-context-menu-item' and r['control']==self.control and r['command']==child['command'] and r['rect'][2]>0 and r['rect'][3]>0 for r in self.records()),'native lazy submenu visible')
            self.check('original-lazy-submenu-handler-runs',self.chrome_js('return document.getElementById("context_reopenInContainerPopupMenu").children.length>0'))
            self.capture('tab-original-lazy-submenu')
            self.choose('Pin Tab')
            self.until(lambda:self.chrome_js('return gBrowser.selectedTab.pinned'),'original root action after submenu rebuild')
            self.check('root-action-retains-original-command-after-lazy-rebuild',True)
            # Restore through the original command model, too.
            box=self.chrome_js('const e=gBrowser.selectedTab;return {rect:e.getBoundingClientRect().toJSON(),origin:[mozInnerScreenX,mozInnerScreenY]}');rect=box['rect']
            assert self.command('pointer %d %d'%((box['origin'][0]+rect['x']+rect['width']/2)*self.scale/self.output_scale,(box['origin'][1]+rect['y']+rect['height']/2)*self.scale/self.output_scale))['ok']
            self.open_from_pointer('pinned-tab');self.choose('Unpin Tab')
            self.until(lambda:not self.chrome_js('return gBrowser.selectedTab.pinned'),'original unpin restores tab')
            self.check('native-tab-command-restores-original-state',True)
            self.lazy_child_trial()
        else:
            self.key(1);self.closed();self.check('built-in-tab-context-native-and-escape',True)
        if self.family=='firefox':self.driver.command('Marionette:SetContext',dict(value='content'))
    def lazy_child_trial(self):
        count=self.chrome_js('return gBrowser.tabs.length')
        box=self.chrome_js('const e=gBrowser.selectedTab;return {rect:e.getBoundingClientRect().toJSON(),origin:[mozInnerScreenX,mozInnerScreenY]}');rect=box['rect']
        assert self.command('pointer %d %d'%((box['origin'][0]+rect['x']+rect['width']/2)*self.scale/self.output_scale,(box['origin'][1]+rect['y']+rect['height']/2)*self.scale/self.output_scale))['ok']
        self.open_from_pointer('tab-child-action')
        submenu=next(r for r in self.items if r['title']=='Open in New Container Tab')
        left,top,width,height=submenu['rect']
        assert self.command('pointer %d %d'%(left+width/2,top+height/2))['ok']
        child=self.until(lambda:next((r for r in reversed(self.records()) if r.get('event')=='native-context-menu-item' and r['control']==self.control and r['title']=='Personal' and r['rect'][2]>0 and r['rect'][3]>0),None),'original container submenu action visible')
        self.capture('tab-container-child-before-action')
        left,top,width,height=child['rect']
        assert self.command('pointer %d %d'%(left+width/2,top+height/2))['ok']
        self.button(1);time.sleep(.12);self.button(0);self.closed()
        self.until(lambda:self.chrome_js('return gBrowser.tabs.length')==count+1,'original lazy submenu child creates tab')
        self.check('lazy-child-executes-original-container-command',self.chrome_js('return gBrowser.selectedTab.userContextId===1'))
        box=self.chrome_js('const e=gBrowser.selectedTab;return {rect:e.getBoundingClientRect().toJSON(),origin:[mozInnerScreenX,mozInnerScreenY]}');rect=box['rect']
        assert self.command('pointer %d %d'%((box['origin'][0]+rect['x']+rect['width']/2)*self.scale/self.output_scale,(box['origin'][1]+rect['y']+rect['height']/2)*self.scale/self.output_scale))['ok']
        self.open_from_pointer('container-tab-close');self.choose('Close Tab')
        self.until(lambda:self.chrome_js('return gBrowser.tabs.length')==count,'original context close restores tab count')
        self.check('container-child-context-close-restores-original-tabs',True)
    def modal_trials(self):
        self.open('text');before=self.js('text.value');self.key(30)
        self.capture('context-letter-before-cancel');self.key(1);self.closed()
        self.check('context-menu-owns-keyboard-without-editing-underlying-field',self.js('text.value')==before)
        self.key(106)
        self.until(lambda:self.js('text.selectionStart===text.selectionEnd'),'ordinary caret collapse before context shortcut')
        self.open('text')
        self.check('context-shortcut-starts-without-complete-selection',self.js('text.selectionStart!==0||text.selectionEnd!==text.value.length'))
        self.chord(30,56);self.closed()
        self.until(lambda:self.js('text.selectionStart===0&&text.selectionEnd===text.value.length'),'original context shortcut action')
        self.capture('context-shortcut-selection');self.check('context-native-select-all-shortcut',True)
    def hovered_cancel_trial(self):
        self.focus_field('text');self.key(106);self.open('text')
        before=self.js('[text.value,text.selectionStart,text.selectionEnd]')
        item=next(r for r in self.items if r['title'].casefold()=='select all' and r['parent']==-1)
        left,top,width,height=item['rect']
        assert self.command('pointer %d %d'%(left+width/2,top+height/2))['ok']
        self.capture('context-hovered-command-before-cancel');self.key(1);self.closed()
        self.check('escape-closes-hovered-command-without-executing-it',self.js('[text.value,text.selectionStart,text.selectionEnd]')==before)

    def native_tab_shortcuts_trial(self):
        # Establish the focus this separate tab-lifecycle trial must restore.
        # Cancelling an address context menu correctly retains address focus.
        self.focus_field('text')
        self.check('native-tab-shortcuts-start-with-page-focus',self.js('document.hasFocus()'))
        if self.family=='firefox':self.driver.command('Marionette:SetContext',dict(value='chrome'))
        def count():
            if self.family=='firefox':return self.chrome_js('return gBrowser.tabs.length')
            return sum(v['type']=='page' for v in self.cdp('Target.getTargets',target=False)['targetInfos'])
        before=count();self.chord(20,56)
        self.until(lambda:count()==before+1,'native Command-T creates original browser tab')
        def visible_menu():
            return any(w['level']==20 and w['visible'] and w['presented'] for w in self.command('windows'))
        self.until(visible_menu,'native application menu survives original new-tab command')
        self.capture('native-new-tab-and-application-menu')
        self.chord(17,56)
        self.until(lambda:count()==before,'native Command-W closes original new tab')
        self.until(visible_menu,'native application menu survives original tab close')
        if self.family=='firefox':self.driver.command('Marionette:SetContext',dict(value='content'))
        self.until(lambda:self.js('document.hasFocus()'),'original page focus after native tab commands')
        self.check('native-tab-shortcuts-preserve-original-tabs-and-menu',True)
    def choose(self,title):
        item=next(r for r in self.items if r['title'].casefold()==title.casefold() and r['parent']==-1)
        left,top,w,h=item['rect'];assert w>0 and h>0,(title,item)
        assert self.command('pointer %d %d'%(left+w/2,top+h/2))['ok'];self.button(1);time.sleep(.12);self.button(0)
        self.closed();return item
    def closed(self):
        self.until(lambda:any(r.get('event')=='native-context-menu-closed' and r['control']==self.control for r in self.records()),self.label+' closes')
        self.capture(self.label+'-closed')
    def select_all(self,name):
        self.open(name);self.choose('Select all')
        self.until(lambda:self.js('(()=>{const e=document.getElementById('+json.dumps(name)+');return e.selectionStart===0&&e.selectionEnd===e.value.length})()'),name+' original selection')
        self.capture(self.label+'-selection');self.check(name+'-original-select-all',True)
    def password_reveal_trial(self):
        value=self.js('password.value')
        self.open('password');self.choose('Reveal Password')
        self.capture('password-revealed-before-reference')
        self.pixels('password',dict(kind=7,text=value),label='password-revealed-native-field')
        self.open('password')
        self.check('password-reveal-source-state-checked',bool(next(r for r in self.items if r['title']=='Reveal Password')['flags']&4))
        self.choose('Reveal Password')
        self.pixels('password',dict(kind=8,text=value),label='password-remasked-native-field')
        self.check('password-original-value-and-type-preserved',self.js('password.value==='+json.dumps(value)+'&&password.type==="password"'))
    def trials(self):
        self.select_all('text')
        self.open('text');self.choose('Select all')
        # A second context opening must preserve a selection long enough for
        # the original Copy command; use the actual right-click interaction.
        self.open('text');self.choose('Copy')
        self.until(lambda:self.js('events.some(e=>e.id==="text"&&e.type==="copy"&&e.trusted)'),'trusted original copy')
        self.open('search');self.choose('Paste')
        self.until(lambda:self.js('search.value==="Alpha beta"'),'original paste to empty editor')
        self.check('context-copy-paste-original-browser-commands',True)
        self.open('search');self.choose('Undo')
        self.until(lambda:self.js('search.value===""'),'context undo original history')
        self.check('context-undo-original-history',True)
        self.open('search');self.choose('Redo')
        self.until(lambda:self.js('search.value==="Alpha beta"'),'context redo original history')
        self.check('context-redo-original-history',True)
        self.select_all('password');self.select_all('notes')
        if self.family=='firefox':self.password_reveal_trial()
        for name in ('plain','link','image'):
            self.open(name);self.key(1);self.closed();self.check(name+'-escape-dismissal',True)
            self.open(name)
            # Outside dismissal uses an uncovered document point in the same
            # window, rather than an assisted compositor focus change.
            self.command(f'pointer {self.window["x"]+self.window["width"]-25} {self.window["y"]+145}')
            self.button(1);time.sleep(.12);self.button(0);self.closed();self.check(name+'-outside-dismissal',True)
        self.check('trusted-source-events-preserved',self.js('events.every(e=>e.trusted)'))
        self.chrome_trials()
        self.native_tab_shortcuts_trial()
        self.modal_trials()
        self.hovered_cancel_trial()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--family',choices=['chromium','firefox'],required=True);p.add_argument('--port',type=int,required=True);p.add_argument('--scale',type=float,default=2);a=p.parse_args()
    x=ContextFixture(a.root,a.family,a.port,a.scale)
    try:x.trials()
    except BaseException:
        x.capture('context-failure')
        state=dict(windows=x.command('windows'),content=x.js('({focused:document.hasFocus(),active:document.activeElement.id,url:location.href})'))
        if a.family=='firefox':
            x.driver.command('Marionette:SetContext',dict(value='chrome'))
            state['chrome']=x.chrome_js('return {focused:document.hasFocus(),address:gURLBar.focused,active:document.activeElement.id,activeWindow:Services.focus.activeWindow===window,focusedWindow:Services.focus.focusedWindow===window,testmode:Services.prefs.getBoolPref("focusmanager.testmode")}')
        (x.root/'context-failure-state.json').write_text(json.dumps(state,indent=2)+'\n')
        raise
    finally:
        if a.family=='firefox':x.driver.close()
