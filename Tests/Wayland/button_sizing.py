"""Native button size, complete pixels and original form actions on the real seat."""
import json
from pathlib import Path
from native_popup_fixture import PopupFixture

class ButtonFixture(PopupFixture):
 def control_model(self,identifier):
  return self.js("const e=document.getElementById("+json.dumps(identifier)+");return {id:e.id,kind:1,title:e.tagName==='INPUT'?e.value:e.innerText,state:0,width:e.offsetWidth,height:e.offsetHeight,enabled:!e.disabled,rect:e.getBoundingClientRect().toJSON()}")

def run(fixture):
 js,check,command=fixture.js,fixture.check,fixture.command
 check('native-button-sizing-document',js('return document.title')=='Native button sizing')
 js('window.events=[];return true')
 command('pointer 1500 1100')
 def rect(identifier):return js('return document.getElementById('+json.dumps(identifier)+').getBoundingClientRect().toJSON()')
 def measure(identifier,label):
  data=fixture.control_model(identifier);data['preferred_size']=True
  reply=command('reference '+json.dumps(dict(name=label+'-size-reference',controls=[data])))
  return json.loads((Path(reply['path'])/'results.json').read_text())[0]['size']
 def compare(identifier,label=None,expected=None):
  label=label or identifier;preferred=measure(identifier,label);expected=expected or preferred
  try:matching=fixture.wait(lambda:rect(identifier)['width']==expected[0] and rect(identifier)['height']==expected[1])
  except AssertionError:matching=False
  check(label+'-native-size',matching,preferred=preferred,expected=expected,actual=rect(identifier));fixture.pixels(identifier,label=label)
 for identifier in ['automatic','empty','disabled','unicode','nested','input-button','submit','reset','flex','grid']:compare(identifier)
 compare('fixed',expected=[180,31])
 minimum=measure('minimum','minimum-probe');compare('minimum',expected=[max(300,minimum[0]),minimum[1]])
 maximum=measure('maximum','maximum-probe');compare('maximum',expected=[min(90,maximum[0]),maximum[1]])
 js("document.getElementById('automatic').textContent='A much longer native button label';return true");compare('automatic','title-grown')
 js("document.getElementById('automatic').firstChild.data='Short';return true");compare('automatic','title-shrunk')
 js("document.getElementById('nested').firstElementChild.firstChild.data='Changed nested ';return true");compare('nested','nested-title-changed')
 js("document.getElementById('nested').lastElementChild.hidden=false;return true");compare('nested','hidden-title-revealed')
 js("document.getElementById('input-button').value='Changed input value';return true");compare('input-button','input-value-changed')
 check('native-button-size-changes-emit-no-actions',js("return !events.some(e=>['click','submit','reset'].includes(e.type))"))
 for identifier,event in [('automatic','click'),('submit','submit'),('reset','reset')]:
  js("window.events=[];document.getElementById('form-value').value='changed';document.getElementById("+json.dumps(identifier)+").focus();return true")
  fixture.key(57)
  entries=js('return events.filter(e=>e.type==='+json.dumps(event)+')')
  check(identifier+'-one-original-trusted-action',len(entries)==1 and entries[0]['trusted'],events=entries)
  if identifier=='reset':check('native-reset-updates-original-form',js("return document.getElementById('form-value').value==='original'"))
 js("window.events=[];document.getElementById('automatic').addEventListener('keydown',e=>e.preventDefault(),{once:true});document.getElementById('automatic').focus();return true")
 fixture.key(57);check('cancelled-native-button-key-has-no-action',js("return !events.some(e=>e.type==='click')"))
