"""Native search-button actions compared with each engine's real Enter path."""
import json,time

def run(f):
 js,check=f.js,f.check
 check('native-search-actions-document',js('return document.title')=='Native search actions')
 def reset(name):
  js('restore();const e=document.getElementById('+json.dumps(name)+');e.focus();e.setSelectionRange(2,2);events=[];return true')
 def semantic():
  return js("return events.filter(e=>['change','submit','search','invalid'].includes(e.type)||(e.type==='click'&&e.id==='submitbutton'))")
 for name in ['single','explicit','multi','invalidfield','readonly','unowned']:
  reset(name);f.key(28);time.sleep(.15);expected=semantic()
  if name=='single':check('original-enter-submits-one-trusted-form',len(expected)==1+sum(e['type']=='search' for e in expected) and len([e for e in expected if e['type']=='submit' and e['trusted']])==1,events=expected)
  reset(name);reference=f.pixels(name,True,label=name+'-before-native-search')
  js('events=[];return true');before=len((f.root.parent/'helper.jsonl').read_text().splitlines())
  rect=reference['search_parts']['search'];box=f.control_model(name)['rect'];origin=f.origin()
  x=round(origin[0]+box['x']+rect['x']+rect['width']/2);y=round(origin[1]+box['y']+rect['y']+rect['height']/2)
  assert f.command('pointer '+str(x)+' '+str(y))['ok'];assert f.command('button 272 1')['ok'];time.sleep(.04);assert f.command('button 272 0')['ok'];assert f.command('pointer 1500 1100')['ok']
  f.wait(lambda:any(row['event']=='native-form-action' and row.get('kind')==14 and row.get('action')==1 for row in map(json.loads,(f.root.parent/'helper.jsonl').read_text().splitlines()[before:])))
  time.sleep(.15)
  # Search notifications are queued by the original engine, not synchronous.
  try:f.wait(lambda:semantic()==expected)
  except AssertionError:pass
  actual=semantic()
  check(name+'-native-search-matches-original-enter',actual==expected,actual=actual,expected=expected)
  f.pixels(name,True,label=name+'-after-native-search')

 # Listener changes must be handled by the original engine default phase.
 cases=[('cancel','single','e.preventDefault();window.callback=true',False,'keypress'),
  ('remove','dynamic','e.currentTarget.remove();window.callback=true',False,'keypress'),
  ('change-value','single','e.currentTarget.value="Changed";window.callback=true',False,'keypress'),
  ('change-focus','single','explicit.focus();window.callback=true',False,'keypress'),
  ('change-form','single','e.currentTarget.setAttribute("form","explicitform");window.callback=true',False,'keypress'),
  ('disable','single','e.currentTarget.disabled=true;window.callback=true',False,'keypress'),
  ('retype','single','e.currentTarget.type="checkbox";window.callback=true',False,'keypress'),
  ('change-retirement','dynamic','e.currentTarget.remove();window.callback=true',True,'change')]
 for label,name,body,edit,event_type in cases:
  def prepare(native):
   reset(name)
   if edit:f.key(45)
   kind='click' if native and event_type=='keypress' else event_type
   js('window.callback=false;document.getElementById('+json.dumps(name)+').addEventListener('+json.dumps(kind)+',e=>{'+body+'},{once:true});events=[];return true')
  prepare(False);f.key(28);time.sleep(.15);expected=semantic()
  expected_state=js('const e=document.getElementById('+json.dumps(name)+');return {present:!!e,value:e?.value??null,focused:document.activeElement.id,callback:window.callback,type:e?.type??null,disabled:e?.disabled??null}')
  prepare(True);reference=f.pixels(name,True,label=label+'-before-native-search');js('events=[];return true')
  rect=reference['search_parts']['search'];box=f.control_model(name)['rect'];origin=f.origin()
  assert f.command('pointer '+str(round(origin[0]+box['x']+rect['x']+rect['width']/2))+' '+str(round(origin[1]+box['y']+rect['y']+rect['height']/2)))['ok']
  assert f.command('button 272 1')['ok'];time.sleep(.04);assert f.command('button 272 0')['ok'];assert f.command('pointer 1500 1100')['ok']
  f.wait(lambda:js('return window.callback===true'));time.sleep(.15)
  # Search notifications are queued by the original engine, not synchronous.
  try:f.wait(lambda:semantic()==expected)
  except AssertionError:pass
  actual=semantic()
  actual_state=js('const e=document.getElementById('+json.dumps(name)+');return {present:!!e,value:e?.value??null,focused:document.activeElement.id,callback:window.callback,type:e?.type??null,disabled:e?.disabled??null}')
  check(label+'-native-search-matches-original-enter',actual==expected and actual_state==expected_state,actual=actual,expected=expected,state=actual_state,expected_state=expected_state)
  if actual_state['present'] and actual_state['type']=='search':f.pixels(name,actual_state['focused']==name,label=label+'-after-native-search')
