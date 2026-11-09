"""Physical keyboard focus on original shared color-panel reuse."""
import argparse
import json
from native_date_fields import ChromiumDates, FirefoxDates

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root',required=True)
parser.add_argument('--firefox-port',type=int)
args=parser.parse_args()
test=FirefoxDates(args.root,args.firefox_port,'native-color-fields.html','Native color fields') if args.firefox_port else ChromiumDates(args.root,'native-color-fields.html','Native color fields')
def panel():
    return next((w for w in test.command('windows') if w['visible'] and w['title']=='Colors'),None)
def click(x,y):
    assert test.command(f'pointer {round(x)} {round(y)}')['ok']
    test.button(1);test.button(0)
complete=False
try:
    for label in ['initial','reopened','keyboard']:
        if label=='keyboard':
            test.js('normal.focus()');test.key(57)
        else:
            rect=test.js('normal.getBoundingClientRect().toJSON()')
            click(test.origin[0]+rect['x']+rect['width']/2,test.origin[1]+rect['y']+rect['height']/2)
        test.until(panel,label+' original color panel')
        test.check(label+'-native-color-panel-has-physical-keyboard-focus',test.until(
            lambda:panel() and panel()['focused'],label+' physical color focus'))
        window=panel();click(window['x']+window['width']-11,window['y']+11)
        test.until(lambda:not panel(),label+' original color close')
        test.check(label+'-original-browser-picker-closes',test.until(
            lambda:not test.js('normal.matches(":open")'),label+' original picker close'))
    test.js('normal.focus()');test.key(57)
    test.until(panel,'owner removal panel')
    test.js('normal.remove()')
    test.check('removed-owner-closes-original-shared-panel',test.until(lambda:not panel(),'owner removal'))
    rect=test.js('second.getBoundingClientRect().toJSON()')
    click(test.origin[0]+rect['x']+rect['width']/2,test.origin[1]+rect['y']+rect['height']/2)
    test.check('new-owner-of-reused-panel-has-physical-keyboard-focus',test.until(
        lambda:panel() and panel()['focused'],'new owner physical focus'))
    test.js('second.type="text"')
    test.check('retyped-owner-closes-original-shared-panel',test.until(lambda:not panel(),'type change'))
    complete=True
finally:
    (test.root/'color-focus-checks.json').write_text(json.dumps(dict(complete=complete,checks=test.results),indent=2)+'\n')
    if args.firefox_port:test.close()
