"""Search notifications remain owned by each original browser engine."""
import json,time

def run(f):
 js,check=f.js,f.check
 check('native-search-notification-document',js('return document.title')=='Native search notifications')
 def reset(name,incremental=False):
  js('restore();const e=document.getElementById('+json.dumps(name)+');e.toggleAttribute("incremental",'+str(incremental).lower()+');e.focus();e.setSelectionRange(2,2);events=[];return true')
 def notifications(name):
  return js('return events.filter(e=>e.type==="search"&&e.id==='+json.dumps(name)+').map(({trusted,value})=>({trusted,value}))')
 def click(reference):
  rect=reference['search_parts']['cancel'];box=f.control_model('single')['rect'];origin=f.origin()
  assert f.command('pointer '+str(round(origin[0]+box['x']+rect['x']+rect['width']/2))+' '+str(round(origin[1]+box['y']+rect['y']+rect['height']/2)))['ok']
  assert f.command('button 272 1')['ok'];time.sleep(.04);assert f.command('button 272 0')['ok'];assert f.command('pointer 1500 1100')['ok']
 def bind(name,event,body):
  if body:js('document.getElementById('+json.dumps(name)+').addEventListener('+json.dumps(event)+',e=>{'+body+'},{once:true});return true')
 for label,incremental,event,body,expected_value in [
  ('plain',False,'input','',''),('incremental',True,'input','',''),
  ('incremental-remove',True,'input','e.currentTarget.removeAttribute("incremental")',''),
  ('incremental-add',False,'input','e.currentTarget.setAttribute("incremental","")',''),
  ('input-value',False,'input','e.currentTarget.value="From input"','From input'),
  ('input-disabled',False,'input','e.currentTarget.disabled=true',''),
  ('search-value',False,'search','e.currentTarget.value="After search"','After search')]:
  reset('engineOracle',incremental)
  if label=='plain':
   assert f.command('key 29 1')['ok'];f.key(30);assert f.command('key 29 0')['ok']
   state=js('return {selection:[engineOracle.selectionStart,engineOracle.selectionEnd],length:engineOracle.value.length,appearance:getComputedStyle(engineOracle).appearance}')
   check('reference-retains-original-select-all',state['selection']==[0,state['length']] and state['appearance']=='none',state=state)
   js('engineOracle.setSelectionRange(2,2);events=[];return true')
  bind('engineOracle',event,body);f.key(1);time.sleep(.7)
  expected=notifications('engineOracle');canonical=js('return engineOracle.value')
  if event=='search' and not expected:expected_value='' # This engine has no search notification.
  check(label+'-original-escape-clears-reference',canonical==expected_value,events=expected,value=canonical)
  reset('single',incremental);bind('single',event,body)
  reference=f.pixels('single',True,label=label+'-before-native-notification');js('events=[];return true');click(reference);time.sleep(.7)
  try:f.wait(lambda:notifications('single')==expected and js('return single.value')==expected_value)
  except AssertionError:pass
  actual=notifications('single');state=js('return {value:single.value,disabled:single.disabled,focused:document.activeElement.id,events:events}')
  check(label+'-native-clear-matches-original-search-notifications',actual==expected and state['value']==expected_value,actual=actual,expected=expected,state=state)
  f.pixels('single',state['focused']=='single',label=label+'-after-native-notification')

 for label,event,body,value,present,kind in [
  ('click-cancel','click','e.preventDefault()','Clear search',True,'search'),
  ('edit-cancel','beforeinput','e.preventDefault()','Clear search',True,'search'),
  ('edit-cancel-empty','beforeinput','e.currentTarget.value="";e.preventDefault()','',True,'search'),
  ('nested-delete-cancel','beforeinput','e.currentTarget.select();document.execCommand("delete");e.preventDefault()','',True,'search'),
  ('nested-caret-delete-cancel','beforeinput','document.execCommand("delete");e.preventDefault()','Cear search',True,'search'),
  ('input-retype','input','e.currentTarget.type="text"','',True,'text'),
  ('input-remove','input','e.currentTarget.remove()',None,False,None),
  ('readonly','','','Clear search',True,'search'),('disabled','','','Clear search',True,'search'),
  ('empty','','','',True,'search')]:
  if label=='nested-caret-delete-cancel':
   reset('engineOracle');bind('engineOracle',event,body);f.key(14);time.sleep(.7)
   original=js('return {value:engineOracle.value,events:events}')
   check('nested-script-delete-keeps-original-engine-range',original['value']==value,state=original)
  reset('single');js('single.readOnly='+str(label=='readonly').lower()+';single.disabled='+str(label=='disabled').lower()+';'+('single.value="";' if label=='empty' else '')+'return true')
  bind('single',event,body);reference=f.pixels('single',label!='disabled',label=label+'-before-no-notification');js('events=[];return true');click(reference);time.sleep(.7)
  state=js("const e=document.getElementById('single');return {present:!!e,value:e?.value??null,type:e?.type??null,focused:document.activeElement.id,events:events}")
  actual=notifications('single')
  check(label+'-does-not-notify-a-cancelled-or-inapplicable-clear',not actual and state['present']==present and state['value']==value and state['type']==kind,state=state,search=actual)
  if present and kind=='search':f.pixels('single',state['focused']=='single',label=label+'-after-no-notification')
