"""URL/telephone fields through the existing real native text fixture."""
import json
from pathlib import Path

def run(f):
 js,check=f.js,f.check
 check('native-text-types-document',js('return document.title')=='Native text field types')
 assert f.command('pointer 1500 1100')['ok']
 for name in ['urlfield','telfield','readonly','disabled']:f.pixels(name,label=name+'-initial')
 for name in ['urlfield','telfield']:
  before=js('return '+name+'.value')
  js(name+'.focus();'+name+'.setSelectionRange(2,2);window.events=[];return true')
  assert f.command('key 29 1')['ok'];f.key(30);assert f.command('key 29 0')['ok']
  check(name+'-native-emacs-beginning',js('return '+name+'.selectionStart===0&&'+name+'.selectionEnd===0'))
  f.key(45)
  expected='x'+before
  edits=js("return events.filter(e=>e.type==='beforeinput'||e.type==='input')")
  check(name+'-native-insertion',js('return '+name+'.value')==expected,value=js('return '+name+'.value'))
  check(name+'-one-original-trusted-edit',[e['type'] for e in edits]==['beforeinput','input'] and all(e['trusted'] and e['inputType']=='insertText' for e in edits),events=edits)
  f.pixels(name,True,label=name+'-edited')
  js(name+'.addEventListener("beforeinput",e=>e.preventDefault(),{once:true});window.events=[];return true')
  f.key(45)
  check(name+'-page-cancellation-keeps-canonical-model',js('return '+name+'.value')==expected and not js("return events.some(e=>e.type==='input')"))
  f.pixels(name,True,label=name+'-cancelled')
 js('readonly.focus();readonly.setSelectionRange(0,0);window.events=[];return true');f.key(45)
 check('url-readonly-retains-original-model',js('return readonly.value==="https://example.org"&&!events.some(e=>e.type==="input")'))
 f.pixels('readonly',True,label='url-readonly-after-input')
 js('urlfield.value="not a url";urlfield.focus();urlfield.setSelectionRange(0,0);window.events=[];return true');f.key(45)
 check('url-original-validity-after-native-edit',js('return urlfield.value==="xnot a url"&&urlfield.validity.typeMismatch'))
 f.pixels('urlfield',True,label='url-invalid')
 check('telephone-original-pattern-after-native-edit',js('return telfield.value==="x+123456"&&telfield.validity.patternMismatch'))
 js('urlfield.value="Copy 123";urlfield.focus();urlfield.setSelectionRange(0,urlfield.value.length);window.events=[];return true')
 assert f.command('key 56 1')['ok'];f.key(46);assert f.command('key 56 0')['ok']
 copied=js("return events.filter(e=>e.type==='copy')")
 check('url-native-alt-copy-uses-original-trusted-command',len(copied)==1 and copied[0]['trusted'],events=copied)
 f.pixels('urlfield',True,label='url-after-copy')
 js('telfield.value="";telfield.focus();telfield.setSelectionRange(0,0);window.events=[];return true')
 assert f.command('key 56 1')['ok'];f.key(47);assert f.command('key 56 0')['ok']
 f.wait(lambda:js('return telfield.value==="Copy 123"'))
 pasted=js("return events.filter(e=>['paste','beforeinput','input'].includes(e.type))")
 check('telephone-native-alt-paste-uses-original-trusted-command',[e['type'] for e in pasted]==['paste','beforeinput','input'] and all(e['trusted'] for e in pasted) and pasted[-1]['inputType']=='insertFromPaste',events=pasted)
 f.pixels('telfield',True,label='telephone-after-paste')
 js('urlfield.value=" \\nhttps://example.org/path\\r ";return true')
 canonical=js('const other=document.createElement("input");other.type="url";other.value=" \\nhttps://example.org/path\\r ";return {actual:urlfield.value,expected:other.value}')
 check('url-script-sanitization-remains-original-engine',canonical['actual']==canonical['expected'],state=canonical)
 f.pixels('urlfield',True,label='url-canonical-script-value')
 for number,kind in enumerate(['tel','url','text','tel']):
  js('dynamic.type='+json.dumps(kind)+';dynamic.value="Hello";dynamic.focus();dynamic.setSelectionRange(2,2);window.events=[];return true')
  assert f.command('key 29 1')['ok'];f.key(30);assert f.command('key 29 0')['ok']
  selection=js('return {start:dynamic.selectionStart,end:dynamic.selectionEnd,value:dynamic.value,type:dynamic.type}')
  check('dynamic-'+kind+'-native-emacs-beginning',selection['start']==0 and selection['end']==0,state=selection)
  f.key(45)
  check('dynamic-'+kind+'-native-model',js('return dynamic.value==="xHello"'))
  f.pixels('dynamic',True,label='dynamic-'+str(number)+'-'+kind)
 owner=next(x for x in reversed([json.loads(v) for v in (f.root.parent/'helper.jsonl').read_text().splitlines()]) if x['event']=='native-form-control' and x.get('kind')==7)
 js('dynamic.addEventListener("beforeinput",e=>e.currentTarget.remove(),{once:true});window.events=[];return true')
 for pressed in [1,0]:assert f.command('key 45 '+str(pressed))['ok']
 f.wait(lambda:js('return !document.getElementById("dynamic")'))
 check('type-field-page-callback-can-retire-native-control',js('return !document.getElementById("dynamic")&&!events.some(e=>e.type==="input")'))
 check('type-field-retirement-releases-native-lifetime',f.wait(lambda:any(x['event']=='native-form-destroy' and x.get('control')==owner['control'] and x.get('process')==owner['process'] for x in [json.loads(v) for v in (f.root.parent/'helper.jsonl').read_text().splitlines()])))
