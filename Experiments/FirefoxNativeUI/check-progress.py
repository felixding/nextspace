#!/usr/bin/env python3
"""Qualify the owned Gecko fixture against separately rendered native images."""
import argparse,base64,io,json
from pathlib import Path
from PIL import Image,ImageChops
from marionette import Marionette

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--port',type=int,default=2829)
parser.add_argument('--expected-pid',type=int,required=True)
parser.add_argument('--references',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
results=[]
def check(case,condition,**details):
    results.append(dict(case=case,passed=bool(condition),**details))
    (args.output/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    assert condition,results[-1]
client=Marionette(args.port)
def execute(script):
    return client.command('WebDriver:ExecuteScript',dict(script=script,args=[]))['value']
def screenshot(label):
    result=client.command('WebDriver:TakeScreenshot',dict(full=False))
    data=base64.b64decode(result['value']);(args.output/(label+'.png')).write_bytes(data)
    return Image.open(io.BytesIO(data)).convert('RGB')
def compare(identifier,reference,label):
    rect=execute('return document.getElementById('+json.dumps(identifier)+').getBoundingClientRect().toJSON()')
    image=screenshot(label);x,y,w,h=[round(rect[k]) for k in ('x','y','width','height')]
    actual=image.crop((x,y,x+w,y+h))
    expected=Image.open(args.references/(reference+'.png')).convert('RGBA')
    background=Image.new('RGBA',expected.size,'white');background.alpha_composite(expected)
    difference=ImageChops.difference(actual,background.convert('RGB')).getbbox() if actual.size==expected.size else 'size'
    check(label,difference is None,difference=difference,actual_size=actual.size,reference_size=expected.size)
try:
    session=client.command('WebDriver:NewSession',{})
    assert session['capabilities']['moz:processID']==args.expected_pid,'Use only the owned fixture process'
    (args.output/'session.json').write_text(json.dumps(session,indent=2)+'\n')
    check('owned-fixture',client.command('WebDriver:GetTitle')['value']=='Gecko native progress transport')
    client.command('WebDriver:Refresh')
    client.command('WebDriver:SetWindowRect',dict(width=900,height=700))
    for identifier in ('normal','empty','full'):compare(identifier,identifier,'initial-'+identifier)
    styled=execute('return document.getElementById("styled").getBoundingClientRect().toJSON()')
    x,y,w,h=[round(styled[k]) for k in ('x','y','width','height')]
    styled_image=screenshot('styled').crop((x,y,x+w,y+h))
    check('author-styled-path-preserved',styled_image.getpixel((10,h//2))==(0,255,0) and styled_image.getpixel((w-10,h//2))==(255,0,255))
    execute('window.events=[]; for(let p of document.querySelectorAll("progress")) for(let type of ["input","change","click"]) p.addEventListener(type,e=>events.push({id:e.target.id,type:e.type,trusted:e.isTrusted})); return true')
    element=client.command('WebDriver:FindElement',dict(using='css selector',value='#normal'))
    client.command('WebDriver:ElementClick',dict(id=next(iter(element["value"].values()))))
    check('trusted-read-only-click',execute('return events.length===1 && events[0].id==="normal" && events[0].type==="click" && events[0].trusted'))
    execute('document.getElementById("normal").value=61;return true')
    compare('normal','value-61','value-update')
    execute('document.getElementById("normal").max=76.25;return true')
    check('normalized-engine-value',execute('return document.getElementById("normal").position')==.8)
    compare('normal','value-80','maximum-update')
    execute('document.getElementById("normal").value=999;return true')
    compare('normal','full','engine-clamped-value')
    execute('document.getElementById("normal").value=-10;return true')
    compare('normal','empty','engine-negative-value')
    execute('document.getElementById("normal").removeAttribute("value");return true')
    check('indeterminate-engine-model',execute('return document.getElementById("normal").position')==-1)
    execute('let p=document.getElementById("normal");p.max=100;p.value=42;return true')
    compare('normal','normal','determinate-restored')
    execute('document.getElementById("normal").style.cssText="width:320px;height:17px";return true')
    compare('normal','resized','resize')
    execute('let p=document.getElementById("normal"),parent=p.parentNode;p.remove();parent.prepend(p);return true')
    compare('normal','resized','remove-reinsert')
    execute('let p=document.getElementById("normal"),n=p.cloneNode();n.max=3;n.value=1.5;p.replaceWith(n);return true')
    compare('normal','replacement','new-engine-element')
    check('updates-do-not-edit-model',execute('return events.length===1 && events.every(e=>e.type==="click")'))
    button=client.command('WebDriver:FindElement',dict(using='css selector',value='#button'))
    client.command('WebDriver:ElementClick',dict(id=next(iter(button["value"].values()))))
    check('ordinary-engine-action',execute('return document.getElementById("button").textContent')=='Activated')
    client.command('WebDriver:Refresh')
    compare('normal','normal','reload-initial-control')
    compare('full','full','reload-full-control')
    client.command('WebDriver:Navigate',dict(url='about:blank'))
    check('navigation-away',client.command('WebDriver:GetTitle')['value']=='')
    print(json.dumps(dict(passed=len(results))),flush=True)
finally:
    client.close()
