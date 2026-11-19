"""Real-seat application shortcuts, including commands absent from menus."""
import argparse
import json
from pathlib import Path
import time

from native_context_menus import ContextFixture


class ApplicationShortcuts(ContextFixture):
    def chrome(self, script):
        self.driver.command('Marionette:SetContext', dict(value='chrome'))
        try:
            return self.chrome_js(script)
        finally:
            self.driver.command('Marionette:SetContext', dict(value='content'))

    def address(self):
        if self.family == 'firefox':
            return self.chrome('const e=gURLBar.inputField;return {focused:gURLBar.focused,'
                               'value:e.value,start:e.selectionStart,end:e.selectionEnd}')
        value = self.address_state()
        return dict(value, focused=value.get('focused') == '1') if value else None

    def selected_address(self):
        value = self.address()
        return value and value['focused'] and value['value'] and value['start'] == 0 and value['end'] == len(value['value'])

    def original_registry(self):
        letter = self.chrome('''window.__nativeRegistryEvents=[];
          const used=new Set([...document.querySelectorAll('key')].filter(e=>{
            const mods=(e.getAttribute('modifiers')||'').split(/[, ]+/);
            return mods.includes('shift')&&mods.some(m=>['accel','control','meta'].includes(m));
          }).map(e=>(e.getAttribute('key')||'').toUpperCase()));
          const letter=['L','Q','X','Y','E','M'].find(key=>!used.has(key));
          if(!letter)throw Error('No unused original character chord for registry fixture');
          let command=document.createXULElement('command');command.id='native-registry-fixture-command';
          command.addEventListener('command',e=>window.__nativeRegistryEvents.push({trusted:e.isTrusted,alt:e.altKey}));
          document.documentElement.append(command);
          let set=document.createXULElement('keyset');set.id='native-registry-fixture-set';
          let key=document.createXULElement('key');key.id='native-registry-fixture-key';
          key.setAttribute('key',letter);key.setAttribute('modifiers','accel,shift');
          key.setAttribute('command',command.id);set.append(key);document.documentElement.append(set);return letter''')
        def count():
            return self.chrome('return window.__nativeRegistryEvents.length')
        def invoke():
            self.focus_field('text')
            assert self.command('key 42 1')['ok']
            try:
                self.chord(dict(L=38, Q=16, X=45, Y=21, E=18, M=50)[letter], 56)
            finally:
                assert self.command('key 42 0')['ok']
        invoke()
        self.until(lambda: count() == 1, 'original non-menu command executes once')
        self.check('original-non-menu-command-retains-trusted-event',
                   self.chrome('return window.__nativeRegistryEvents[0].trusted'))
        for target in ('command', 'key', 'set'):
            self.chrome('document.getElementById("native-registry-fixture-'+target+'").setAttribute("disabled","true");return true')
            invoke()
            time.sleep(.15)
            self.check('original-'+target+'-disabled-state-prevents-command', count() == 1)
            self.chrome('document.getElementById("native-registry-fixture-'+target+'").removeAttribute("disabled");return true')
        invoke()
        self.until(lambda: count() == 2, 'reenabled original command')
        self.check('original-command-reenable-reused', True)
        self.chrome('document.getElementById("native-registry-fixture-set").remove();return true')
        invoke()
        time.sleep(.15)
        self.check('removed-keyset-cannot-replay-command', count() == 2)
        self.chrome('document.getElementById("native-registry-fixture-command").remove();return true')

    def run(self, missing=False):
        original_menu = self.until(lambda: next((w['id'] for w in self.command('windows')
                                   if w['visible'] and w['level'] == 20), None), 'original detached application menu')
        self.focus_field('text')
        self.key(106)
        self.chord(38, 56)
        if missing:
            time.sleep(.3)
            state = self.address()
            (self.root/'missing-address-shortcut-state.json').write_text(json.dumps(state, indent=2)+'\n')
            self.capture('missing-native-address-shortcut')
            self.check('reported-native-address-shortcut-failure-reproduced', not state['focused'])
            return
        self.until(self.selected_address, 'first native address shortcut selects full URL')
        self.capture('native-address-shortcut-first')
        self.check('first-native-address-shortcut-focuses-and-selects', True)
        self.check('key-registry-preserves-original-detached-menu',
                   any(w['id'] == original_menu and w['visible'] for w in self.command('windows')))
        for source in ('text', 'password', 'notes'):
            self.focus_field(source)
            self.chord(38, 56)
            self.until(self.selected_address, 'native address shortcut from '+source)
            self.check('native-address-shortcut-from-'+source, True)
        self.key(106)
        self.until(lambda: self.address()['start'] == self.address()['end'], 'address caret collapsed')
        self.chord(38, 56)
        self.until(self.selected_address, 'repeated native address shortcut')
        self.check('repeated-native-address-shortcut-reselects', True)
        self.focus_field('text')
        self.js('window.__locationKeys=[];window.__cancelledLocation=false;window.__cancelLocation=e=>{window.__locationKeys.push({key:e.key,code:e.code,alt:e.altKey,trusted:e.isTrusted});if(e.altKey&&e.code==="KeyL"){e.preventDefault();window.__cancelledLocation=true}};document.addEventListener("keydown",window.__cancelLocation,true);true')
        self.chord(38, 56)
        self.until(lambda: self.js('window.__cancelledLocation'), 'original page saw the native shortcut')
        time.sleep(.15)
        self.check('original-page-cancellation-prevents-address-command', not self.address()['focused'])
        self.js('document.removeEventListener("keydown",window.__cancelLocation,true);true')
        self.chord(38, 56)
        self.until(self.selected_address, 'address shortcut after cancelled event')
        self.check('native-address-shortcut-recovers-after-cancellation', True)
        if self.family == 'firefox':
            self.original_registry()
        self.check('original-detached-menu-survives-command-registry-lifecycle',
                   any(w['id'] == original_menu and w['visible'] for w in self.command('windows')))
        self.capture('native-application-shortcuts-final')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--family', choices=['firefox', 'chromium'], required=True)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--scale', type=float, default=2)
    parser.add_argument('--expect-missing', action='store_true')
    args = parser.parse_args()
    fixture = ApplicationShortcuts(args.root, args.family, args.port, args.scale,
                                   report='application-shortcut-checks.json')
    try:
        fixture.run(args.expect_missing)
        print(json.dumps(dict(complete=True, checks=len(fixture.results))), flush=True)
    except BaseException:
        fixture.capture('application-shortcut-failure')
        (fixture.root/'application-shortcut-failure-state.json').write_text(json.dumps(dict(
            address=fixture.address(),content=fixture.js('({active:document.activeElement.id,focused:document.hasFocus(),keys:window.__locationKeys,cancelled:window.__cancelledLocation})')),
            indent=2)+'\n')
        if args.family == 'firefox':
            (fixture.root/'original-registry-failure-state.json').write_text(json.dumps(fixture.chrome(
                'return {events:window.__nativeRegistryEvents,keys:[...document.querySelectorAll("key[id^=native-registry]")].map(e=>({key:e.getAttribute("key"),modifiers:e.getAttribute("modifiers"),namespace:e.namespaceURI,command:e.getAttribute("command"),disabled:e.getAttribute("disabled")}))}'),indent=2)+'\n')
        raise
    finally:
        if args.family == 'firefox':
            fixture.driver.close()
