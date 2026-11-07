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
 for identifier,display,other in [('flex','inline-flex','inline-grid'),('grid','inline-grid','inline-flex')]:
  target='document.getElementById('+json.dumps(identifier)+')'
  for suffix,title in [('grown','A longer native layout button'),('unicode','日本語Café🙂'),('empty','')]:
   js(target+'.textContent='+json.dumps(title)+';return true');compare(identifier,identifier+'-title-'+suffix)
  js(target+".textContent='Native layout button';return true");compare(identifier,identifier+'-title-restored')
  js(target+".style.minWidth='300px';return true")
  preferred=measure(identifier,identifier+'-minimum-probe');compare(identifier,identifier+'-minimum',expected=[max(300,preferred[0]),preferred[1]])
  js(target+".style.minWidth='';"+target+".style.maxWidth='90px';return true")
  preferred=measure(identifier,identifier+'-maximum-probe');compare(identifier,identifier+'-maximum',expected=[min(90,preferred[0]),preferred[1]])
  js(target+".style.cssText='display:"+display+";width:180px;height:31px;box-sizing:border-box';return true");compare(identifier,identifier+'-fixed',expected=[180,31])
  js(target+".textContent='123456';return true");compare(identifier,identifier+'-fixed-title-first',expected=[180,31])
  before=measure(identifier,identifier+'-fixed-title-first-probe')
  js(target+".firstChild.data='654321';return true");compare(identifier,identifier+'-fixed-title-changed',expected=[180,31])
  after=measure(identifier,identifier+'-fixed-title-changed-probe')
  check(identifier+'-changed-title-keeps-native-preferred-size',before==after,before=before,after=after)
  for width in ['min-content','max-content']:
   js(target+".style.cssText='display:"+display+";width:"+width+"';return true");compare(identifier,identifier+'-'+width)
  js(target+".style.cssText='display:"+other+"';return true");compare(identifier,identifier+'-display-changed')
 for display in ['inline-flex','inline-grid']:
  actual=js("const e=document.createElement('div');e.style.cssText='display:"+display+";gap:8px;grid-template-columns:37px 53px';e.innerHTML='<span style=\"width:37px;height:11px\"></span><span style=\"width:53px;height:11px\"></span>';document.body.append(e);const r=e.getBoundingClientRect().toJSON();e.remove();return r")
  check('ordinary-'+display+'-retains-engine-layout',actual['width']==98 and actual['height']==11,actual=actual)
 check('native-button-size-changes-emit-no-actions',js("return !events.some(e=>['click','submit','reset'].includes(e.type))"))
 for identifier,event in [('automatic','click'),('submit','submit'),('reset','reset')]:
  js("window.events=[];document.getElementById('form-value').value='changed';document.getElementById("+json.dumps(identifier)+").focus();return true")
  fixture.key(57)
  entries=js('return events.filter(e=>e.type==='+json.dumps(event)+')')
  check(identifier+'-one-original-trusted-action',len(entries)==1 and entries[0]['trusted'],events=entries)
  if identifier=='reset':check('native-reset-updates-original-form',js("return document.getElementById('form-value').value==='original'"))
 js("window.events=[];document.getElementById('automatic').addEventListener('keydown',e=>e.preventDefault(),{once:true});document.getElementById('automatic').focus();return true")
 fixture.key(57);check('cancelled-native-button-key-has-no-action',js("return !events.some(e=>e.type==='click')"))
