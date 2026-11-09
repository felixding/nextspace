"""Native calendars on real browser windows, with compositor input/geometry."""
import json
from native_date_fields import ChromiumDates, FirefoxDates


class ChromiumCalendarPanels(ChromiumDates):
    def __init__(self, root):
        super().__init__(root, 'native-calendar-panels.html', 'Native calendar panels')
        self.browser_pid = json.loads((self.root/'launch.json').read_text())['pids'][-1]

    def browser_window(self):
        return next(w for w in self.command('windows')
                    if w['pid'] == self.browser_pid and w['visible']
                    and w['title'].startswith('Native calendar panels'))

    def panels(self):
        return [w for w in self.command('windows') if w['visible'] and w['title'] == 'Date and Time']

    def screen_origin(self):
        window = self.browser_window()
        return (window['x'] + (window['frame_left'] if window['server_decorated'] else 0),
                window['y'] + (window['frame_top'] if window['server_decorated'] else 0))

    def content_origin(self):
        x, y = self.screen_origin()
        window = self.browser_window()
        return x, y + window['surface_height'] - self.js('innerHeight')

    def origin_matches(self):
        return self.js('[screenX,screenY]') == list(self.screen_origin())

    def panel_matches(self, identifier='normal'):
        panels = self.panels()
        if len(panels) != 1:
            return False
        rect = self.js('document.getElementById('+json.dumps(identifier)+').getBoundingClientRect().toJSON()')
        x, y = self.content_origin()
        return (panels[0]['x'], panels[0]['y']) == (round(x + rect['x']), round(y + rect['bottom']))

    def choose(self, identifier='normal'):
        rect = self.js('document.getElementById('+json.dumps('open-'+identifier)+').getBoundingClientRect().toJSON()')
        x, y = self.content_origin()
        assert self.command(f"pointer {round(x+rect['x']+rect['width']/2)} {round(y+rect['y']+rect['height']/2)}")['ok']
        self.button(1)
        self.button(0)
        self.until(self.panels, 'native calendar opens')

    def picker_trials(self):
        def error(identifier):
            return self.js('(()=>{try{document.getElementById('+json.dumps(identifier)+
                ').showPicker();return "no-error"}catch(e){return e.name}})()')
        self.check('show-picker-retains-original-activation-gate', error('normal') == 'NotAllowedError')
        for identifier in ('readonly', 'disabled'):
            self.check('show-picker-retains-original-'+identifier+'-gate', error(identifier) == 'InvalidStateError')
        self.focus('normal', '2026-11-07')
        self.choose()
        self.check('show-picker-original-user-activation-succeeds',
                   self.js('window.openResults') == [dict(id='normal', result='opened')])
        self.check('show-picker-opens-native-calendar-window', self.panels()[0]['pid'] != self.browser_pid)
        self.key(106)
        self.until(lambda: self.js('normal.value') == '2026-11-08', 'native calendar chooses original model')
        self.check('native-calendar-choice-preserves-original-trusted-events', self.js('window.events') == [
            dict(id='normal', type=kind, value='2026-11-08', trusted=True) for kind in ('input', 'change')])
        rows = [json.loads(line) for line in (self.root/'helper.jsonl').read_text().splitlines()]
        self.check('browser-calendar-choice-has-native-action-witness', any(
            row.get('event') == 'native-form-action' and row.get('kind') == 17
            and row.get('value') == 1794096000 for row in rows))
        self.js('normal.focus();normal.blur()')
        self.check('browser-owner-blur-closes-native-calendar',
                   self.until(lambda: not self.panels(), 'native calendar owner blur'))

    def geometry_trials(self):
        self.check('browser-origin-matches-owned-compositor-surface',
                   self.until(self.origin_matches, 'actual Chromium surface origin'))
        self.focus('normal', '2026-11-07')
        self.choose()
        self.check('reopened-calendar-receives-physical-keyboard-focus', self.until(
            lambda: self.panels() and self.panels()[0]['focused'], 'reopened calendar keyboard focus'))
        self.check('native-calendar-anchors-below-original-field', self.until(self.panel_matches, 'initial calendar anchor'))
        before = self.js('({value:normal.value,events:window.events})')
        window = self.browser_window()
        assert self.command(f"move {window['id']} 100 70")['ok']
        self.check('browser-move-propagates-original-screen-coordinates',
                   self.until(lambda: self.origin_matches() and self.screen_origin()[0] == 101,
                              'moved Chromium origin'))
        self.check('visible-native-calendar-follows-browser-move', self.until(self.panel_matches, 'moved calendar anchor'))
        self.js('normal.style.transform="translate(13px,9px)"')
        self.check('visible-native-calendar-follows-original-layout', self.until(self.panel_matches, 'changed field anchor'))
        self.check('geometry-updates-preserve-original-value-and-events',
                   self.js('({value:normal.value,events:window.events})') == before)
        self.key(106)
        self.until(lambda: self.js('normal.value') == '2026-11-08', 'native edit after origin changes')
        self.check('moved-calendar-retains-native-editing-and-trusted-events', self.js('window.events') == [
            dict(id='normal', type=kind, value='2026-11-08', trusted=True) for kind in ('input', 'change')])
        self.js('normal.focus();normal.blur();normal.style.transform=""')
        self.until(lambda: not self.panels(), 'calendar closes on original blur')
        self.additional_window_trials()

    def additional_window_trials(self):
        original = self.browser_window()
        target = self.cdp('Target.createTarget', dict(url='about:blank', newWindow=True), target=False)['targetId']
        attached = self.cdp('Target.attachToTarget', dict(targetId=target, flatten=True), target=False)['sessionId']
        old_session = self.session
        try:
            self.session = attached
            self.js('document.title="Geometry replacement window"')
            def replacement():
                return next((w for w in self.command('windows') if w['pid'] == self.browser_pid
                             and w['visible'] and w['id'] != original['id']), None)
            new = self.until(replacement, 'second original browser window')
            self.command(f"move {new['id']} 60 45")
            self.check('additional-browser-window-has-independent-observation', self.until(
                lambda: self.js('[screenX,screenY]') == [replacement()['x']+replacement()['frame_left'],
                    replacement()['y']+replacement()['frame_top']], 'second window geometry'))
        finally:
            self.session = old_session
            self.cdp('Target.closeTarget', dict(targetId=target), target=False)
        self.until(lambda: not any(w['visible'] and w['id'] == new['id'] for w in self.command('windows')),
                   'second window destroyed')
        self.check('toplevel-destruction-preserves-surviving-browser-window', self.origin_matches())
        self.window_recovery_trials(original)

    def window_recovery_trials(self, original):
        assert self.command(f"move {original['id']} 0 0")['ok']
        self.until(lambda: self.screen_origin() == (1, 22) and self.origin_matches(), 'original origin restored')
        self.focus('normal', '2026-11-07')
        self.choose()
        self.check('native-calendar-reopens-after-other-toplevel-destruction',
                   self.until(self.panel_matches, 'calendar after toplevel teardown'))
        self.js('normal.focus();normal.blur()')
        self.until(lambda: not self.panels(), 'final calendar close')

    def variant_trials(self):
        for identifier, initial, code, expected in [
                ('clock', '12:30:45', 103, '13:30:45'),
                ('stamp', '2026-11-07T12:30:45', 106, '2026-11-08T12:30:45')]:
            self.focus(identifier, initial)
            self.choose(identifier)
            self.check(identifier+'-chooser-has-physical-keyboard-focus', self.until(
                lambda: self.panels() and self.panels()[0]['focused'], identifier+' chooser focus'))
            self.key(code)
            self.until(lambda: self.js('document.getElementById('+json.dumps(identifier)+').value') == expected,
                       identifier+' native chooser edit')
            self.check(identifier+'-chooser-retains-original-trusted-events', self.js('events') == [
                dict(id=identifier, type=kind, value=expected, trusted=True) for kind in ('input', 'change')])
            self.key(1)
            self.check(identifier+'-chooser-preserves-native-escape-completion', bool(self.panels()))
            self.key(28)
            self.check(identifier+'-chooser-native-confirm-dismisses', self.until(
                lambda: not self.panels(), identifier+' native confirmation'))
        self.focus('empty', '')
        self.choose('empty')
        self.check('empty-chooser-presentation-preserves-empty-model', self.js('empty.value') == '' and not self.js('events'))
        self.key(106)
        self.until(lambda: bool(self.js('empty.value')), 'empty chooser native edit')
        self.check('empty-chooser-initialization-has-trusted-events',
                   self.js('events.length') == 2 and self.js('events.every(e=>e.trusted)'))
        self.key(28)
        self.until(lambda: not self.panels(), 'empty chooser dismisses')
        self.focus('normal', '2026-11-07')
        self.choose()
        self.js('normal.readOnly=true')
        self.check('script-readonly-retires-open-chooser', self.until(
            lambda: not self.panels(), 'readonly chooser retirement'))
        self.key(106)
        self.check('retired-chooser-preserves-model-and-events', self.js('normal.value') == '2026-11-07' and not self.js('events'))
        self.js('normal.readOnly=false')
        self.focus('normal', '2026-11-07')
        self.choose()
        self.js('window.removedDate=normal;normal.remove()')
        self.check('removed-owner-retires-open-chooser', self.until(
            lambda: not self.panels(), 'removed chooser owner'))
        self.js('document.body.prepend(removedDate);window.removedDate=null')


class FirefoxCalendarPanels(FirefoxDates, ChromiumCalendarPanels):
    def __init__(self, root, port):
        FirefoxDates.__init__(self, root, port, 'native-calendar-panels.html', 'Native calendar panels')
        self.browser_pid = json.loads((self.root/'launch.json').read_text())['pids'][-1]

    def additional_window_trials(self):
        original = self.browser_window()
        handle = self.driver.command('WebDriver:GetWindowHandle')['value']
        created = self.driver.command('WebDriver:NewWindow', dict(type='window', focus=True))['handle']
        try:
            self.driver.command('WebDriver:SwitchToWindow', dict(handle=created))
            self.js('document.title="Geometry replacement window"')
            def replacement():
                return next((w for w in self.command('windows') if w['pid'] == self.browser_pid
                             and w['visible'] and w['id'] != original['id'] and w['level'] == 0), None)
            new = self.until(replacement, 'second original browser window')
            self.command(f"move {new['id']} 60 45")
            self.check('additional-browser-window-has-independent-observation', self.until(
                lambda: self.js('[screenX,screenY]') == [replacement()['x']+replacement()['frame_left'],
                    replacement()['y']+replacement()['frame_top']], 'second window geometry'))
        finally:
            self.driver.command('WebDriver:CloseWindow')
            self.driver.command('WebDriver:SwitchToWindow', dict(handle=handle))
        self.until(lambda: not any(w['visible'] and w['id'] == new['id'] for w in self.command('windows')),
                   'second window destroyed')
        self.check('toplevel-destruction-preserves-surviving-browser-window', self.origin_matches())
        self.window_recovery_trials(original)


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', required=True)
    p.add_argument('--firefox-port', type=int)
    a = p.parse_args()
    test = FirefoxCalendarPanels(a.root, a.firefox_port) if a.firefox_port else ChromiumCalendarPanels(a.root)
    status = dict(complete=False)
    try:
        test.picker_trials()
        test.geometry_trials()
        test.variant_trials()
        status['complete'] = True
    except BaseException as error:
        status['error'] = str(error)
        failure = dict(error=str(error))
        try:
            failure['windows'] = test.command('windows')
            failure['dom'] = test.js('({screenX,screenY,value:normal.value,active:document.activeElement.id,events})')
        except Exception as observation:
            failure['observation_error'] = str(observation)
        (test.root/'calendar-browser-failure.json').write_text(json.dumps(failure, indent=2)+'\n')
        raise
    finally:
        (test.root/'calendar-browser-checks.json').write_text(json.dumps(test.results, indent=2)+'\n')
        (test.root/'calendar-browser-status.json').write_text(json.dumps(status, indent=2)+'\n')
        if a.firefox_port:
            test.close()
