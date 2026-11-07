"""Canonical browser placeholders rendered by the original shared native cells."""
import json
from native_search_fields import SearchFixture

class PlaceholderFixture(SearchFixture):
 def control_model(self,identifier):
  model=super().control_model(identifier)
  model.update(self.js('const e=document.getElementById('+json.dumps(identifier)+');return {placeholder:e.getAttribute("placeholder"),selection_start:e.selectionStart??0,selection_length:(e.selectionEnd??0)-(e.selectionStart??0)}'))
  return model

def run(f):
 js,check=f.js,f.check
 check('native-placeholder-document',js('return document.title')=='Native field placeholders')
 assert f.command('pointer 1500 1100')['ok']
 for kind in ['text','password','search','url','tel','email']:
  js('field.type='+json.dumps(kind)+';field.value="";field.disabled=false;field.readOnly=false;field.placeholder="Find a word";peer.focus();window.events=[];return true')
  f.pixels('field',label=kind+'-placeholder')
  js('field.placeholder="検索α";return true');f.pixels('field',label=kind+'-unicode-placeholder')
  js('field.placeholder="Line1\\r\\nLine2";return true');f.pixels('field',model=dict(placeholder='Line1Line2'),label=kind+'-original-newline-normalization')
  js('field.placeholder="検索α";field.value="Existing";return true');f.pixels('field',label=kind+'-placeholder-with-value')
  js('field.value="";field.disabled=true;return true');f.pixels('field',label=kind+'-disabled-placeholder')
  js('field.disabled=false;field.readOnly=true;return true');f.pixels('field',label=kind+'-readonly-placeholder')
  js('field.readOnly=false;field.removeAttribute("placeholder");return true');f.pixels('field',label=kind+'-removed-placeholder')
  js('field.placeholder="";return true');f.pixels('field',label=kind+'-empty-placeholder')
  check(kind+'-placeholder-does-not-change-canonical-value-or-emit-edits',js('return field.value===""&&events.length===0'),events=js('return events'))
  js('field.placeholder="Type here";field.focus();window.events=[];return true');f.key(45)
  check(kind+'-native-edit-retains-trusted-engine-events',js('return field.value==="x"&&events.filter(e=>e.type==="input").length===1&&events.every(e=>e.trusted)'),events=js('return events'))
  f.pixels('field',True,model=dict(text='',selection_start=0,selection_length=0,text_keys=[dict(text='x')]) if kind=='email' else None,label=kind+'-typed-over-placeholder')
  js('field.addEventListener("beforeinput",e=>{e.preventDefault();e.currentTarget.placeholder="Cancelled hint";},{once:true});window.events=[];return true');f.key(45)
  state=js('return {value:field.value,placeholder:field.placeholder,events:events}')
  check(kind+'-placeholder-callback-retains-cancelled-value',state['value']=='x' and not any(e['type']=='input' for e in state['events']),state=state)
  js('field.value="";return true');f.pixels('field',label=kind+'-callback-placeholder')
 check('native-placeholder-final-control-alive',js('return !!field&&field.placeholder==="Cancelled hint"'))
