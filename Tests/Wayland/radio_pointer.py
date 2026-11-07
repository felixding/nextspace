"""Native matrix pointer actions through the engines' original click dispatchers."""
import json,time


def run(f):
 members=['r0','r1','r2','r3'];js,check,command=f.js,f.check,f.command
 def records():
  return [json.loads(x) for x in (f.root/'helper.jsonl').read_text().splitlines() if x.startswith('{') and x.endswith('}')]
 def prepare(initial='r0',script=''):
  f.reset();f.wait(lambda:js("return document.title==='Native radio groups'"));f.model('r0')
  js('document.getElementById('+json.dumps(initial)+').checked=true;document.getElementById('+json.dumps(initial)+').focus();window.events=[];window.pointerClicks=[];document.addEventListener("click",e=>pointerClicks.push({id:e.target.id,kind:e.constructor.name,pointerType:e.pointerType,detail:e.detail,button:e.button,trusted:e.isTrusted}),true);'+script+';return true')
  model=f.wait(lambda:(m if (m:=f.model('r0'))['selected']==f.identify(initial) else None))
  owner=next(r for r in reversed(records()) if r['event']=='native-form-control' and r.get('kind')==12 and r['control']==model['control'])
  # Independent single-click cases must not become an engine double click.
  time.sleep(1.1)
  return owner
 def point(identifier):
  if identifier is None:return [1000,850]
  if identifier=='outside-window':return [1500,1100]
  r=js('return document.getElementById('+json.dumps(identifier)+').getBoundingClientRect().toJSON()');o=f.origin()
  return [round(o[0]+r['x']+r['width']/2),round(o[1]+r['y']+r['height']/2)]
 def gesture(owner,start,end,allow_no_start=False):
  before=len(records());a,b=point(start),point(end)
  assert command('pointer '+' '.join(map(str,a)))['ok'];assert command('button 272 1')['ok']
  if allow_no_start:f.wait(lambda:js('return window.pointerMutationDone===true'))
  time.sleep(.04)
  if b!=a:assert command('pointer '+' '.join(map(str,b)))['ok'];time.sleep(.04)
  assert command('button 272 0')['ok']
  def native():return [r for r in records()[before:] if r.get('kind')==12 and r.get('control')==owner['control'] and r.get('process')==owner['process']]
  if not allow_no_start or any(r['event']=='native-form-press' for r in native()):
   f.wait(lambda:any(r['event'] in ['native-form-release','native-form-cancelled-before-start'] for r in native()))
  time.sleep(.1)
  state=f.state();state['pointer_clicks']=js('return pointerClicks')
  return state,native()
 def native_actions(rows):return [r for r in rows if r['event']=='native-form-action']
 def trusted_pointer(state,identifier):
  clicks=state['pointer_clicks']
  return len(clicks)==1 and clicks[0]['id']==identifier and clicks[0]['kind']=='PointerEvent' and clicks[0]['pointerType']=='mouse' and clicks[0]['button']==0 and clicks[0]['trusted']
 cases=[('enabled','r2','r2','r0','r2',1),('selected','r2','r2','r2','r2',0),('disabled','r1','r1','r2','r2',0),('drag-other','r0','r3','r0','r0',0),('outside','r2',None,'r0','r0',0),('outside-window','r2','outside-window','r0','r0',0)]
 for name,start,end,initial,selected,changes in cases:
  owner=prepare(initial);state,rows=gesture(owner,start,end);actions=native_actions(rows)
  check(name+'-native-pointer-action',len(actions)==1 and actions[0]['value']==members.index(selected) and [r['click_count'] for r in rows if r['event']=='native-form-press']==[1],native=rows)
  check(name+'-original-pointer-click',state['focus']==selected and selected in state['checked'] and trusted_pointer(state,selected) and len([e for e in state['events'] if e['type'] in ['input','change']])==changes*2 and all(e['trusted'] for e in state['events']),state=state)
  f.pixels(selected,members,selected,selected,True,label='pointer-'+name)
 owner=prepare(script="document.getElementById('r2').addEventListener('click',e=>e.preventDefault(),{once:true})")
 state,rows=gesture(owner,'r2','r2')
 check('pointer-click-cancellation-restores-original-model',len(native_actions(rows))==1 and state['focus']=='r2' and 'r0' in state['checked'] and trusted_pointer(state,'r2') and not any(e['type'] in ['input','change'] for e in state['events']),state=state,native=rows)
 f.pixels('r0',members,'r0','r2',True,label='pointer-cancel-selected');f.pixels('r2',members,'r0','r2',True,label='pointer-cancel-key')
 for name,mutation in [('removed',"e.target.remove()"),('regrouped',"e.target.name='changed'"),('changed-type',"e.target.type='checkbox'")]:
  owner=prepare(script="document.getElementById('r2').addEventListener('mouseup',e=>{"+mutation+"},{once:true})")
  state,rows=gesture(owner,'r2','r2')
  check(name+'-pointer-origin-cancels-stale-action',len(native_actions(rows))==1 and 'r0' in state['checked'] and 'r2' not in state['checked'] and not any(e['type'] in ['click','input','change'] for e in state['events']),state=state,native=rows)
 owner=prepare(script="document.getElementById('r0').addEventListener('focus',e=>e.target.remove(),{once:true})")
 state,rows=gesture(owner,'r2',None)
 check('removed-native-pointer-focus-target-cancels-stale-action',len(native_actions(rows))==1 and not js("return !!document.getElementById('r0')") and 'r2' not in state['checked'] and not any(e['type'] in ['click','input','change'] for e in state['events']),state=state,native=rows)
 owner=prepare();before=len(records());at=point('r2')
 assert command('pointer '+' '.join(map(str,at)))['ok']
 # Queue real seat clicks without Marionette/state/log round trips between
 # them. Each engine still owns click-count classification and its threshold.
 for _ in range(3):
  assert command('button 272 1')['ok'];time.sleep(.04)
  assert command('button 272 0')['ok'];time.sleep(.06)
 def counted():return [r for r in records()[before:] if r.get('kind')==12 and r.get('control')==owner['control'] and r.get('process')==owner['process']]
 f.wait(lambda:sum(r['event']=='native-form-release' for r in counted())==3)
 time.sleep(.1);state=f.state();state['pointer_clicks']=js('return pointerClicks');cycles=[]
 for row in counted():
  if row['event']=='native-form-press':cycles.append([])
  if cycles:cycles[-1].append(row)
 observed=[]
 for index,rows in enumerate(cycles,1):
  count=rows[0]['click_count'];observed.append(count);actions=native_actions(rows)
  clicks=[x for x in state['pointer_clicks'] if x['detail']==count]
  okay=(len(actions)==1 and len(clicks)==1 and trusted_pointer(dict(pointer_clicks=clicks),'r2')) if actions else not clicks
  check('native-multiple-pointer-click-'+str(index),count==index and okay and state['focus']=='r2' and 'r2' in state['checked'],state=state,native=rows)
 check('native-matrix-receives-original-click-counts',observed==[1,2,3],click_counts=observed)
 for name,mutation in [('removed',"e.target.remove()"),('changed-type',"e.target.type='checkbox'")]:
  owner=prepare(script="window.pointerMutationDone=false;document.getElementById('r2').addEventListener('mousedown',e=>{"+mutation+";void document.body.offsetWidth;window.pointerMutationDone=true},{once:true})")
  state,rows=gesture(owner,'r2','r2',allow_no_start=True)
  check(name+'-mousedown-origin-cancels-stale-action','r0' in state['checked'] and 'r2' not in state['checked'] and not any(e['type'] in ['input','change'] or (e['type']=='click' and e['id'] in members) for e in state['events']),state=state,native=rows)
  js("document.getElementById('s0').checked=true;document.getElementById('s0').focus();window.events=[];window.pointerClicks=[];return true")
  model=f.model('s0');owner=next(r for r in reversed(records()) if r['event']=='native-form-control' and r.get('kind')==12 and r['control']==model['control'])
  state,rows=gesture(owner,'s1','s1')
  check(name+'-retirement-keeps-native-pointer-host-responsive',len(native_actions(rows))==1 and native_actions(rows)[0]['value']==1 and 's1' in state['checked'] and trusted_pointer(state,'s1'),state=state,native=rows)
