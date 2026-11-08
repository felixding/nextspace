"""Real compositor input and independent GNUstep date-picker comparisons."""
import json
import math
from pathlib import Path
import sys
import time
from native_number_fields import ChromiumNumbers


class ChromiumDates(ChromiumNumbers):
    def __init__(self, root):
        super().__init__(root, 'native-date-fields.html', 'Native date fields')

    def key(self, code):
        for state in (1, 0):
            assert self.command(f'key {code} {state}')['ok']
        time.sleep(.12)

    def focus(self, identifier, value):
        self.js('(()=>{let e=document.getElementById('+json.dumps(identifier)+');'
                'e.value='+json.dumps(value)+';e.focus();events=[]})()')
        time.sleep(.15)

    def click_part(self, identifier, stepper=False):
        rect = self.js('document.getElementById('+json.dumps(identifier)+').getBoundingClientRect().toJSON()')
        x = rect['right']-8 if stepper else rect['x']+18
        y = rect['y']+rect['height']/2-(5 if stepper else 0)
        assert self.command(f'pointer {round(self.origin[0]+x)} {round(self.origin[1]+y)}')['ok']
        self.button(1)
        self.button(0)
        time.sleep(.15)

    def trials(self):
        self.focus('normal', '2026-11-07')
        self.key(103)
        self.check('native-month-up-uses-original-browser-model-and-trusted-events',
                   self.js('normal.value') == '2026-12-07' and self.js('events') == [
                       dict(id='normal', type=kind, value='2026-12-07', trusted=True) for kind in ('input', 'change')])
        self.key(106)  # Original NSDatePicker selects the next field.
        self.key(103)
        self.check('native-field-selection-survives-browser-model-echo', self.js('normal.value') == '2026-12-08')
        self.focus('empty', '')
        self.check('focus-preserves-empty-date-without-events', self.js('empty.value') == '' and not self.js('events'))
        self.click_part('empty')
        self.check('pointer-focus-preserves-empty-date-without-events', self.js('empty.value') == '' and not self.js('events'))
        self.key(103)
        self.check('first-native-edit-initializes-empty-browser-date',
                   bool(self.js('empty.value')) and self.js('events.length') == 2 and self.js('events.every(e=>e.trusted)'))
        self.key(14)
        self.check('native-backspace-clears-browser-date', self.js('empty.value') == '' and self.js('events.length') == 4)
        self.key(14)
        self.check('repeated-empty-clear-is-silent', self.js('events.length') == 4)
        self.key(2)
        self.check('native-digit-initializes-empty-browser-date', bool(self.js('empty.value')))
        self.focus('normal', '1970-01-01')
        self.check('unix-epoch-remains-filled', self.js('normal.value') == '1970-01-01')
        self.key(14)
        self.check('epoch-can-be-cleared-to-distinct-empty-model', self.js('normal.value') == '')
        self.focus('normal', '2026-11-07')
        self.key(2);self.key(3)
        self.check('native-multidigit-editor-state-survives-application-echo', self.js('normal.value') == '2026-12-07')
        self.focus('normal', '2026-11-07')
        self.js('normal.addEventListener("keydown",event=>event.preventDefault(),{once:true})')
        self.key(103)
        self.check('page-cancelled-key-does-not-run-native-default', self.js('normal.value') == '2026-11-07' and not self.js('events'))
        for identifier in ('readonly', 'disabled', 'cancelled'):
            self.js('events=[]')
            before = self.js('document.getElementById('+json.dumps(identifier)+').value')
            self.click_part(identifier, True)
            self.check(identifier+'-prevents-native-mouse-edit',
                       self.js('document.getElementById('+json.dumps(identifier)+').value') == before and not self.js('events'))
        self.focus('normal', '2026-11-07')
        self.click_part('normal', True)
        self.check('native-stepper-mouse-edits-and-commits', self.js('normal.value') != '2026-11-07' and
                   self.js('events.length') == 2 and self.js('events.every(e=>e.trusted)'))
        self.focus('normal', '2026-11-07')
        self.js('normal.addEventListener("input",()=>normal.value="2025-02-03",{once:true})')
        self.key(103)
        self.check('script-value-change-during-native-action-survives', self.js('normal.value') == '2025-02-03')
        self.key(103)
        self.check('next-native-action-uses-script-updated-model', self.js('normal.value') == '2025-03-03')
        self.focus('normal', '2026-11-07')
        self.js('normal.addEventListener("input",()=>normal.readOnly=true,{once:true})')
        self.key(103)
        self.key(103)
        self.check('script-readonly-stops-further-native-actions', self.js('normal.value') == '2026-12-07' and self.js('events.length') == 2)
        self.js('normal.readOnly=false')
        self.focus('normal', '2026-11-07')
        self.js('normal.addEventListener("input",()=>normal.type="text",{once:true})')
        self.key(103)
        self.check('script-retyping-retires-native-date', self.js('normal.type') == 'text' and self.js('normal.value') == '2026-12-07')
        self.js('normal.type="date"')
        self.focus('normal', '2026-11-07')
        self.js('normal.addEventListener("input",()=>{window.removedDate=normal;normal.remove()},{once:true})')
        self.key(103)
        self.check('script-removal-during-native-action-is-safe', self.js('!document.getElementById("normal")') and self.js('removedDate.value') == '2026-12-07')
        self.js('document.body.prepend(removedDate);window.removedDate=null')
        self.focus('cancelled', '2026-11-07')
        self.key(15)
        self.check('native-tab-exits-last-date-control', self.js('document.activeElement.id') == 'after')
        assert self.command('key 42 1')['ok']
        try:
            self.key(15)
        finally:
            assert self.command('key 42 0')['ok']
        self.check('native-backtab-enters-previous-date-owner', self.js('document.activeElement.id') == 'cancelled')
        self.js('events=[]');self.key(103)
        self.check('focus-traversal-delivers-native-date-editing', self.js('cancelled.value') == '2026-12-07')
        self.focus('normal', '2026-11-07');self.key(15)
        self.check('native-tab-enters-next-date-owner', self.js('document.activeElement.id') == 'empty')
        self.focus('readonly', '2026-11-07');self.key(103)
        self.check('readonly-date-key-preserves-value', self.js('readonly.value') == '2026-11-07' and not self.js('events'))
        self.key(15)
        self.check('readonly-date-preserves-browser-focus-navigation', self.js('document.activeElement.id') == 'cancelled')

    def pixels(self):
        from PIL import Image, ImageChops
        for identifier in ('normal', 'empty', 'readonly', 'disabled'):
            self.js('document.activeElement.blur();events=[]')
            self.js('normal.value="2026-11-07";empty.value=""')
            assert self.command('pointer 1500 1100')['ok']
            time.sleep(.2)
            model = self.js('(()=>{let e=document.getElementById('+json.dumps(identifier)+');return '
                            '{box:e.getBoundingClientRect().toJSON(),value:e.valueAsNumber,enabled:!e.disabled&&!e.readOnly}})()')
            field = dict(id=identifier, kind=17, title='', state=0, width=model['box']['width'],
                         height=model['box']['height'], enabled=model['enabled'],
                         date_flags=20 | (8 if model['value'] is None else 0), date_elements=2,
                         date_style=0, date_value=(model['value'] or 0)/1000)
            reply = self.command('reference '+json.dumps(dict(name=identifier+'-date-reference', controls=[field], focus=False)))
            expected = Image.open(Path(reply['path'])/(identifier+'.png')).convert('RGBA')
            canvas = Image.new('RGBA', expected.size, 'white');canvas.alpha_composite(expected)
            capture = self.command('capture '+self.command('outputs')[0]['name']);event = capture['event']
            actual = Image.frombytes('RGB',(event['width'],event['height']),Path(capture['path']).read_bytes(),'raw','BGRX',event['stride'])
            x = math.floor(self.origin[0]+model['box']['x']+.5);y = math.floor(self.origin[1]+model['box']['y']+.5)
            cropped = actual.crop((x,y,x+expected.width,y+expected.height))
            cropped.save(self.root/(identifier+'-date-actual.png'));canvas.convert('RGB').save(self.root/(identifier+'-date-expected.png'))
            diff = ImageChops.difference(cropped, canvas.convert('RGB'));diff.save(self.root/(identifier+'-date-diff.png'))
            self.check(identifier+'-complete-independent-native-pixels', diff.getbbox() is None)


if __name__ == '__main__':
    trial = ChromiumDates(sys.argv[1])
    try:
        trial.trials()
        trial.pixels()
    finally:
        (trial.root/'date-checks.json').write_text(json.dumps(trial.results,indent=2)+'\n')
