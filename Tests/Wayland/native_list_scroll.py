"""List layout/scroll transactions compared with the original native control."""
import json,time
from pathlib import Path

def run(f):
 f.reset();f.focus('list');f.key_cell=0
 initial=f.pixels('list',True,label='scroll-initial');f.key_cell=initial['list_state']['key_cell']
 geometry=initial['scroll_geometry'];native=initial['list_state']
 def state():return f.js('return {left:list.scrollLeft,top:list.scrollTop,width:list.scrollWidth,height:list.scrollHeight,client:[list.clientLeft,list.clientTop,list.clientWidth,list.clientHeight],selected:list.selectedIndex}')
 actual=state();g=geometry['clip']
 f.check('DOM-clip-and-document-match-original-native-list',actual['client']==[g[x] for x in ['x','y','width','height']] and actual['height']==native['content']['height'] and actual['width']==native['content']['width'],native=initial,actual=actual)
 def option_rects():return f.js('const r=list.getBoundingClientRect();return [...list.options].map(o=>{const b=o.getBoundingClientRect();return {x:b.x-r.x,y:b.y-r.y,width:b.width,height:b.height}})')
 f.check('DOM-option-rectangles-match-actual-native-cells',option_rects()==initial['native_item_rects'],actual=option_rects(),native=initial['native_item_rects'])
 f.js('window.scrolls=[];list.addEventListener("scroll",e=>scrolls.push({trusted:e.isTrusted,top:list.scrollTop}));return true')
 for label,y in [('script-scroll',120),('script-native-maximum',100000),('script-native-minimum',-100000)]:
  f.js('window.scrolls=[];list.scrollTop='+str(y)+';return true');time.sleep(.1)
  reference=f.pixels('list',True,model={'scroll':[0,y]},label=label)
  expected=reference['list_state']['visible']['y'];actual=state()
  f.check(label+'-original-native-position-and-trusted-event',actual['top']==expected and f.js('return scrolls.some(e=>e.trusted&&e.top==='+str(expected)+')'),actual=actual,expected=expected)
  f.check(label+'-option-rectangles-follow-native-viewport',option_rects()==reference['native_item_rects'])
 # No page wheel handler exists: the native widget's own region must win.
 f.clear();f.point(dict(x=40,y=30,width=80,height=30));assert f.command('scroll 1')['ok'];time.sleep(.15)
 reference=f.pixels('list',True,model={'scroll':[0,0],'wheel':[dict(dy=10)]},label='wheel-no-page-handler')
 expected=reference['list_state']['visible']['y']
 f.check('wheel-native-default-without-selection-action',state()['top']==expected and not f.changes(),actual=state(),expected=expected)
 f.check('native-wheel-emits-original-trusted-scroll',f.wait(lambda:f.js('return scrolls.some(e=>e.trusted&&e.top==='+str(expected)+')')))
 f.js('window.wheels=[];list.addEventListener("wheel",e=>{wheels.push({trusted:e.isTrusted,cancelable:e.cancelable});e.preventDefault()},{once:true,passive:false});return true')
 before=state();f.point(dict(x=40,y=30,width=80,height=30));assert f.command('scroll 1')['ok'];time.sleep(.15)
 f.check('cancelled-trusted-wheel-keeps-native-and-DOM-position',state()==before and f.js('return wheels.length===1&&wheels[0].trusted&&wheels[0].cancelable'))
 f.pixels('list',True,model={'scroll':[0,expected]},label='cancelled-wheel')
 f.js('list.scrollTop=0;return true');time.sleep(.1)
 # Original native key navigation supplies both selectedness and reveal offset.
 reference=f.plan('scroll-key-reference',[dict(key=9) for _ in range(12)])
 f.clear()
 for _ in range(12):f.key(108)
 expected=reference['list_state'];f.key_cell=expected['key_cell'];time.sleep(.2)
 f.check('native-key-selection-and-reveal-position-match',f.selected()==expected['selected'] and state()['top']==expected['visible']['y'],actual=state(),native=expected)
 f.pixels('list',True,model={'scroll':[expected['visible']['x'],expected['visible']['y']]},label='key-reveal')
 reference=f.plan('script-reveal-reference',[dict(key=9) for _ in range(7)])
 expected=reference['list_state'];f.clear()
 immediate=f.js('list.selectedIndex=20;return {top:list.scrollTop,selected:list.selectedIndex}')
 # Observe the original asynchronous engine reveal to its exact native target.
 reveal=[dict(elapsed=0,**immediate)];started=time.monotonic();deadline=started+8
 while True:
  actual=state();reveal.append(dict(elapsed=time.monotonic()-started,top=actual['top'],selected=actual['selected']))
  if (f.selected()==expected['selected'] and actual['top']==expected['visible']['y']) or time.monotonic()>=deadline:break
  time.sleep(.02)
 f.check('script-selectedness-uses-native-row-reveal-without-input-change',f.selected()==expected['selected'] and state()['top']==expected['visible']['y'] and not f.changes(),actual=state(),native=expected,reveal_trace=reveal)
 f.pixels('list',True,model={'scroll':[0,expected['visible']['y']]},label='script-reveal')
 f.js('window.targets=[];window.nativeClickTargets=[];document.addEventListener("mousedown",e=>targets.push({tag:e.target.tagName,index:e.target.index??null}),{once:true});for(const t of ["mousedown","mouseup","click"])document.addEventListener(t,e=>nativeClickTargets.push({type:e.type,tag:e.target.tagName,index:e.target.index??null,trusted:e.isTrusted}),{once:true});return true')
 f.clear();f.click(reference['native_item_rects'][19]);f.key_cell=20
 f.check('native-cell-click-keeps-original-trusted-selection-change',f.selected()==[20] and [e['type'] for e in f.changes()]==['input','change'] and all(e['trusted'] for e in f.changes()),actual=state(),targets=f.js('return targets'))
 if getattr(f,'require_native_hit',False):f.check('DOM-pointer-target-matches-the-native-row',f.js('return targets.length===1&&targets[0].tag==="OPTION"&&targets[0].index===19'),actual=f.js('return targets'),native_row=19)
 if getattr(f,'require_native_hit',False):
  from native_list_hits import run as hit_checks
  hit_checks(f,reference)
 f.pixels('list',True,model={'scroll':[0,expected['visible']['y']]},label='scrolled-cell-click')
 f.js('list.scrollTop=100000;return true');time.sleep(.1)
 reference=f.pixels('list',True,model={'scroll':[0,100000]},label='before-resize')
 f.js('list.style.width="240px";list.style.height="130px";return true');time.sleep(.2)
 reference=f.pixels('list',True,model={'scroll':[0,100000]},label='resized')
 expected=reference['list_state'];g=reference['scroll_geometry']['clip']
 f.check('resized-DOM-clip-and-native-clamped-position-match',state()['top']==expected['visible']['y'] and state()['client']==[g[x] for x in ['x','y','width','height']],actual=state(),native=reference)
 f.check('resized-option-rectangles-match-native',option_rects()==reference['native_item_rects'])
 f.js('list.style.appearance="none";return true');time.sleep(.2)
 f.check('unsupported-appearance-releases-native-layout-metrics',state()['client']!=[g[x] for x in ['x','y','width','height']],actual=state())
 retained=state()['top'];f.js('list.style.appearance="auto";return true');time.sleep(.2);f.key_cell=0
 reference=f.pixels('list',True,model={'scroll':[0,retained]},label='appearance-restored')
 f.check('native-appearance-restores-retained-engine-scroll-position',state()['top']==reference['list_state']['visible']['y'],actual=state(),native=reference['list_state'])
 # Retiring a native target during trusted wheel dispatch must not leave a
 # browser scroll animation to overwrite its reinserted native successor.
 f.reset();f.focus('list');f.key_cell=0
 initial=f.pixels('list',True,label='wheel-retirement-initial');f.key_cell=initial['list_state']['key_cell']
 owner=next(x for x in reversed(f.records()) if x['event']=='native-form-control' and x.get('kind')==13)
 f.js('window.retiredWheel=null;window.listParent=list.parentNode;list.addEventListener("wheel",e=>{window.retiredWheel={trusted:e.isTrusted,cancelable:e.cancelable};window.retiredList=e.currentTarget;retiredList.remove()},{once:true,passive:false});return true')
 f.point(dict(x=40,y=30,width=80,height=30));assert f.command('scroll 1')['ok']
 f.wait(lambda:f.js('return !document.getElementById("list")'))
 f.check('trusted-wheel-callback-can-retire-native-list',f.js('return retiredWheel.trusted&&retiredWheel.cancelable'))
 retired=lambda:any(x['event']=='native-form-destroy' and x.get('kind')==13 and x.get('control')==owner['control'] and x.get('process')==owner['process'] for x in f.records())
 f.check('wheel-retirement-releases-native-list',f.wait(retired))
 f.js('listParent.append(retiredList);retiredList.scrollTop=0;return true');f.focus('list');f.key_cell=0
 f.pixels('list',True,model={'scroll':[0,0]},label='wheel-reinserted-before')
 data=f.control_model('list');data.update(scroll=[0,0],wheel=[dict(dy=10)])
 reply=f.command('reference '+json.dumps(dict(name='wheel-reinserted-position-reference',controls=[data],focus=True)))
 expected=json.loads((Path(reply['path'])/'results.json').read_text())[0]['list_state']['visible']['y']
 f.clear();f.point(dict(x=40,y=30,width=80,height=30));assert f.command('scroll 1')['ok']
 actual=f.wait(state,lambda s:s['top']!=0)
 f.check('reinserted-list-wheel-uses-original-native-offset',actual['top']==expected and not f.changes(),actual=actual,expected=expected)
 positions=[];deadline=time.monotonic()+.35
 while time.monotonic()<deadline:
  positions.append(state()['top']);time.sleep(.02)
 f.check('reinserted-list-rejects-late-competing-scroll',positions and all(v==expected for v in positions),positions=positions,expected=expected)
 f.pixels('list',True,model={'scroll':[0,0],'wheel':[dict(dy=10)]},label='wheel-reinserted-after')
