"""Compare document scrollbars with original NSScroller and real seat actions."""
import argparse
import ctypes as C
import json
from pathlib import Path
import re
import socket
import sys
import time
from PIL import Image,ImageChops
from native_density_controls import DensityFixture


class RootScrollbars(DensityFixture):
    def __init__(self,root,scale,port,family='firefox'):
        super().__init__(root,family,port,scale,'native-root-scrollbars.html','Native root scrollbars')
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Experiments/ChromiumScrollers'))
        from helper import Request,Response
        self.Request,self.Response=Request,Response

    def bars(self):
        rows=[json.loads(r) for r in (self.root/'helper.jsonl').read_text().splitlines()]
        owners={(r['control'],int(r['horizontal'])):r for r in rows if r.get('event')=='native-metrics'}
        if self.family=='chromium':
            port=self.js('({width:document.documentElement.clientWidth,height:document.documentElement.clientHeight,left:document.getElementById("document").getBoundingClientRect().left+scrollX,gutter:innerWidth-document.documentElement.clientWidth})')
            bars={}
            for (control,horizontal),owner in owners.items():
                if abs(owner['total']/self.scale-(1200 if horizontal else 2200))>1:continue
                length=port['width' if horizontal else 'height']*self.scale
                if abs(owner['length']-length)>1:continue
                bars[horizontal]=dict(owner,x=port['left']*self.scale if horizontal else 0,
                    y=0,width=owner['length'] if horizontal else port['gutter']*self.scale,
                    height=port['gutter']*self.scale if horizontal else owner['length'])
            if len(bars)==2:bars[1]['y']=bars[0]['length']
            return bars if len(bars)==2 else None
        paints=re.findall(r'native-document-scroller id=(\d+) horizontal=(\d) rect=([-\d.]+),([-\d.]+) ([-\d.]+)x([-\d.]+) total=([-\d.]+) page=([-\d.]+)',(self.root/'hook.log').read_text())
        bars={}
        for control,horizontal,x,y,width,height,total,page in paints:
            key=(int(control),int(horizontal))
            if key not in owners:continue
            # Current document has an intentionally distinctive content extent.
            if abs(float(total)/self.scale-(1200 if int(horizontal) else 2200))>1:continue
            bars[int(horizontal)]=dict(owners[key],x=float(x),y=float(y),width=float(width),height=float(height),total=float(total),page=float(page))
        return bars if len(bars)==2 else None

    def state(self,bar):
        endpoint=json.loads((self.root/'native-endpoint.json').read_text())['path']
        with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as peer:
            peer.settimeout(5);peer.connect(endpoint)
            peer.send(bytes(self.Request(magic=0x4e585343,operation=5,process=bar['process'],control=bar['control'],horizontal=int(bar['horizontal']))))
            return self.Response.from_buffer_copy(peer.recv(65536))

    def native_presses(self,bar):
        return sum(row.get('event')=='native-press' and row.get('process')==bar['process'] and row.get('control')==bar['control']
            for row in map(json.loads,(self.root/'helper.jsonl').read_text().splitlines()))

    def point_bar(self,bar,x,y):
        self.update_origin()
        px=(self.origin_pixels[0]+bar['x']+x)/self.output_scale
        py=(self.origin_pixels[1]+bar['y']+y)/self.output_scale
        assert self.command(f'pointer {round(px)} {round(py)}')['ok']

    def native_pixels(self,label,bar):
        self.command('pointer 1500 1100')
        axis='scrollX' if bar['horizontal'] else 'scrollY'
        def settled():
            state=self.state(bar)
            return state if not state.parts[0].y and abs(state.parts[0].x-self.js(axis)*self.scale)<.0001 else None
        # Original engines can align the native action to a device pixel.
        # Compare the echoed document position, after native tracking ends.
        state=self.until(settled,'native document position echo before pixel comparison')
        length=bar['width'] if bar['horizontal'] else bar['height']
        spec=dict(name=label+'-reference',horizontal=bool(bar['horizontal']),length=length/self.scale,
            total=bar['total']/self.scale,page=bar['page']/self.scale,value=state.parts[0].x/self.scale,scale=self.scale)
        (self.root/(label+'-reference-model.json')).write_text(json.dumps(spec,indent=2)+'\n')
        reply=self.command('scroller-reference '+json.dumps(spec),timeout=40)
        reference=Path(reply['path']);metadata=json.loads((reference/'reference.json').read_text())
        expected=Image.frombytes('RGBA',(metadata['width'],metadata['height']),(reference/'reference.argb').read_bytes(),'raw','BGRA')
        background=Image.new('RGBA',expected.size,'white');background.alpha_composite(expected);expected=background.convert('RGB')
        self.check(label+'-original-native-viewport-size',expected.size==(round(bar['width']),round(bar['height'])))
        self.update_origin();x=round(self.origin_pixels[0]+bar['x']);y=round(self.origin_pixels[1]+bar['y'])
        # Fractional browser chrome can leave a final scrollbar edge outside
        # the original client buffer. Preserve that real engine clip; compare
        # every visible native pixel without resampling or color tolerances.
        client_right=round((self.window['x']+self.window['frame_left'])*self.output_scale)+self.window['buffer_width']
        client_bottom=round((self.window['y']+self.window['frame_top'])*self.output_scale)+self.window['buffer_height']
        visible=(min(expected.width,client_right-x),min(expected.height,client_bottom-y))
        assert min(visible)>0
        clipped=visible!=expected.size
        (self.root/(label+'-original-client-clip.json')).write_text(json.dumps(dict(
            native_size=expected.size,visible_size=visible,origin=[x,y],client_right=client_right,client_bottom=client_bottom))+'\n')
        if clipped:expected=expected.crop((0,0,*visible))
        deadline=time.monotonic()+10
        while True:
            shot=self.command('capture '+self.command('outputs')[0]['name']);event=shot['event']
            desktop=Image.frombytes('RGB',(event['width'],event['height']),Path(shot['path']).read_bytes(),'raw','BGRX',event['stride'])
            actual=desktop.crop((x,y,x+expected.width,y+expected.height));difference=ImageChops.difference(actual,expected)
            if difference.getbbox() is None or time.monotonic()>=deadline:break
            time.sleep(.02)
        actual.save(self.root/(label+'-actual.png'));expected.save(self.root/(label+'-expected.png'));difference.save(self.root/(label+'-diff.png'))
        self.check(label+('-original-native-pixels-with-client-clip' if clipped else '-complete-original-native-pixels'),difference.getbbox() is None)

    def run(self):
        bars=self.until(self.bars,'both original native document scrollers')
        (self.root/'root-scrollbar-models.json').write_text(json.dumps(bars,indent=2)+'\n')
        self.check('native-vertical-bar-occupies-left-layout-gutter',self.js('document.getElementById("document").getBoundingClientRect().left+scrollX')>0 and bars[0]['x']==0)
        self.check('native-horizontal-bar-retains-original-document-overflow',self.js('document.documentElement.scrollWidth')==1200)
        for horizontal in (0,1):self.native_pixels('root-'+str(horizontal)+'-initial',bars[horizontal])
        for horizontal in (0,1):
            bar=bars[horizontal];part=self.state(bar).parts[5]
            before=self.native_presses(bar)
            self.point_bar(bar,part.x+part.width/2,part.y+part.height/2);self.button(1);self.button(0)
            axis='scrollX' if horizontal else 'scrollY'
            value=self.until(lambda:self.js(axis) or None,'native arrow moves original document')
            self.check('root-'+str(horizontal)+'-native-arrow-has-one-native-action',value==40)
            self.check('root-'+str(horizontal)+'-arrow-reaches-original-native-control',self.native_presses(bar)==before+1)
            knob=self.state(bar).parts[2]
            x,y=knob.x+knob.width/2,knob.y+knob.height/2
            time.sleep(.65);self.point_bar(bar,x,y);self.button(1)
            try:
                self.point_bar(bar,x+(30*self.scale if horizontal else 0),y+(0 if horizontal else 30*self.scale))
                self.until(lambda:self.js(axis)>40,'native thumb drags original document')
            finally:self.button(0)
            self.check('root-'+str(horizontal)+'-native-thumb-updates-original-scroll-position',self.js(axis)>40)
            self.check('root-'+str(horizontal)+'-thumb-reaches-original-native-control',self.native_presses(bar)==before+2)
            self.native_pixels('root-'+str(horizontal)+'-after-drag',bar)
        self.check('original-browser-scroll-events-remain-trusted',self.js('scrollEvents.length>0&&scrollEvents.every(e=>e.trusted)'))

    def lifecycle(self):
        if self.family=='firefox':self.driver.command('WebDriver:SetWindowRect',dict(width=640,height=460,x=0,y=0))
        else:
            window=self.cdp('Browser.getWindowForTarget')
            self.cdp('Browser.setWindowBounds',dict(windowId=window['windowId'],bounds=dict(width=640,height=460)))
        self.until(lambda:self.js('outerWidth<=650&&outerHeight<=470'),'original browser resize')
        def resized():
            bars=self.bars()
            return bars if bars and abs(bars[0]['height']/self.scale-self.js('document.documentElement.clientHeight'))<1 else None
        bars=self.until(resized,'native scrollers follow resized document')
        self.check('root-resize-retains-original-scroll-range',self.js('document.documentElement.scrollWidth===1200&&document.documentElement.scrollHeight===2200'))
        for horizontal in (0,1):self.native_pixels('root-'+str(horizontal)+'-resized',bars[horizontal])
        self.js('document.getElementById("document").style.cssText="width:100px;height:100px"')
        self.check('root-fitting-document-releases-both-layout-gutters',self.until(lambda:self.js('document.documentElement.clientWidth===innerWidth&&document.documentElement.clientHeight===innerHeight'),'fitting original document'))
        self.js('document.getElementById("document").style.cssText="width:1200px;height:2200px"')
        self.until(lambda:self.js('document.documentElement.clientWidth<innerWidth&&document.documentElement.clientHeight<innerHeight'),'original overflow returns')
        bars=self.until(resized,'native overflow scrollers restored')
        for horizontal in (0,1):self.native_pixels('root-'+str(horizontal)+'-restored',bars[horizontal])
        if self.family=='firefox':self.driver.command('WebDriver:Navigate',dict(url='about:blank'))
        else:self.cdp('Page.navigate',dict(url='about:blank'))
        self.until(lambda:self.js('location.href')=='about:blank','original document detached')
        self.check('root-document-detach-retires-original-native-controls',self.until(lambda:all(self.state(bar).parts[6].width==0 for bar in bars.values()),'native document lifetime teardown'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True);p.add_argument('--scale',type=float,default=1);p.add_argument('--port',type=int,default=2870);p.add_argument('--family',choices=['firefox','chromium'],default='firefox');p.add_argument('--lifecycle',action='store_true')
    args=p.parse_args();fixture=RootScrollbars(args.root,args.scale,args.port,args.family)
    try:
        fixture.run()
        if args.lifecycle:fixture.lifecycle()
    finally:
        if fixture.family=='firefox':fixture.driver.close()
