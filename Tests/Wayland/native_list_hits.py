"""Original browser hit/event contracts using actual native row rectangles."""
import json,time

def run(f,reference):
 clicks=f.js('return nativeClickTargets')
 f.check('original-down-up-click-retain-the-native-row-and-trusted-events',clicks==[dict(type=t,tag='OPTION',index=19,trusted=True) for t in ['mousedown','mouseup','click']],actual=clicks)
 rows=reference['native_item_rects'];clip=reference['scroll_geometry']['clip']
 visible=[i for i,r in enumerate(rows) if r['width']>0 and r['height']>0 and
  clip['y']<r['y']+r['height']/2<clip['y']+clip['height']]
 assert len(visible)>2
 def hits(indices):
  return f.js('const root=list.getBoundingClientRect(),rows='+json.dumps(rows)+',indices='+json.dumps(indices)+';return indices.map(i=>{const r=rows[i],n=document.elementFromPoint(root.x+r.x+r.width/2,root.y+r.y+r.height/2);return {tag:n?.tagName,index:n?.index??null}})')
 wanted=[dict(tag='OPTION',index=i) for i in visible]
 f.check('native-point-queries-and-repeated-cache-hits-return-the-visible-native-rows',hits(visible)==wanted and hits(visible)==wanted,actual=hits(visible),expected=wanted)
 nonitems=[dict(x=clip['x']/2,y=clip['y']+clip['height']/2),dict(x=.5,y=.5)]
 actual=f.js('const r=list.getBoundingClientRect();return '+json.dumps(nonitems)+'.map(p=>document.elementFromPoint(r.x+p.x,r.y+p.y)===list)')
 f.check('native-scroller-and-border-point-hits-target-the-control',all(actual),actual=actual)
 a,b=visible[1:3]
 f.js('window.nativeHitEvents=[];window.nativeHitLog=e=>nativeHitEvents.push({type:e.type,tag:e.target.tagName??e.target.nodeName,index:e.target.index??null,relatedTag:e.relatedTarget?.tagName??e.relatedTarget?.nodeName??null,relatedIndex:e.relatedTarget?.index??null,trusted:e.isTrusted});for(const t of ["mouseover","mouseout","mouseenter","mouseleave","mousemove","pointerover","pointerout","pointermove"])document.addEventListener(t,nativeHitLog,true);return true')
 try:
  assert f.command('pointer 1500 1100')['ok'];time.sleep(.08)
  f.js('nativeHitEvents=[];return true')
  f.point(rows[a]);time.sleep(.08);f.point(rows[b]);time.sleep(.08)
  events=f.js('return nativeHitEvents')
  transitions=lambda name,source,related:any(e['type']==name and e.get('tag')=='OPTION' and e.get('index')==source and e.get('relatedTag')=='OPTION' and e.get('relatedIndex')==related and e['trusted'] for e in events)
  f.check('original-native-row-mouse-hover-and-related-targets',all(transitions(t,source,related) for t,source,related in [('mouseout',a,b),('mouseover',b,a),('mouseleave',a,b),('mouseenter',b,a)]),actual=events,native_rows=[a,b])
  f.check('original-native-row-pointer-hover-and-related-targets',transitions('pointerout',a,b) and transitions('pointerover',b,a),actual=events)
  selected=f.selected();f.clear()
  f.js('window.nativeCancelledHit=null;list.addEventListener("mousedown",e=>{e.preventDefault();window.nativeCancelledHit={tag:e.target.tagName,index:e.target.index,trusted:e.isTrusted,cancelable:e.cancelable,prevented:e.defaultPrevented}},{once:true});return true')
  f.click(rows[a]);actual=f.wait(lambda:f.js('return nativeCancelledHit'))
  f.check('native-row-mousedown-cancellation-precedes-native-selection',actual==dict(tag='OPTION',index=a,trusted=True,cancelable=True,prevented=True) and f.selected()==selected and not f.changes(),actual=actual,selected=f.selected(),expected=selected)
  # The original traversal must retain application overlays above native UI.
  actual=f.js('const r=list.getBoundingClientRect(),row='+json.dumps(rows[b])+';const d=document.createElement("div");d.id="nativeHitOverlay";Object.assign(d.style,{position:"fixed",left:(r.x+row.x)+"px",top:(r.y+row.y)+"px",width:row.width+"px",height:row.height+"px",zIndex:9999,background:"white"});document.body.appendChild(d);return document.elementFromPoint(r.x+row.x+row.width/2,r.y+row.y+row.height/2)===d')
  f.check('original-application-overlay-still-owns-hit-traversal',actual)
  f.js('nativeHitOverlay.remove();document.body.style.minHeight=(innerHeight*2)+"px";window.scrollTo(0,40);return true');time.sleep(.1)
  f.check('page-scroll-keeps-original-frame-to-native-row-coordinates',f.js('return window.scrollY')==40 and hits(visible)==wanted,actual=hits(visible),expected=wanted)
 finally:
  f.js('for(const t of ["mouseover","mouseout","mouseenter","mouseleave","mousemove","pointerover","pointerout","pointermove"])document.removeEventListener(t,nativeHitLog,true);document.getElementById("nativeHitOverlay")?.remove();window.scrollTo(0,0);document.body.style.minHeight="";return true')
  time.sleep(.1)
