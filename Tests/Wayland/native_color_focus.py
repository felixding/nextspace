"""Physical keyboard focus on original shared color-panel reuse."""
import argparse
import json
from native_density_controls import DensityFixture

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root',required=True)
parser.add_argument('--firefox-port',type=int)
parser.add_argument('--withhold-bitmaps',action='store_true',help='Keep native picker state live while inline-well readback is temporarily unavailable')
parser.add_argument('--scale',type=float,default=1)
args=parser.parse_args()
test=DensityFixture(args.root,'firefox' if args.firefox_port else 'chromium',args.firefox_port or 9293,
                    expected_scale=args.scale,page='native-color-fields.html',title='Native color fields',
                    report='color-focus-progress.json')
test.origin=tuple(v/test.output_scale for v in test.origin_pixels)
def panel():
    return next((w for w in test.command('windows') if w['visible'] and w['title']=='Colors'),None)
def click(x,y):
    assert test.command(f'pointer {round(x)} {round(y)}')['ok']
    test.button(1);test.button(0)
complete=False
marker=test.root/'withhold-color-bitmaps'
try:
    if args.withhold_bitmaps:marker.touch(exist_ok=False)
    # A preceding address-editor trial can leave the original autocomplete
    # popup in front of page content. Dismiss it through its normal Escape.
    test.key(1)
    for label in ['initial','reopened','keyboard']:
        # Closing the native panel restores the browser through an asynchronous
        # Wayland focus event. Wait for the original document to receive it
        # before sending the next independent physical activation.
        if label != 'initial':
            test.until(lambda:test.js('document.hasFocus()'),label+' browser focus restored')
        if label=='keyboard':
            test.js('normal.focus()');test.key(57)
        else:
            rect=test.js('normal.getBoundingClientRect().toJSON()')
            click(test.origin[0]+rect['x']+rect['width']/2,test.origin[1]+rect['y']+rect['height']/2)
        test.until(panel,label+' original color panel')
        test.check(label+'-native-color-panel-has-physical-keyboard-focus',test.until(
            lambda:panel() and panel()['focused'],label+' physical color focus'))
        # Observe an actual presented frame before the next panel interaction;
        # compositor focus can arrive before the native client's activation.
        test.command('capture '+test.command('outputs')[0]['name'])
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
    if args.withhold_bitmaps:marker.unlink(missing_ok=True)
    (test.root/('color-focus-withheld-checks.json' if args.withhold_bitmaps else 'color-focus-checks.json')).write_text(json.dumps(dict(complete=complete,checks=test.results),indent=2)+'\n')
    if args.firefox_port:test.driver.close()
