"""List layout/scroll transactions compared with the original native control."""
import json,time

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
 expected=reference['list_state'];f.clear();f.js('list.selectedIndex=20;return true');time.sleep(.2)
 f.check('script-selectedness-uses-native-row-reveal-without-input-change',f.selected()==expected['selected'] and state()['top']==expected['visible']['y'] and not f.changes(),actual=state(),native=expected)
 f.pixels('list',True,model={'scroll':[0,expected['visible']['y']]},label='script-reveal')
 f.js('window.targets=[];document.addEventListener("mousedown",e=>targets.push({tag:e.target.tagName,index:e.target.index??null}),{once:true});return true')
 f.clear();f.click(reference['native_item_rects'][19]);f.key_cell=20
 f.check('native-cell-click-keeps-original-trusted-selection-change',f.selected()==[20] and [e['type'] for e in f.changes()]==['input','change'] and all(e['trusted'] for e in f.changes()),actual=state(),targets=f.js('return targets'))
 if getattr(f,'require_native_hit',False):f.check('DOM-pointer-target-matches-the-native-row',f.js('return targets.length===1&&targets[0].tag==="OPTION"&&targets[0].index===19'),actual=f.js('return targets'),native_row=19)
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
