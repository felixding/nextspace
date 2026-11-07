"""Real GNUstep search controls through the common browser text binding."""
import json,time
from form_text_regression import TextFixture

class SearchFixture(TextFixture):
 def control_model(self,identifier):
  model=super().control_model(identifier)
  if self.js('return document.getElementById('+json.dumps(identifier)+').type')=='search':model['kind']=14
  return model

def run(f):
 js,check=f.js,f.check
 def ctrl(code):
  assert f.command('key 29 1')['ok'];f.key(code);assert f.command('key 29 0')['ok']
 def alt(code):
  assert f.command('key 56 1')['ok'];f.key(code);assert f.command('key 56 0')['ok']
 check('native-search-document',js('return document.title')=='Native search fields')
 assert f.command('pointer 1500 1100')['ok']
 for name in ['searchfield','readonly','disabled','limited']:f.pixels(name,label=name+'-initial')
 js('searchfield.focus();searchfield.setSelectionRange(3,3);window.events=[];return true');ctrl(30)
 check('search-native-emacs-beginning',js('return searchfield.selectionStart===0&&searchfield.selectionEnd===0'))
 f.key(45)
 edits=js("return events.filter(e=>e.type==='beforeinput'||e.type==='input')")
 check('search-original-trusted-edit',js('return searchfield.value==="xAlpha beta"') and [e['type'] for e in edits]==['beforeinput','input'] and all(e['trusted'] for e in edits),events=edits)
 f.pixels('searchfield',True,label='search-edited')
 js('searchfield.addEventListener("beforeinput",e=>e.preventDefault(),{once:true});window.events=[];return true');f.key(45)
 check('search-page-cancellation-retains-canonical-model',js('return searchfield.value==="xAlpha beta"&&!events.some(e=>e.type==="input")'))
 f.pixels('searchfield',True,label='search-cancelled')
 js('readonly.focus();readonly.setSelectionRange(0,0);window.events=[];return true');f.key(45)
 check('search-readonly-retains-original-value',js('return readonly.value==="Read only"&&!events.some(e=>e.type==="input")'))
 f.pixels('readonly',True,label='search-readonly-input')
 js('searchfield.value="Inactive search";return true');f.pixels('searchfield',label='search-inactive-script-update')
 js('searchfield.value="Copy search";searchfield.focus();searchfield.select();window.events=[];return true');alt(46)
 copied=js("return events.filter(e=>e.type==='copy')");check('search-native-alt-copy',len(copied)==1 and copied[0]['trusted'],events=copied)
 js('peer.focus();window.events=[];return true');alt(47);f.wait(lambda:js('return peer.value==="Copy search"'))
 check('search-clipboard-reaches-original-peer',js('return peer.value==="Copy search"'))
 js('peer.value="Paste search";peer.select();window.events=[];return true');alt(46)
 js('searchfield.focus();searchfield.select();window.events=[];return true');alt(47);f.wait(lambda:js('return searchfield.value==="Paste search"'))
 edits=js("return events.filter(e=>['paste','beforeinput','input'].includes(e.type))")
 check('search-native-paste-retains-trusted-events',[e['type'] for e in edits]==['paste','beforeinput','input'] and all(e['trusted'] for e in edits),events=edits)
 f.pixels('searchfield',True,label='search-after-paste')
 js('limited.focus();limited.setSelectionRange(0,0);window.events=[];return true')
 for _ in range(4):f.key(45)
 check('search-original-maxlength',js('return limited.value==="xxabc"'),value=js('return limited.value'))
 f.pixels('limited',True,label='search-maxlength')
 for number,kind in enumerate(['text','search','url','search','email','search']):
  js('dynamic.type='+json.dumps(kind)+';dynamic.value="Alpha beta";dynamic.focus();window.events=[];return true');ctrl(30);f.key(45)
  check('search-immediate-'+str(number)+'-'+kind+'-native-model',js('return dynamic.value==="xAlpha beta"'),value=js('return dynamic.value'))
  if kind!='email':f.pixels('dynamic',True,label='search-transition-'+str(number)+'-'+kind)

 buttons(f)

def buttons(f):
 js,check=f.js,f.check
 def click(name,reference):
  rect=reference['search_parts']['cancel'];box=f.control_model(name)['rect'];origin=f.origin()
  x=round(origin[0]+box['x']+rect['x']+rect['width']/2);y=round(origin[1]+box['y']+rect['y']+rect['height']/2)
  assert f.command('pointer '+str(x)+' '+str(y))['ok']
  assert f.command('button 272 1')['ok'];time.sleep(.04);assert f.command('button 272 0')['ok'];assert f.command('pointer 1500 1100')['ok']

 js('searchfield.value="Clear search";searchfield.focus();searchfield.setSelectionRange(2,2);window.events=[];return true')
 reference=f.pixels('searchfield',True,label='search-before-native-clear')
 click('searchfield',reference)
 f.wait(lambda:js('return searchfield.value===""'))
 events=js("return events.filter(e=>e.type==='beforeinput'||e.type==='input')")
 check('search-native-clear-updates-original-engine',js('return searchfield.value===""') and [e['type'] for e in events]==['beforeinput','input'] and all(e['trusted'] for e in events),events=events)
 f.pixels('searchfield',True,label='search-native-cleared')

 js('searchfield.value="Keep search";searchfield.focus();searchfield.setSelectionRange(2,2);searchfield.addEventListener("beforeinput",e=>e.preventDefault(),{once:true});window.events=[];return true')
 reference=f.pixels('searchfield',True,label='search-before-cancelled-clear')
 click('searchfield',reference)
 f.wait(lambda:js('return events.some(e=>e.type==="beforeinput")'))
 check('search-native-clear-retains-page-cancellation',js('return searchfield.value==="Keep search"&&!events.some(e=>e.type==="input")'),events=js('return events'))
 f.pixels('searchfield',True,label='search-native-cancelled-clear')

 for name,expected in [('readonly','Read only'),('disabled','Disabled')]:
  js('window.events=[];return true');reference=f.pixels(name,name=='readonly',label=name+'-before-clear')
  click(name,reference);f.pixels(name,name=='readonly',label=name+'-after-clear')
  check(name+'-native-clear-keeps-original-model',js('return document.getElementById('+json.dumps(name)+').value')==expected and not js('return events.some(e=>e.type==="input")'),events=js('return events'))

 js('searchfield.value="Retire search";searchfield.focus();searchfield.setSelectionRange(2,2);searchfield.addEventListener("beforeinput",e=>e.currentTarget.remove(),{once:true});window.events=[];return true')
 reference=f.pixels('searchfield',True,label='search-before-retired-clear')
 records=[json.loads(v) for v in (f.root.parent/'helper.jsonl').read_text().splitlines()]
 owner=next(x for x in records if x['event']=='native-form-control' and x.get('kind')==14)
 click('searchfield',reference)
 f.wait(lambda:js('return !document.getElementById("searchfield")'))
 check('search-native-clear-callback-can-retire-control',js('return !document.getElementById("searchfield")&&!events.some(e=>e.type==="input")'),events=js('return events'))
 check('search-native-clear-retirement-releases-native-lifetime',f.wait(lambda:any(x['event']=='native-form-destroy' and x.get('control')==owner['control'] and x.get('process')==owner['process'] for x in map(json.loads,(f.root.parent/'helper.jsonl').read_text().splitlines()))))

def key_retirement(f):
 """Chromium may finish a native pointer gesture before handling a key."""
 js,check=f.js,f.check
 js('dynamic.value="Held clear";dynamic.focus();dynamic.setSelectionRange(2,2);dynamic.addEventListener("mousedown",()=>window.heldDown=true,{once:true});dynamic.addEventListener("beforeinput",e=>e.currentTarget.remove(),{once:true});window.events=[];return true')
 reference=f.pixels('dynamic',True,label='search-before-key-retirement')
 rect=reference['search_parts']['cancel'];box=f.control_model('dynamic')['rect'];origin=f.origin()
 records=[json.loads(v) for v in (f.root.parent/'helper.jsonl').read_text().splitlines()]
 live={(x['process'],x['control']) for x in records if x['event']=='native-form-control' and x.get('kind')==14}
 retired={(x['process'],x['control']) for x in records if x['event']=='native-form-destroy'};live-=retired
 assert f.command('pointer '+str(round(origin[0]+box['x']+rect['x']+rect['width']/2))+' '+str(round(origin[1]+box['y']+rect['y']+rect['height']/2)))['ok']
 assert f.command('button 272 1')['ok'];f.wait(lambda:js('return window.heldDown===true'))
 try:
  for pressed in [1,0]:assert f.command('key 45 '+str(pressed))['ok']
  f.wait(lambda:js('return !document.getElementById("dynamic")'))
 finally:
  assert f.command('button 272 0')['ok'];assert f.command('pointer 1500 1100')['ok']
 edits=js("return events.filter(e=>e.type==='beforeinput'||e.type==='input')")
 check('search-key-can-retire-active-native-pointer',js('return !document.getElementById("dynamic")') and len(edits)==1 and edits[0]['type']=='beforeinput' and edits[0]['trusted'] and edits[0]['inputType'].startswith('delete'),events=edits)
 def released():
  return live&{(x['process'],x['control']) for x in map(json.loads,(f.root.parent/'helper.jsonl').read_text().splitlines()) if x['event']=='native-form-destroy'}
 check('search-key-retirement-releases-native-lifetime',f.wait(lambda:len(released())==1),released=sorted(released()))
