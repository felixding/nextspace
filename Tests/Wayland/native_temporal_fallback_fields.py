"""Native text controls for temporal types unsupported by pinned Firefox defaults."""
import json
from pathlib import Path
import sys
import time
from native_date_fields import FirefoxDates


def run(t):
    for identifier, initial in [('month', '2026-11'), ('week', '2026-W45')]:
        t.focus(identifier, initial)
        t.check(identifier+'-keeps-original-text-fallback-model',
                t.js(identifier+'.type') == 'text' and t.js(identifier+'.getAttribute("type")') == identifier
                and t.js('Number.isNaN('+identifier+'.valueAsNumber)') and t.js(identifier+'.valueAsDate') is None)
        for code in (30, 37):
            assert t.command('key 29 1')['ok']
            try:
                t.key(code)
            finally:
                assert t.command('key 29 0')['ok']
        t.check(identifier+'-native-emacs-beginning-and-kill-line', t.js(identifier+'.value') == '')
        t.key(2)
        t.check(identifier+'-native-text-edit-keeps-original-unsupported-type-semantics',
                t.js(identifier+'.value') == '1' and t.js(identifier+'.validity.valid'))
        t.check(identifier+'-native-edit-retains-original-trusted-events',
                t.js('window.events.some(e=>e.type==="input")&&window.events.every(e=>e.trusted)'))
    t.focus('readonly', '2026-11');t.key(2)
    t.check('readonly-temporal-fallback-rejects-edit', t.js('readonly.value') == '2026-11' and not t.js('window.events'))
    t.js('window.events=[]');t.click_part('disabled');t.key(2)
    t.check('disabled-temporal-fallback-rejects-edit', t.js('disabled.value') == '2026-W45' and not t.js('window.events'))
    t.focus('month', '2026-11');t.js('month.blur()');t.key(2)
    t.check('temporal-text-fallback-owner-blurs-normally', t.js('document.activeElement.id') != 'month' and t.js('month.value') == '2026-11')
    rows = [json.loads(line) for line in (t.root/'helper.jsonl').read_text().splitlines()[t.native_action_offset:]]
    handled = {row['control'] for row in rows if row.get('event') == 'native-form-key'
               and row.get('kind') == 7 and row.get('type') == 0 and row.get('result') == 1}
    commands = {row['control'] for row in rows if row.get('event') == 'native-command' and row.get('kind') == 7}
    t.check('temporal-text-fallback-has-original-native-key-and-command-witnesses',
            len(handled) >= 2 and commands.issuperset(handled))
    for identifier, initial, enabled, editable in [('month', '2026-11', True, True), ('week', '2026-W45', True, True),
                                                   ('readonly', '2026-11', True, False), ('disabled', '2026-W45', False, False)]:
        t.focus(identifier, initial);t.js('document.activeElement.blur();window.events=[]')
        assert t.command('pointer 1500 1100')['ok'];time.sleep(.15)
        box = t.js('document.getElementById('+json.dumps(identifier)+').getBoundingClientRect().toJSON()')
        field = dict(id=identifier, kind=7, title='', state=0, width=box['width'], height=box['height'],
                     enabled=enabled, editable=editable, text=initial)
        t.component_pixels(identifier, field, box, 'temporal-fallback')


if __name__ == '__main__':
    t = FirefoxDates(sys.argv[1], int(sys.argv[2]), 'native-temporal-fallback-fields.html', 'Native temporal fallback fields')
    try:
        run(t)
    finally:
        (t.root/'fallback-checks.json').write_text(json.dumps(t.results,indent=2)+'\n');t.close()
