"""Original Blink week models through the original GNUstep week fields."""
import json
from pathlib import Path
import sys
import time
from native_date_fields import ChromiumDates


def run(t):
    def focus(value, identifier='normal', week=True):
        t.focus(identifier, value);t.click_part(identifier)
        if week:
            t.key(106)  # Native fallback format selects year first, then week.
        t.js('window.events=[]')
    def value():
        return t.js('normal.value')
    def actions():
        return [row for row in (json.loads(line) for line in (t.root/'helper.jsonl').read_text().splitlines()[t.native_action_offset:])
                if row.get('event') == 'native-form-action' and row.get('kind') == 17]
    t.check('original-week-type-is-preserved', t.js('normal.type') == 'week')
    focus('2026-W53');t.key(103)
    t.check('native-week-carries-week-year', value() == '2027-W01')
    t.check('week-retains-original-dom-numeric-and-date-models',
            t.js('normal.valueAsNumber') == 1799020800000 and t.js('normal.valueAsDate.getTime()') == 1799020800000)
    t.check('week-edit-has-original-trusted-events', t.js('window.events') == [
        dict(id='normal', type=kind, value='2027-W01', trusted=True) for kind in ('input', 'change')])
    t.check('week-edit-has-actual-native-callback', actions() and actions()[0]['value'] == 1799020800)
    t.key(103)
    t.check('native-week-selection-survives-model-echo', value() == '2027-W02')
    focus('2026-W01', week=False);t.key(103)
    t.check('native-week-year-is-not-civil-year', value() == '2027-W01')
    for initial, expected in [('0001-W01','0001-W02'), ('1500-W01','1500-W02'), ('1582-W39','1582-W40'),
                              ('1970-W01','1970-W02'), ('2020-W53','2021-W01')]:
        focus(initial);before=len(actions());t.key(103)
        t.check('original-native-week-era-'+initial, value() == expected and len(actions()) > before)
    focus('1970-W01');t.key(108)
    t.check('native-week-retains-pre-epoch-model', value() == '1969-W52')
    focus('2026-W01');t.key(6);t.key(3)
    t.check('native-week-digit-entry', value() == '2026-W52')
    focus('2026-W52');t.js('normal.min="2027-W01"');t.key(103)
    t.check('week-retains-original-underflow-state', value() == '2026-W53' and t.js('normal.validity.rangeUnderflow'))
    t.js('normal.removeAttribute("min")');focus('2026-W52');t.js('normal.max="2026-W52"');t.key(103)
    t.check('week-retains-original-overflow-state', value() == '2026-W53' and t.js('normal.validity.rangeOverflow'))
    t.js('normal.removeAttribute("max")');focus('2026-W52');t.js('normal.min="2026-W52";normal.step="2"');t.key(103)
    t.check('week-retains-original-step-state', value() == '2026-W53' and t.js('normal.validity.stepMismatch'))
    t.js('normal.removeAttribute("min");normal.removeAttribute("step")')
    focus('', 'empty')
    t.check('empty-week-focus-is-silent', t.js('empty.value') == '' and not t.js('window.events'))
    t.key(103)
    t.check('first-empty-week-edit-uses-original-model', bool(t.js('empty.value')) and t.js('empty.valueAsDate.getUTCDay()') == 1)
    t.key(14)
    t.check('week-clear-has-native-empty-callback', t.js('empty.value') == '' and actions()[-1]['state'] == -1)
    for identifier in ('readonly','disabled','cancelled'):
        t.js('window.events=[]');t.click_part(identifier, True)
        t.check(identifier+'-blocks-week-pointer-edit', t.js(identifier+'.value') == '2026-W53' and not t.js('window.events'))
    focus('2026-W53');t.js('normal.addEventListener("keydown",e=>e.preventDefault(),{once:true})');t.key(103)
    t.check('page-cancelled-week-key-retains-native-default-boundary', value() == '2026-W53' and not t.js('window.events'))
    focus('2026-W53');t.js('normal.addEventListener("input",()=>normal.value="2025-W02",{once:true})');t.key(103)
    t.check('week-script-replacement-survives-native-action', value() == '2025-W02')
    t.click_part('normal');t.key(106);t.key(103)
    t.check('next-week-action-uses-script-model', value() == '2025-W03')
    focus('2026-W53');t.js('normal.addEventListener("input",()=>{normal.type="month";normal.value="2025-02"},{once:true})');t.key(103)
    t.check('week-action-cannot-overwrite-new-month-domain', t.js('normal.type') == 'month' and value() == '2025-02')
    t.focus('normal','2025-02');t.key(103)
    t.check('month-after-week-reuses-native-picker', value() == '2025-03')
    t.js('normal.type="week"')
    focus('2026-W53');t.js('normal.blur()');t.key(103)
    t.check('native-week-owner-blur-releases-keyboard', value() == '2026-W53' and t.js('document.activeElement.id') != 'normal')
    for identifier, initial, enabled in [('normal','2026-W53',True),('empty','',True),('readonly','2026-W53',False),('disabled','2026-W53',False)]:
        t.focus(identifier, initial);t.js('document.activeElement.blur();window.events=[]')
        assert t.command('pointer 1500 1100')['ok'];time.sleep(.15)
        model=t.js('(()=>{let e=document.getElementById('+json.dumps(identifier)+');return {box:e.getBoundingClientRect().toJSON(),value:e.valueAsNumber}})()')
        field=dict(id=identifier,kind=17,title='',state=0,width=model['box']['width'],height=model['box']['height'],
                   enabled=enabled,date_flags=404 if initial else 412,date_elements=6,date_style=0,date_value=(model['value'] or 0)/1000)
        t.component_pixels(identifier,field,model['box'],'week')


if __name__ == '__main__':
    t=ChromiumDates(sys.argv[1],'native-week-fields.html','Native week fields')
    try:
        run(t)
    finally:
        (t.root/'week-checks.json').write_text(json.dumps(t.results,indent=2)+'\n')
