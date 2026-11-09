"""Proleptic HTML dates through original native calendar actions and pixels."""
import json
from pathlib import Path
import sys
import time
from native_date_fields import ChromiumDates, FirefoxDates


def run(t):
    def actions():
        return sum(row.get('event') == 'native-form-action' and row.get('kind') == 17
                   for row in (json.loads(line) for line in (t.root/'helper.jsonl').read_text().splitlines()))
    for initial, expected in [('0001-01-01', '0001-02-01'), ('1500-01-01', '1500-02-01'),
                              ('1582-10-01', '1582-11-01'), ('1900-02-01', '1900-03-01'),
                              ('275760-08-01', '275760-09-01')]:
        t.focus('normal', initial);before = actions();t.key(103)
        t.check('original-native-date-era-'+initial,
                t.js('normal.value') == expected and actions() > before and t.js('window.events.every(e=>e.trusted)'))
    for initial in ('0001-01-01', '1582-10-01'):
        t.focus('normal', initial);t.js('normal.blur();window.events=[]')
        assert t.js('document.activeElement.id') != 'normal'
        assert t.command('pointer 1500 1100')['ok'];time.sleep(.15)
        model = t.js('({box:normal.getBoundingClientRect().toJSON(),value:normal.valueAsNumber})')
        field = dict(id='normal', kind=17, title='', state=0, width=model['box']['width'], height=model['box']['height'],
                     enabled=True, date_flags=148, date_elements=2, date_style=0, date_value=model['value']/1000)
        t.component_pixels('normal', field, model['box'], 'calendar-era-'+initial)


if __name__ == '__main__':
    t = FirefoxDates(sys.argv[1], int(sys.argv[2])) if len(sys.argv)>2 else ChromiumDates(sys.argv[1])
    try:
        run(t)
    finally:
        (t.root/'calendar-era-checks.json').write_text(json.dumps(t.results,indent=2)+'\n')
        if isinstance(t, FirefoxDates):
            t.close()
