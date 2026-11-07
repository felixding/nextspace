"""Native email editors preserve the engine's protected public selection API."""
import json
from form_text_regression import TextFixture

class EmailFixture(TextFixture):
 def control_model(self,identifier):
  data=super().control_model(identifier)
  # Public email selection is deliberately null. Focused comparisons below
  # drive an independent native editor with text_keys instead of inventing it.
  if data['selection_start'] is None:data.update(selection_start=0,selection_length=0)
  return data

def first_key(f):
 seed='seed@example.test'
 data=f.control_model('dynamic');data.update(kind=7,text=seed,selection_start=2,selection_length=0,text_keys=[dict(text='a',modifiers=4),dict(text='x')])
 reply=f.command('reference '+json.dumps(dict(name='first-key-native-reference',controls=[data],focus=True)))
 from pathlib import Path
 expected=json.loads((Path(reply['path'])/'results.json').read_text())[0]['text_keys'][-1]['value']
 for number,kind in enumerate(['text','url','tel','email']*3):
  f.js('dynamic.type='+json.dumps(kind)+';dynamic.value='+json.dumps(seed)+';dynamic.focus();window.events=[];return true')
  assert f.command('key 29 1')['ok'];f.key(30);assert f.command('key 29 0')['ok'];f.key(45)
  actual=f.js('return {value:dynamic.value,type:dynamic.type,start:dynamic.selectionStart,end:dynamic.selectionEnd}')
  f.check('first-key-'+str(number)+'-'+kind+'-matches-native-editor',actual['value']==expected,state=actual,expected=expected)
 f.pixels('dynamic',True,model=dict(text=seed,selection_start=2,selection_length=0,text_keys=[dict(text='a',modifiers=4),dict(text='x')]),label='first-key-final')

def run(f):
 js,check=f.js,f.check
 def ctrl(code):
  assert f.command('key 29 1')['ok'];f.key(code);assert f.command('key 29 0')['ok']
 def alt(code):
  assert f.command('key 56 1')['ok'];f.key(code);assert f.command('key 56 0')['ok']
 def contract(name,label):
  data=js('const e=document.getElementById('+json.dumps(name)+');let error=null;try{e.setSelectionRange(0,0)}catch(x){error=x.name}return {start:e.selectionStart,end:e.selectionEnd,direction:e.selectionDirection,error}')
  check(label+'-original-public-selection-contract',data==dict(start=None,end=None,direction=None,error='InvalidStateError'),state=data)
 home=dict(text='a',modifiers=4);insert=dict(text='x')
 check('native-email-document',js('return document.title')=='Native email fields')
 for name in ['emailfield','multiple','readonly','disabled','limited']:
  contract(name,name+'-initial');f.pixels(name,label=name+'-initial')
 for name in ['emailfield','multiple']:
  before=js('return '+name+'.value');js(name+'.focus();window.events=[];return true');ctrl(30);f.key(45)
  reference=f.pixels(name,True,model=dict(text=before,selection_start=2,selection_length=0,text_keys=[home,insert]),label=name+'-native-edit')
  expected=reference['text_keys'][-1]
  check(name+'-native-emacs-edit-matches-independent-editor',js('return '+name+'.value')==expected['value'],native=expected,value=js('return '+name+'.value'))
  edits=js("return events.filter(e=>e.type==='beforeinput'||e.type==='input')")
  check(name+'-one-original-trusted-edit',[e['type'] for e in edits]==['beforeinput','input'] and all(e['trusted'] and e['inputType']=='insertText' and e['start'] is None and e['end'] is None for e in edits),events=edits)
  contract(name,name+'-edited')
  current=js('return '+name+'.value');js(name+'.addEventListener("beforeinput",e=>e.preventDefault(),{once:true});window.events=[];return true');f.key(45)
  check(name+'-page-cancellation-keeps-original-value',js('return '+name+'.value')==current and not js("return events.some(e=>e.type==='input')"))
  f.pixels(name,True,model=dict(text=current,selection_start=expected['start'],selection_length=expected['end']-expected['start'],text_keys=[insert],text_veto=True),label=name+'-cancelled')
 js('readonly.focus();window.events=[];return true');ctrl(30);f.key(45)
 check('email-readonly-keeps-original-model',js('return readonly.value==="user@example.test"&&!events.some(e=>e.type==="input")'))
 f.pixels('readonly',True,model=dict(selection_start=(1<<64)-1,selection_length=0,focus_after_model=True,text_keys=[home,insert]),label='readonly-after-input')
 js('emailfield.value="not an email";return true')
 check('email-original-invalidity-retained',js('return emailfield.validity.typeMismatch'))
 f.pixels('emailfield',label='email-invalid')
 js('multiple.value="  a@one.test , b@two.test  ";return true')
 canonical=js('const e=document.createElement("input");e.type="email";e.multiple=true;e.value="  a@one.test , b@two.test  ";return {actual:multiple.value,expected:e.value,valid:multiple.validity.valid,expectedValid:e.validity.valid}')
 check('multiple-email-original-sanitization-and-validity',canonical['actual']==canonical['expected'] and canonical['valid']==canonical['expectedValid'],state=canonical)
 f.pixels('multiple',label='multiple-canonical')
 js('multiple.multiple=false;return true')
 check('email-multiple-attribute-keeps-original-validation',js('return multiple.validity.typeMismatch'))
 f.pixels('multiple',label='multiple-to-single')
 js('emailfield.value="copy@example.test";emailfield.focus();window.events=[];return true');ctrl(30)
 assert f.command('key 42 1')['ok']
 for _ in 'copy@example.test':f.key(106)
 assert f.command('key 42 0')['ok']
 f.pixels('emailfield',True,model=dict(text='copy@example.test',text_keys=[home]+[dict(key=7,modifiers=1) for _ in 'copy@example.test']),label='email-before-copy-selection')
 alt(46)
 copied=js("return events.filter(e=>e.type==='copy')")
 check('email-native-keyboard-selection-and-alt-copy',len(copied)==1 and copied[0]['trusted'],events=copied)
 f.pixels('emailfield',True,model=dict(text='copy@example.test',text_keys=[home]+[dict(key=7,modifiers=1) for _ in 'copy@example.test']),label='email-native-selection')
 js('peer.value="";peer.focus();window.events=[];return true');alt(47);f.wait(lambda:js('return peer.value==="copy@example.test"'))
 check('native-email-copy-reaches-original-plain-field',js('return peer.value==="copy@example.test"'))
 js('peer.value="paste@example.test";peer.select();window.events=[];return true');alt(46)
 js('emailfield.focus();window.events=[];return true');ctrl(30)
 assert f.command('key 42 1')['ok']
 for _ in 'copy@example.test':f.key(106)
 assert f.command('key 42 0')['ok']
 alt(47);f.wait(lambda:js('return emailfield.value==="paste@example.test"'))
 pasted=js("return events.filter(e=>['paste','beforeinput','input'].includes(e.type))")
 check('native-email-paste-retains-original-trusted-events',[e['type'] for e in pasted]==['paste','beforeinput','input'] and all(e['trusted'] for e in pasted) and pasted[-1]['inputType']=='insertFromPaste',events=pasted)
 contract('emailfield','email-after-paste');f.pixels('emailfield',label='email-after-paste')
 js('limited.focus();window.events=[];return true');ctrl(30)
 for _ in range(4):f.key(45)
 check('email-original-maxlength-limits-native-edit',js('return limited.value==="xxa@b.test"&&limited.value.length===limited.maxLength'),value=js('return limited.value'))
 f.pixels('limited',label='email-maxlength')
 first_key(f)
 for number,kind in enumerate(['text','email','tel','email']):
  js('dynamic.type='+json.dumps(kind)+';dynamic.value="user@example.test";dynamic.focus();window.events=[];return true');ctrl(30);f.key(45)
  reference=f.pixels('dynamic',True,model=dict(text='user@example.test',selection_start=2,selection_length=0,text_keys=[home,insert]),label='dynamic-'+str(number)+'-'+kind)
  check('dynamic-'+str(number)+'-'+kind+'-native-edit',js('return dynamic.value')==reference['text_keys'][-1]['value'])
  if kind=='email':contract('dynamic','dynamic-'+str(number))
 owner=next(x for x in reversed([json.loads(v) for v in (f.root.parent/'helper.jsonl').read_text().splitlines()]) if x['event']=='native-form-control' and x.get('kind')==7)
 js('dynamic.addEventListener("beforeinput",e=>e.currentTarget.remove(),{once:true});window.events=[];return true')
 for pressed in [1,0]:assert f.command('key 45 '+str(pressed))['ok']
 f.wait(lambda:js('return !document.getElementById("dynamic")'))
 check('email-beforeinput-can-retire-native-control',js('return !document.getElementById("dynamic")&&!events.some(e=>e.type==="input")'))
 check('email-retirement-releases-native-lifetime',f.wait(lambda:any(x['event']=='native-form-destroy' and x.get('control')==owner['control'] and x.get('process')==owner['process'] for x in [json.loads(v) for v in (f.root.parent/'helper.jsonl').read_text().splitlines()])))
