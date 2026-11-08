"""Real browser number semantics and native-editor trials on an owned fixture."""
import json
from pathlib import Path
import socket
import time


class ChromiumNumbers:
    def __init__(self, root):
        self.root = Path(root)
        self.results = []
        target = next(item for item in self.cdp('Target.getTargets', target=False)['targetInfos']
                      if item['type'] == 'page')
        self.session = self.cdp('Target.attachToTarget', dict(targetId=target['targetId'], flatten=True), False)['sessionId']
        self.cdp('Page.navigate', dict(url='file:///workspace/Tests/Wayland/native-number-fields.html'))
        self.until(lambda: self.js('document.title') == 'Native number fields', 'page load')
        pid = json.loads((self.root/'launch.json').read_text())['pids'][-1]
        window = next(item for item in self.command('windows') if item['pid'] == pid and item['level'] == 0)
        assert self.command('focus '+str(window['id']))['ok']
        inside = self.js('({height:innerHeight,scale:devicePixelRatio})')
        assert inside['scale'] == 1
        self.origin = (window['x']+(window['frame_left'] if window['server_decorated'] else 0),
                       window['y']+(window['frame_top'] if window['server_decorated'] else 0)
                       +window['surface_height']-inside['height'])

    def command(self, value):
        with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as connection:
            connection.settimeout(20)
            connection.connect(str(self.root/'control.sock'))
            connection.send(json.dumps(dict(command=value)).encode())
            return json.loads(connection.recv(1048576))

    def cdp(self, method, params=None, target=True):
        request = dict(method=method, params=params or {})
        if target:
            request['sessionId'] = self.session
        response = self.command('cdp '+json.dumps(request))
        assert 'error' not in response, response
        return response['result']

    def js(self, script):
        response = self.cdp('Runtime.evaluate', dict(expression=script, returnByValue=True))
        assert 'exceptionDetails' not in response, response
        return response['result'].get('value')

    @staticmethod
    def until(predicate, label):
        deadline = time.monotonic()+10
        while time.monotonic() < deadline:
            result = predicate()
            if result:
                return result
            time.sleep(.02)
        raise AssertionError(label)

    def check(self, name, value):
        assert value, name
        row = dict(case=name, passed=True)
        self.results.append(row)
        print(json.dumps(row), flush=True)

    def snapshot(self, identifier):
        return self.js('(()=>{let el=document.getElementById('+json.dumps(identifier)+');return '
            '{value:el.value,bad:el.validity.badInput,step:el.validity.stepMismatch,'
            'under:el.validity.rangeUnderflow,over:el.validity.rangeOverflow,events:window.events}})()')

    def spin_box(self, identifier):
        document = self.cdp('DOM.getDocument', dict(depth=-1, pierce=True))['root']
        def nodes(node):
            yield node
            for name in ('children', 'shadowRoots'):
                for child in node.get(name, []):
                    yield from nodes(child)
        def attributes(node):
            values = node.get('attributes', [])
            return dict(zip(values[::2], values[1::2]))
        input_node = next(node for node in nodes(document) if attributes(node).get('id') == identifier)
        spin = next(node for node in nodes(input_node) if attributes(node).get('id') == 'spin')
        quad = self.cdp('DOM.getBoxModel', dict(backendNodeId=spin['backendNodeId']))['model']['border']
        return min(quad[::2]), min(quad[1::2]), max(quad[::2]), max(quad[1::2])

    def pointer(self, identifier, direction):
        left, top, right, bottom = self.spin_box(identifier)
        assert self.command(f'pointer {round(self.origin[0]+(left+right)/2)} '
                            f'{round(self.origin[1]+top+(bottom-top)*(0.25 if direction>0 else 0.75))}')['ok']
        # Hover can expose the engine's original anonymous spin box.
        time.sleep(.05)

    def button(self, state):
        assert self.command(f'button 272 {state}')['ok']

    def click(self, identifier, direction):
        self.pointer(identifier, direction)
        self.button(1)
        self.button(0)
        time.sleep(.15)
        return self.snapshot(identifier)

    def reset(self, identifier, value, minimum=None, maximum=None, step=None):
        self.js('(()=>{let el=document.getElementById('+json.dumps(identifier)+');'
            'for(let [name,value] of Object.entries('+json.dumps(dict(min=minimum, max=maximum, step=step))+'))'
            '{if(value===null)el.removeAttribute(name);else el.setAttribute(name,value)}'
            'el.value='+json.dumps(value)+';window.events=[]})()')
        time.sleep(.05)

    def semantic_trials(self):
        cases = [('up','normal','2','0','10','1',1), ('down','normal','2','0','10','1',-1),
                 ('maximum','normal','10','0','10','1',1), ('minimum','normal','0','0','10','1',-1),
                 ('decimal-up','decimal','0.25','0.2','2','0.1',1),
                 ('decimal-down','decimal','0.25','0.2','2','0.1',-1),
                 ('empty-up','empty','','5','15','1',1), ('empty-down','empty','','5','15','1',-1),
                 ('any-up','normal','2',None,None,'any',1), ('any-down','normal','2',None,None,'any',-1),
                 ('readonly','readonly','2',None,None,'1',1), ('disabled','disabled','2',None,None,'1',1),
                 ('cancelled','cancelled','2',None,None,'1',1)]
        snapshots = {}
        for name, identifier, value, minimum, maximum, step, direction in cases:
            self.reset(identifier, value, minimum, maximum, step)
            snapshots[name] = self.click(identifier, direction)
        return snapshots

    def native_editor_trials(self):
        self.reset('normal', '', None, None, '1')
        rect = self.js('normal.getBoundingClientRect().toJSON()')
        assert self.command(f"pointer {round(self.origin[0]+rect['x']+15)} {round(self.origin[1]+rect['y']+10)}")['ok']
        self.button(1)
        self.button(0)
        def key(code):
            for state in (1, 0):
                assert self.command(f'key {code} {state}')['ok']
        key(12)  # An incomplete negative number remains a real engine edit.
        self.until(lambda: self.js('normal.validity.badInput'), 'incomplete numeric edit')
        self.check('native-number-editor-preserves-bad-input-state', self.js('normal.value') == '')
        key(2)
        self.until(lambda: self.js('normal.value') == '-1', 'complete numeric edit')
        self.check('native-number-editor-retains-original-sanitization-and-trusted-input',
                   not self.js('normal.validity.badInput') and all(row['trusted'] for row in self.js('events')))
        # These commands are interpreted by the original GNUstep field editor.
        for code in (30, 37):
            for event in ('key 29 1', f'key {code} 1', f'key {code} 0', 'key 29 0'):
                assert self.command(event)['ok']
        self.until(lambda: self.js('normal.value') == '', 'native Emacs editing commands')
        self.check('native-number-editor-emacs-beginning-and-kill-line', True)

    def repeat_trial(self):
        self.reset('normal', '0', None, None, '1')
        self.pointer('normal', 1)
        self.button(1)
        try:
            self.until(lambda: len(self.js('events.filter(event=>event.type==="input")')) >= 3,
                       'original native stepper repeat')
        finally:
            self.button(0)
        self.until(lambda: any(row['type'] == 'change' for row in self.js('events')), 'repeat commit')
        value = self.js('normal.value')
        time.sleep(.15)
        rows = self.js('events')
        self.check('native-stepper-repeat-returns-original-ordered-browser-events',
                   value == self.js('normal.value') and int(value) == len([row for row in rows if row['type'] == 'input'])
                   and sum(row['type'] == 'change' for row in rows) == 1 and all(row['trusted'] for row in rows))

    def lifecycle_trials(self):
        self.reset('normal', '0', None, None, '1')
        self.js('normal.addEventListener("input",()=>normal.readOnly=true,{once:true})')
        self.pointer('normal', 1)
        self.button(1)
        try:
            self.until(lambda: self.js('normal.readOnly'), 'script read-only update')
            time.sleep(.1)
        finally:
            self.button(0)
        self.until(lambda: any(row['type'] == 'change' for row in self.js('events')), 'read-only gesture commit')
        self.check('script-readonly-stops-steps-and-preserves-original-commit',
                   self.js('normal.value') == '1' and len(self.js('events')) == 2)
        self.js('normal.readOnly=false')

        self.reset('normal', '0', None, None, '1')
        self.js('normal.addEventListener("input",()=>normal.type="text",{once:true})')
        self.pointer('normal', 1)
        self.button(1)
        self.until(lambda: self.js('normal.type') == 'text', 'script changed input type')
        self.button(0)
        time.sleep(.1)
        self.check('script-retyping-retires-native-stepper-during-action', self.js('normal.value') == '1')
        self.js('normal.type="number"')

        self.reset('normal', '0', None, None, '1')
        self.js('normal.addEventListener("input",()=>{window.removedNumber=normal;normal.remove()},{once:true})')
        self.pointer('normal', 1)
        self.button(1)
        self.until(lambda: self.js('!document.getElementById("normal")'), 'script removed input')
        self.button(0)
        time.sleep(.1)
        self.check('script-removal-retires-native-stepper-during-action', self.js('removedNumber.value') == '1')
        self.js('document.body.prepend(removedNumber);window.removedNumber=null')

    def arrow_trial(self):
        self.reset('normal', '2', None, None, '1')
        self.js('normal.focus()')
        for state in (1, 0):
            assert self.command(f'key 103 {state}')['ok']
        time.sleep(.15)
        self.check('number-arrow-key-retains-original-application-action', self.js('normal.value') == '3')
