"""Real native clear gestures respect the application's click default phase."""
import json,time

def run(f):
 js,check=f.js,f.check
 check('native-clear-default-document',js('return document.title')=='Native search actions')
 cases=[
  ('cancel','e.preventDefault()',True,'Clear search',['click']),
  ('normal','',True,'',['click','beforeinput','input']),
  ('value','e.currentTarget.value="Changed"',True,'',['click','beforeinput','input']),
  ('disable','e.currentTarget.disabled=true',True,'Clear search',['click']),
  ('remove','e.currentTarget.remove()',False,None,['click']),
  ('focus','explicit.focus()',True,'Clear search',['click']),
  ('retype','e.currentTarget.type="hidden"',True,'Clear search',['click']),
  ('beforeinput-cancel','',True,'Clear search',['click','beforeinput']),
  ('beforeinput-remove','',False,None,['click','beforeinput'])]
 for label,body,present,value,types in cases:
  js('restore();single.value="Clear search";single.focus();single.setSelectionRange(2,2);window.clearClicked=false;window.seenValue=null;return true')
  reference=f.pixels('single',True,label=label+'-before-native-clear')
  js('single.addEventListener("click",e=>{window.seenValue=e.currentTarget.value;'+body+';window.clearClicked=true},{once:true});events=[];return true')
  if label.startswith('beforeinput-'):
   action='e.preventDefault()' if label.endswith('cancel') else 'e.currentTarget.remove()'
   js('single.addEventListener("beforeinput",e=>{'+action+'},{once:true});return true')
  rect=reference['search_parts']['cancel'];box=f.control_model('single')['rect'];origin=f.origin()
  x=round(origin[0]+box['x']+rect['x']+rect['width']/2);y=round(origin[1]+box['y']+rect['y']+rect['height']/2)
  assert f.command('pointer '+str(x)+' '+str(y))['ok'];assert f.command('button 272 1')['ok'];time.sleep(.04);assert f.command('button 272 0')['ok'];assert f.command('pointer 1500 1100')['ok']
  f.wait(lambda:js('return window.clearClicked'));time.sleep(.15)
  def state():
   return js("const e=document.getElementById('single');return {present:!!e,value:e?.value??null,type:e?.type??null,disabled:e?.disabled??null,seen:window.seenValue,focused:document.activeElement.id,peer:explicit.value,events:events.filter(e=>['click','beforeinput','input','submit'].includes(e.type))}")
  try:f.wait(lambda:state()['present']==present and state()['value']==value and [e['type'] for e in state()['events']]==types)
  except AssertionError:pass
  actual=state();events=actual['events']
  okay=actual['present']==present and actual['value']==value and actual['seen']=='Clear search' and actual['peer']=='Alpha' and [e['type'] for e in events]==types and all(e['trusted'] for e in events)
  if label=='focus':okay=okay and actual['focused']=='explicit'
  if label=='value':okay=okay and events[1]['value']=='Changed'
  check(label+'-native-clear-respects-click-default',okay,state=actual,expected=dict(present=present,value=value,event_types=types,click_value='Clear search'))
  if actual['present'] and actual['type']=='search':f.pixels('single',actual['focused']=='single',label=label+'-after-native-clear')

 key_interruption(f)

def key_interruption(f):
 js,check=f.js,f.check
 # A real key may end native tracking before the physical mouse release.
 js('restore();single.value="Clear search";single.focus();single.setSelectionRange(2,2);window.held=false;single.addEventListener("mousedown",()=>window.held=true,{once:true});events=[];return true')
 reference=f.pixels('single',True,label='key-interruption-before-native-clear')
 rect=reference['search_parts']['cancel'];box=f.control_model('single')['rect'];origin=f.origin()
 assert f.command('pointer '+str(round(origin[0]+box['x']+rect['x']+rect['width']/2))+' '+str(round(origin[1]+box['y']+rect['y']+rect['height']/2)))['ok']
 assert f.command('button 272 1')['ok'];f.wait(lambda:js('return window.held'))
 try:
  assert f.command('key 29 1')['ok'];f.key(30);assert f.command('key 29 0')['ok']
  selection=js('return [single.selectionStart,single.selectionEnd]')
  check('key-interruption-keeps-native-emacs-navigation',selection==[0,0],selection=selection)
  f.key(45)
 finally:
  assert f.command('button 272 0')['ok'];assert f.command('pointer 1500 1100')['ok']
 time.sleep(.15);actual=js("return {value:single.value,events:events.filter(e=>['beforeinput','input','submit'].includes(e.type))}")
 check('key-interruption-cancels-pending-native-clear',actual['value']=='xClear search' and [e['type'] for e in actual['events']]==['beforeinput','input'] and all(e['trusted'] and e['inputType']=='insertText' and e['data']=='x' for e in actual['events']),state=actual)
 f.pixels('single',True,label='key-interruption-after-native-clear')
