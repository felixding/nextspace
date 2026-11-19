"""Original native popup geometry under RDM and arbitrary CSS transforms."""
import argparse
import ctypes as C
import json
from pathlib import Path
import socket
import sys
import time
from native_devtools_controls import DevTools


class ProjectedPopups(DevTools):
    def context(self, value):
        self.driver.command('Marionette:SetContext', {'value':value})

    def system(self, script):
        return self.driver.command('WebDriver:ExecuteScript',
            dict(script=script,args=[],sandbox='system'))['value']

    def source(self, identifier):
        self.context('content')
        return self.system('let e=document.getElementById('+json.dumps(identifier)+''');
            let b=e.getBoundingClientRect(),r=window.windowUtils.toScreenRect(b.x,b.y,b.width,b.height),s=window.desktopToDeviceScale;
            return {x:r.x/s,y:r.y/s,width:r.width/s,height:r.height/s}''')

    def center(self, rect):
        return rect['x']+rect['width']/2,rect['y']+rect['height']/2

    def records(self):
        return [json.loads(s) for s in (self.root/'helper.jsonl').read_text().splitlines()]

    def bounds(self, source):
        # The most recent binding belongs to this real pointer interaction.
        record=next(r for r in reversed(self.records()) if r.get('event')=='native-control-screen-bounds')
        assert all(abs(record[k]-source[k])<.02 for k in ('x','y','width','height')),(record,source)
        return record

    def calendar(self, label):
        source=self.source('date');trigger=self.source('calendar')
        panel=lambda:next((w for w in self.command('windows') if w['visible'] and w['title']=='Date and Time'),None)
        self.click(*self.center(trigger));opened=self.until(panel,'original projected calendar')
        bounds=self.bounds(source)
        # This fixture leaves room below its source. Keep original native gap
        # and compositor pixel snapping; there are no scale-specific offsets.
        assert abs(opened['x']-source['x'])<=1,(source,opened)
        assert abs(opened['y']-source['y']-source['height']-4)<=1,(source,opened)
        self.capture(label+'-calendar')
        self.click(*self.center(trigger))
        again=self.until(lambda:(lambda w:w if w and w['focused'] else None)(panel()),'repeated original calendar focus')
        assert all(abs(again[k]-opened[k])<=1 for k in ('x','y'))
        self.key(1);self.until(lambda:not panel(),'original calendar cancellation')
        self.results.append(dict(trial='projected-calendar',label=label,source=source,native=bounds,
            panel=opened,repeated=again,passed=True));self.save(False)

    def choice(self, label):
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Experiments/ChromiumScrollers'))
        from native_controls import ControlRequest,MAGIC
        from helper import Response
        self.context('content');self.system('document.getElementById("choice").selectedIndex=0;window.wrappedJSObject.events.length=0;return true')
        source=self.source('choice');x,y=self.center(source)
        assert self.command('pointer %d %d'%(x,y))['ok']
        assert self.command('button 272 1')['ok']
        try:
            menu=self.until(lambda:next((w for w in self.command('windows') if w['visible'] and w['level']==101),None),'original projected NSMenu')
            bounds=self.bounds(source);rows=self.records()
            owner=next(r for r in reversed(rows) if r.get('event')=='native-popup-model')
            viewport=next(r for r in reversed(rows) if r.get('event')=='native-form-control'
                and r['process']==owner['process'] and r['control']==owner['control'] and r['kind']==6)
            request=ControlRequest(magic=MAGIC,operation=12,process=owner['process'],kind=6,control=owner['control'],x=1)
            with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as peer:
                peer.settimeout(5);peer.connect(json.loads((self.root/'native-endpoint.json').read_text())['path'])
                peer.send(bytes(request));reply=Response.from_buffer_copy(peer.recv(65536))
            rect=reply.parts[6];assert rect.width>0 and rect.height>0
            # Invert the supplied source projection, including returned sizes.
            point=(source['x']+(rect.x+rect.width/2)*source['width']/viewport['width'],
                   source['y']+(rect.y+rect.height/2)*source['height']/viewport['height'])
            assert menu['x']<=point[0]<menu['x']+menu['width'] and menu['y']<=point[1]<menu['y']+menu['height'],(menu,point)
            assert self.command('pointer %d %d'%point)['ok'];time.sleep(.12)
            self.capture(label+'-choice')
        finally:assert self.command('button 272 0')['ok']
        self.until(lambda:self.system('return document.getElementById("choice").selectedIndex')==1,'native choice selects original option')
        assert self.system('let e=window.wrappedJSObject.events;return e.length>0&&e.every(e=>e.trusted)')
        self.results.append(dict(trial='projected-choice',label=label,source=source,native=bounds,menu=menu,point=point,passed=True));self.save(False)

    def run(self, scales):
        self.key(1);self.context('chrome')
        if self.button():self.js('document.getElementById("key_responsiveDesignMode").doCommand();return true')
        self.context('content')
        self.driver.command('WebDriver:Navigate',{'url':Path('/workspace/Tests/Wayland/native-projected-popups.html').as_uri()})
        self.driver.command('WebDriver:SetWindowRect',dict(x=140,y=60,width=1100,height=850))
        self.context('chrome');self.js('document.getElementById("key_responsiveDesignMode").doCommand();return true')
        self.until(self.button,'original responsive toolbar')
        field=self.js('let w=document.querySelector("iframe.rdm-toolbar").contentWindow;let b=w.document.querySelector("input[type=number]").getBoundingClientRect(),r=w.windowUtils.toScreenRect(b.x,b.y,b.width,b.height),s=w.desktopToDeviceScale;return {x:r.x/s,y:r.y/s,width:r.width/s,height:r.height/s}')
        self.click(*self.center(field));assert self.command('key 56 1')['ok']
        try:self.key(30)
        finally:assert self.command('key 56 0')['ok']
        for key in (4,8,6,28):self.key(key)
        self.until(lambda:self.js('return document.querySelector("iframe.rdm-toolbar").contentDocument.querySelector("input[type=number]").value')=='375','original RDM width input')
        output=self.command('outputs')[0]['name']
        transforms=['','translate(17.25px,11.375px) scale(.713,.829)',
                    'translate(6.875px,4.625px) scale(1.137,1.231)']
        for scale in scales:
            self.context('chrome')
            assert self.command('resize-output %s %d %d'%(output,round(1600*scale),round(1200*scale)))['ok']
            assert self.command('test-scale %s %d 30000'%(output,round(scale*120)))['ok']
            assert self.command('confirm')['ok']
            self.until(lambda:abs(self.button()['scale']-scale)<1/60,'original density changes')
            for index, transform in enumerate(transforms):
                self.context('content');self.system('for(let e of document.querySelectorAll("label"))e.style.transform='+json.dumps(transform)+';return true')
                time.sleep(.3);label='projected-%g-%d'%(scale,index)
                self.calendar(label);self.choice(label)
        self.save(True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root');p.add_argument('--port',type=int,required=True)
    p.add_argument('--scales',type=float,nargs='+',default=[1,1.25,1.5,1.75,2]);p.add_argument('--report',default='projected-popup-checks.json')
    a=p.parse_args();t=ProjectedPopups(a.root,a.port,a.report)
    try:t.run(a.scales);print(json.dumps(dict(complete=True,trials=len(t.results))))
    except BaseException:t.capture('projected-popup-failure');t.save(False);raise
    finally:t.driver.close()
