"""Shared real-input time/datetime models, native callbacks and full images."""
import json
import math
from pathlib import Path
import sys
import time
from native_date_fields import ChromiumDates, FirefoxDates


def run(t):
    def value(identifier):
        return t.js('document.getElementById('+json.dumps(identifier)+').value')
    def events():
        return t.js('window.events')
    t.focus('clock', '23:59:59.875');t.key(103)
    t.check('native-time-hour-carries-through-midnight-with-milliseconds', value('clock') == '00:59:59.875')
    t.check('time-native-action-retains-original-trusted-browser-events',
            events() == [dict(id='clock', type=kind, value='00:59:59.875', trusted=True) for kind in ('input', 'change')])
    t.key(106);t.key(103)
    t.check('native-time-minute-selection-survives-canonical-model-echo', value('clock') == '01:00:59.875')
    t.key(106);t.key(103)
    t.check('native-time-second-carries-without-losing-milliseconds', value('clock') == '01:01:00.875')
    t.focus('clock', '00:00:00.125');t.key(108)
    t.check('native-time-hour-carries-before-epoch-with-canonical-clock-value', value('clock') == '23:00:00.125')
    t.focus('clock', '12:34:56.123');t.key(103);t.key(106);t.key(103);t.key(103)
    t.check('nonbinary-millisecond-model-echo-keeps-native-minute-selection', value('clock') == '13:36:56.123')
    t.focus('clock', '00:00:00.123');t.key(108)
    t.check('nonbinary-milliseconds-survive-native-pre-epoch-carry', value('clock') == '23:00:00.123')
    t.focus('emptyClock', '')
    t.check('empty-time-focus-does-not-create-a-value', value('emptyClock') == '' and not events())
    t.click_part('emptyClock')
    t.check('empty-time-pointer-focus-does-not-create-a-value', value('emptyClock') == '' and not events())
    t.key(103)
    t.check('first-empty-time-edit-has-no-hidden-date-in-browser-model',
            bool(value('emptyClock')) and t.js('emptyClock.valueAsNumber>=0&&emptyClock.valueAsNumber<86400000')
            and len(events()) == 2 and all(row['trusted'] for row in events()))
    t.key(14)
    t.check('native-time-clear-preserves-empty-model', value('emptyClock') == '' and len(events()) == 4)
    t.key(14)
    t.check('repeated-native-time-clear-is-silent', len(events()) == 4)
    t.key(2);t.key(3)
    t.check('native-digit-entry-can-start-an-empty-time', bool(value('emptyClock')) and t.js('emptyClock.validity.valid'))
    t.focus('stamp', '2026-11-07T23:59:59.875');t.key(103)
    t.check('native-datetime-month-edit-keeps-clock-and-milliseconds', value('stamp') == '2026-12-07T23:59:59.875')
    t.key(106);t.key(103)
    t.check('native-datetime-day-selection-survives-model-echo', value('stamp') == '2026-12-08T23:59:59.875')
    t.focus('emptyStamp', '')
    t.check('empty-datetime-focus-is-silent', value('emptyStamp') == '' and not events())
    t.key(103)
    t.check('native-empty-datetime-edit-creates-original-browser-events', bool(value('emptyStamp')) and len(events()) == 2 and all(row['trusted'] for row in events()))
    t.key(14)
    t.check('native-datetime-can-be-cleared', value('emptyStamp') == '' and len(events()) == 4)
    t.focus('clock', '00:00')
    t.check('filled-native-midnight-remains-distinct-from-empty', t.js('clock.valueAsNumber') == 0)
    t.key(14)
    t.check('filled-midnight-can-be-cleared-through-native-action', value('clock') == '' and len(events()) == 2)
    for identifier, initial in [('readonlyClock', '12:34:56.125'), ('disabledStamp', '2026-11-07T12:34:56.125')]:
        t.js('window.events=[]');t.click_part(identifier, True)
        t.check(identifier+'-blocks-native-pointer-edit', value(identifier) == initial and not events())
    t.focus('clock', '12:34:56.125')
    t.js('clock.addEventListener("keydown",event=>event.preventDefault(),{once:true})');t.key(103)
    t.check('page-cancelled-time-key-does-not-invoke-native-edit', value('clock') == '12:34:56.125' and not events())
    t.focus('clock', '12:34:56.125')
    t.js('clock.addEventListener("input",()=>clock.value="03:04:05.625",{once:true})');t.key(103)
    t.check('page-script-time-value-change-survives-native-action', value('clock') == '03:04:05.625')
    t.key(103)
    t.check('next-native-time-edit-uses-script-updated-model', value('clock') == '04:04:05.625')
    t.focus('clock', '12:34:56.125')
    t.js('clock.addEventListener("input",()=>clock.readOnly=true,{once:true})');t.key(103);t.key(103)
    t.check('script-readonly-stops-native-time-edits', value('clock') == '13:34:56.125' and len(events()) == 2)
    t.js('clock.readOnly=false')
    t.focus('clock', '12:34:56.125')
    t.js('clock.addEventListener("input",()=>{clock.type="datetime-local";clock.value="2030-02-03T04:05:06.251"},{once:true})')
    t.point_part('clock', True);t.button(1)
    try:
        t.until(lambda: t.js('clock.type') == 'datetime-local', 'held time changed temporal domain')
        time.sleep(.2)
        t.check('held-time-action-cannot-overwrite-new-datetime-domain', value('clock') == '2030-02-03T04:05:06.251')
    finally:
        t.button(0)
    # Changing the input type can rebuild the engine frame and blur its owner.
    # Re-enter that original owner before testing the newly bound native model.
    t.focus('clock', '2030-02-03T04:05:06.251');t.key(103)
    t.check('refocused-native-edit-uses-new-datetime-domain', value('clock') == '2030-03-03T04:05:06.251')
    t.js('clock.type="time"')
    t.focus('clock', '12:34:56.125')
    # Accumulate actual native repeat callbacks while the original engine is
    # busy in a page listener, then replace its model before receipts drain.
    t.js('clock.addEventListener("input",()=>{let end=performance.now()+700;while(performance.now()<end){};clock.value="03:04:05.625"},{once:true})')
    t.point_part('clock', True);t.button(1)
    try:
        t.until(lambda: value('clock') == '03:04:05.625', 'held time script model replacement')
        time.sleep(.2)
        t.check('held-native-time-action-preserves-script-model-replacement', value('clock') == '03:04:05.625')
    finally:
        t.button(0)
    t.key(103)
    t.check('next-native-time-edit-uses-replaced-held-model', value('clock') == '04:04:05.625')
    t.focus('clock', '12:34:56.125')
    t.js('window.nativeBlurEvents=[];clock.addEventListener("blur",event=>window.nativeBlurEvents.push(event.isTrusted),{once:true});clock.blur()')
    time.sleep(.15)
    t.check('native-temporal-blur-releases-original-owner-once',
            t.js('document.activeElement.id') != 'clock' and t.js('window.nativeBlurEvents') == [True])
    t.key(103)
    t.check('blurred-native-time-cannot-consume-next-key', value('clock') == '12:34:56.125' and not events())
    t.focus('clock', '12:34:56.125');t.key(15)
    t.check('native-time-tab-enters-next-whole-control', t.js('document.activeElement.id') == 'emptyClock')
    t.focus('emptyStamp', '2026-11-07T12:34:56.125');t.key(15)
    t.check('native-datetime-tab-reaches-original-readonly-control', t.js('document.activeElement.id') == 'readonlyClock')
    t.key(15)
    t.check('readonly-time-tab-skips-original-disabled-control', t.js('document.activeElement.id') == 'after')
    rows = [json.loads(line) for line in (t.root/'helper.jsonl').read_text().splitlines()[t.native_action_offset:]]
    actions = [row for row in rows if row.get('event') == 'native-form-action' and row.get('kind') == 17]
    t.check('time-edits-have-ordered-original-native-action-witnesses',
            len(actions) >= 3 and [row['value'] for row in actions[:3]] == [3599.875, 3659.875, 3660.875])
    t.check('time-clear-has-real-native-empty-action-witness', any(row['state'] == -1 and row['value'] == 0 for row in actions))
    pixels(t)


def pixels(t):
    from PIL import Image, ImageChops
    for identifier, elements, flags, initial in [
        ('clock', 4, 52, '23:59:59.875'), ('emptyClock', 4, 60, ''),
        ('stamp', 5, 20, '2026-11-07T23:59:59.875'), ('emptyStamp', 5, 28, '')]:
        t.focus(identifier, initial);t.js('document.activeElement.blur();window.events=[]')
        assert t.js('document.activeElement.id') != identifier, identifier+'-original-owner-blurs'
        assert t.command('pointer 1500 1100')['ok'];time.sleep(.15)
        model = t.js('(()=>{let e=document.getElementById('+json.dumps(identifier)+');return {box:e.getBoundingClientRect().toJSON(),value:e.valueAsNumber}})()')
        field = dict(id=identifier, kind=17, title='', state=0, width=model['box']['width'], height=model['box']['height'],
                     enabled=True, date_flags=flags, date_elements=elements, date_style=0, date_value=(model['value'] or 0)/1000)
        reference = t.command('reference '+json.dumps(dict(name=identifier+'-temporal-reference', controls=[field], focus=False)))
        expected = Image.open(Path(reference['path'])/(identifier+'.png')).convert('RGBA')
        canvas = Image.new('RGBA', expected.size, 'white');canvas.alpha_composite(expected)
        capture = t.command('capture '+t.command('outputs')[0]['name']);event = capture['event']
        actual = Image.frombytes('RGB',(event['width'],event['height']),Path(capture['path']).read_bytes(),'raw','BGRX',event['stride'])
        x = math.floor(t.origin[0]+model['box']['x']+.5);y = math.floor(t.origin[1]+model['box']['y']+.5)
        cropped = actual.crop((x,y,x+expected.width,y+expected.height))
        cropped.save(t.root/(identifier+'-temporal-actual.png'));canvas.convert('RGB').save(t.root/(identifier+'-temporal-expected.png'))
        diff = ImageChops.difference(cropped, canvas.convert('RGB'));diff.save(t.root/(identifier+'-temporal-diff.png'))
        t.check(identifier+'-complete-independent-native-temporal-pixels', diff.getbbox() is None)


if __name__ == '__main__':
    t = FirefoxDates(sys.argv[1], int(sys.argv[2]), 'native-temporal-fields.html', 'Native temporal fields') if len(sys.argv) > 2 else ChromiumDates(sys.argv[1], 'native-temporal-fields.html', 'Native temporal fields')
    try:
        run(t)
    finally:
        (t.root/'temporal-checks.json').write_text(json.dumps(t.results,indent=2)+'\n')
        if isinstance(t, FirefoxDates):
            t.close()
