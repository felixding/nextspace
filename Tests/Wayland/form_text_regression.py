"""Focused regression for the shared form paint/input lifetime path."""
import json
from native_popup_fixture import PopupFixture

class TextFixture(PopupFixture):
 def control_model(self,identifier):
  return self.js("const e=document.getElementById("+json.dumps(identifier)+");return {id:e.id,kind:e.type==='password'?8:7,title:'',state:0,value:0,text:e.value,width:e.offsetWidth,height:e.offsetHeight,enabled:!e.disabled,editable:!e.readOnly,selection_start:e.selectionStart,selection_length:e.selectionEnd-e.selectionStart,rect:e.getBoundingClientRect().toJSON()}")

def run(fixture):
 js,check=fixture.js,fixture.check
 check('shared-form-text-document',js('return document.title')=='Blink native text transport')
 fixture.command('pointer 1500 1100')
 for identifier in ['normal','password','readonly','disabled','unicode']:fixture.pixels(identifier,label='text-'+identifier)
 js("normal.focus();normal.setSelectionRange(2,2);window.events=[];return true")
 fixture.command('key 29 1');fixture.key(30);fixture.command('key 29 0')
 check('shared-form-native-emacs-beginning',js('return normal.selectionStart===0&&normal.selectionEnd===0'))
 fixture.key(45)
 events=js("return events.filter(e=>e.type==='beforeinput'||e.type==='input')")
 check('shared-form-native-text-insertion',js("return normal.value==='xHello'"),events=events)
 check('shared-form-one-trusted-edit',[e['type'] for e in events]==['beforeinput','input'] and all(e['trusted'] for e in events))
 fixture.pixels('normal',True,label='text-after-edit')
 js("normal.addEventListener('beforeinput',e=>e.preventDefault(),{once:true});normal.focus();window.events=[];return true")
 fixture.key(45);check('shared-form-cancelled-edit-keeps-model',js("return normal.value==='xHello'&&!events.some(e=>e.type==='input')"))
 js("readonly.focus();readonly.setSelectionRange(0,0);window.events=[];return true")
 fixture.key(45);check('shared-form-readonly-keeps-model',js("return readonly.value==='Hello'&&!events.some(e=>e.type==='input')"))
 js("readonly.focus();normal.value='Inactive update';return true")
 fixture.pixels('normal',label='text-inactive-script-update')
