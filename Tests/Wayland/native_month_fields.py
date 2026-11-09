"""Original Blink month semantics and shared NSDatePicker actions/pixels."""
import json
from pathlib import Path
import sys
import time
from native_date_fields import ChromiumDates


def run(t):
    def value(identifier='normal'):
        return t.js('document.getElementById('+json.dumps(identifier)+').value')
    def events():
        return t.js('window.events')
    t.check('original-month-type-remains-month', t.js('normal.type') == 'month')
    t.focus('normal', '2026-12');t.key(103)
    t.check('native-month-carries-through-year', value() == '2027-01')
    t.check('month-retains-original-numeric-and-date-dom-models',
            t.js('normal.valueAsNumber') == 684 and t.js('normal.valueAsDate.getTime()') == 1798761600000)
    t.check('native-month-retains-original-trusted-events',
            events() == [dict(id='normal', type=kind, value='2027-01', trusted=True) for kind in ('input', 'change')])
    t.key(106);t.key(103);t.key(103)
    t.check('month-native-year-selection-survives-canonical-model-echo', value() == '2029-01')
    t.focus('normal', '1969-12');t.key(108)
    t.check('native-month-supports-pre-epoch-model', value() == '1969-11')
    for initial, expected in [('0001-01', '0001-02'), ('1500-01', '1500-02'), ('1582-10', '1582-11'),
                              ('1900-02', '1900-03'), ('275760-08', '275760-09')]:
        t.focus('normal', initial)
        def native_actions():
            return sum(row.get('event') == 'native-form-action' and row.get('kind') == 17
                       for row in (json.loads(line) for line in (t.root/'helper.jsonl').read_text().splitlines()))
        before = native_actions();t.key(103)
        t.check('native-month-era-'+initial, value() == expected and native_actions() > before)
    t.focus('normal', '1970-01')
    t.check('filled-epoch-month-remains-distinct-from-empty', t.js('normal.valueAsDate.getTime()') == 0)
    t.key(14)
    t.check('native-month-can-clear-epoch-value', value() == '' and len(events()) == 2)
    t.key(14)
    t.check('repeated-empty-month-clear-is-silent', len(events()) == 2)
    t.focus('empty', '')
    t.check('empty-month-focus-does-not-create-a-value', value('empty') == '' and not events())
    t.click_part('empty')
    t.check('empty-month-pointer-focus-does-not-create-a-value', value('empty') == '' and not events())
    t.key(103)
    t.check('first-empty-month-edit-retains-original-month-model',
            bool(value('empty')) and t.js('empty.valueAsDate.getUTCDate()') == 1 and len(events()) == 2)
    t.key(14)
    t.check('native-empty-month-edit-can-be-cleared', value('empty') == '' and len(events()) == 4)
    t.key(2);t.key(3)
    t.check('native-digits-can-start-empty-month', bool(value('empty')) and t.js('empty.validity.valid'))
    t.focus('normal', '2026-05');t.key(2);t.key(3)
    t.check('native-month-digit-entry-survives-model-echo', value() == '2026-12')
    t.focus('normal', '2026-11');t.js('normal.min="2027-01"');t.key(103)
    t.check('native-month-retains-original-underflow-validation', value() == '2026-12' and t.js('normal.validity.rangeUnderflow'))
    t.js('normal.removeAttribute("min")');t.focus('normal', '2026-11');t.js('normal.max="2026-11"');t.key(103)
    t.check('native-month-retains-original-overflow-validation', value() == '2026-12' and t.js('normal.validity.rangeOverflow'))
    t.js('normal.removeAttribute("max")');t.focus('normal', '2026-11');t.js('normal.min="2026-11";normal.step="2"');t.key(103)
    t.check('native-month-retains-original-step-validation', value() == '2026-12' and t.js('normal.validity.stepMismatch'))
    t.js('normal.removeAttribute("step");normal.removeAttribute("min")')
    for identifier in ('readonly', 'disabled', 'cancelled'):
        t.js('window.events=[]');t.click_part(identifier, True)
        t.check(identifier+'-blocks-native-month-pointer-edit', value(identifier) == '2026-11' and not events())
    t.focus('normal', '2026-11')
    t.js('normal.addEventListener("keydown",event=>event.preventDefault(),{once:true})');t.key(103)
    t.check('cancelled-month-key-does-not-invoke-native-default', value() == '2026-11' and not events())
    t.focus('normal', '2026-11')
    t.js('normal.addEventListener("input",()=>normal.value="2025-02",{once:true})');t.key(103)
    t.check('script-replacement-survives-native-month-action', value() == '2025-02')
    t.key(103)
    t.check('next-month-action-uses-script-replaced-model', value() == '2025-03')
    t.focus('normal', '2026-11')
    t.js('normal.addEventListener("input",()=>normal.readOnly=true,{once:true})');t.key(103);t.key(103)
    t.check('script-readonly-stops-month-actions', value() == '2026-12' and len(events()) == 2)
    t.js('normal.readOnly=false')
    t.focus('normal', '2026-11');t.click_part('normal', True)
    t.check('native-month-pointer-step-uses-original-model', value() == '2026-12' and len(events()) == 2)
    t.focus('normal', '2026-11')
    t.js('normal.addEventListener("input",()=>{let end=performance.now()+700;while(performance.now()<end){};normal.value="2025-02"},{once:true})')
    t.point_part('normal', True);t.button(1)
    try:
        t.until(lambda: value() == '2025-02', 'held month script replacement');time.sleep(.2)
        t.check('held-native-month-preserves-script-model-replacement', value() == '2025-02')
    finally:
        t.button(0)
    t.key(103)
    t.check('next-month-edit-uses-replaced-held-model', value() == '2025-03')
    t.focus('normal', '2026-11')
    t.js('normal.addEventListener("input",()=>{normal.type="date";normal.value="2030-02-03"},{once:true})')
    t.point_part('normal', True);t.button(1)
    try:
        t.until(lambda: t.js('normal.type') == 'date', 'held month changed domain');time.sleep(.2)
        t.check('held-month-action-cannot-overwrite-date-domain', value() == '2030-02-03')
    finally:
        t.button(0)
    t.focus('normal', '2030-02-03');t.key(103)
    t.check('new-date-domain-reuses-same-native-picker', value() == '2030-03-03')
    t.js('normal.type="month"');t.focus('normal', '2026-11')
    t.js('normal.addEventListener("input",()=>{window.removedMonth=normal;normal.remove()},{once:true})');t.key(103)
    t.check('month-removal-during-native-callback-is-safe',
            t.js('!document.getElementById("normal")') and t.js('removedMonth.value') == '2026-12')
    t.js('document.body.prepend(removedMonth);window.removedMonth=null')
    t.focus('normal', '2026-11');t.js('normal.blur()');t.key(103)
    t.check('native-month-owner-blur-releases-keyboard', t.js('document.activeElement.id') != 'normal' and value() == '2026-11' and not events())
    t.focus('normal', '2026-11');t.key(15)
    t.check('native-month-tab-traverses-whole-owner', t.js('document.activeElement.id') == 'empty')
    rows = [json.loads(line) for line in (t.root/'helper.jsonl').read_text().splitlines()[t.native_action_offset:]]
    actions = [row for row in rows if row.get('event') == 'native-form-action' and row.get('kind') == 17]
    t.check('month-has-original-native-canonical-epoch-action-witness',
            len(actions) >= 3 and [row['value'] for row in actions[:3]] == [1798761600, 1830297600, 1861920000])
    t.check('month-clear-has-original-native-empty-action-witness', any(row['state'] == -1 and row['value'] == 0 for row in actions))
    pixels(t)


def pixels(t):
    for identifier, initial, enabled in [('normal', '2026-11', True), ('empty', '', True),
                                         ('readonly', '2026-11', False), ('disabled', '2026-11', False)]:
        t.focus(identifier, initial);t.js('document.activeElement.blur();window.events=[]')
        assert t.command('pointer 1500 1100')['ok'];time.sleep(.15)
        model = t.js('(()=>{let e=document.getElementById('+json.dumps(identifier)+');return {box:e.getBoundingClientRect().toJSON(),value:e.valueAsDate?.getTime()??null}})()')
        field = dict(id=identifier, kind=17, title='', state=0, width=model['box']['width'], height=model['box']['height'],
                     enabled=enabled, date_flags=84 if initial else 92, date_elements=1, date_style=0, date_value=(model['value'] or 0)/1000)
        t.component_pixels(identifier, field, model['box'], 'month')


if __name__ == '__main__':
    t = ChromiumDates(sys.argv[1], 'native-month-fields.html', 'Native month fields')
    try:
        run(t)
    finally:
        (t.root/'month-checks.json').write_text(json.dumps(t.results,indent=2)+'\n')
