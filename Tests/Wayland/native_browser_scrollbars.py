"""Real-seat verification of native browser scrollbar and dropdown interactions."""
import argparse
import json
from pathlib import Path
import time

from desktop_input import Desktop


def wait_result(func, check, seconds=8):
    until = time.monotonic()+seconds
    while time.monotonic()<until:
        result = func()
        if check(result):
            return result
        time.sleep(.05)
    raise AssertionError(result)


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('root', type=Path)
args = parser.parse_args()
desktop = Desktop(args.root)
command = desktop.command
scale = command('outputs')[0]['scale'] / 120
checks = []

def window(app):
    return next(w for w in command('windows') if w['app_id']==app and w['level']==0)
def model(app):
    title = window(app)['title']
    row = json.JSONDecoder().raw_decode(title.split('|',1)[1])[0]
    fields = ('density', 'height', 'gutter', 'page', 'ended', 'notes', 'choices',
              'dropdown', 'open', 'editor', 'notesFocused', 'pastedURL')
    state = dict(zip(fields, row, strict=True))
    for field in ('notes','choices'):
        state[field]=dict(zip(('x','y','width','height','gutter','value'),state[field]))
    return state

def chord(modifier, key):
    assert command(f'key {modifier} 1')['ok']
    try:
        desktop.key(key)
    finally:
        assert command(f'key {modifier} 0')['ok']

front = window('firefox-esr')
x,y = front['x']+front['width']//2,front['y']+10
for event in (f'pointer {x} {y}', 'button 272 1', f'pointer {x+78} {y+60}', 'button 272 0'):
    assert command(event)['ok']
wait_result(lambda:window('firefox-esr')['y'],lambda value:value!=front['y'])
for app in ('chromium-browser','firefox-esr'):
    win = window(app)
    exposed = 45 if app=='chromium-browser' else win['width']-45
    desktop.click(win['x']+exposed,win['y']+10)
    wait_result(lambda:window(app),lambda w:w['focused'])
    before = model(app)
    ratio = before['density']/scale
    assert abs(ratio-1)<.02,(app,scale,before['density'])
    x0 = win['x']+win['frame_left']
    bottom = win['y']+win['frame_top']+win['surface_height']
    y0 = bottom-before['height']*ratio
    gutter = before['gutter']*ratio
    assert 10<=gutter<=25,(app,scale,gutter)
    desktop.capture(app+'-native-arrows-before')
    for field in ('notes','choices'):
        geometry = before[field]
        assert 10<=geometry['gutter']*ratio<=25,(app,field,geometry)
        arrow_x = x0+(geometry['x']+geometry['gutter']/2)*ratio
        arrow_y = y0+(geometry['y']+geometry['height']-geometry['gutter']/2)*ratio
        desktop.click(arrow_x,arrow_y)
        changed = wait_result(lambda:model(app),lambda m:m[field]['value']>before[field]['value'])
        assert changed['page']==before['page'],(field,changed)
        checks.append(dict(browser=app, owner=field, offset=changed[field]['value']))
    def dropdown(state):
        x,y,width,height=state['dropdown']
        return x0+(x+width/2)*ratio,y0+(y+height/2)*ratio
    def menu():
        return next((w for w in command('windows') if w['visible'] and w['level']==101),None)
    desktop.click(*dropdown(before))
    initial_menu=wait_result(menu,bool)
    wait_result(lambda:model(app)['open'],bool)
    desktop.click(*dropdown(before))
    wait_result(menu,lambda value:value is None)
    wait_result(lambda:model(app)['open'],lambda value:not value)
    wait_result(lambda:window(app),lambda value:value['focused'])
    desktop.capture(app+'-dropdown-closed')
    desktop.click(*dropdown(before))
    wait_result(menu,bool)
    desktop.click(x0+gutter/2,bottom-gutter/2-2)
    after = wait_result(lambda:model(app),lambda m:m['page']>before['page'])
    checks.append(dict(browser=app, owner='page', offset=after['page']))
    wait_result(menu,lambda value:value is None)
    desktop.click(*dropdown(after))
    moved=wait_result(menu,bool)
    assert abs(initial_menu['y']-moved['y']-after['page']*ratio)<3,(app,scale,initial_menu,moved,after)
    desktop.key(1)
    wait_result(menu,lambda value:value is None)
    wait_result(lambda:model(app)['open'],lambda value:not value)
    desktop.click(*dropdown(after))
    wait_result(menu,bool)
    assert command('pointer %d %d' % (x0+win['surface_width']//2,y0+140))['ok']
    ended = model(app)['ended']
    assert command('scroll -1')['ok']
    wheel = wait_result(lambda:model(app),lambda m:m['page']<after['page'] and m['ended']>ended)
    wait_result(menu,lambda value:value is None)
    wait_result(lambda:model(app)['open'],lambda value:not value)
    desktop.click(*dropdown(wheel))
    wait_result(menu,bool)
    desktop.key(1)
    wait_result(menu,lambda value:value is None)
    checks.append(dict(browser=app, dropdown_reopened=True, wheel_dismissal=True, escape=True))
    desktop.capture(app+'-native-arrows-after')

    notes = model(app)['notes']
    editor_point = x0+(notes['x']+notes['width']/2)*ratio, y0+(notes['y']+24)*ratio
    desktop.click(*editor_point)
    wait_result(lambda:model(app)['notesFocused'],bool)
    chord(56, 30)  # Alt+A selects all in the original editor.
    wait_result(lambda:model(app)['editor'],lambda pos:pos[0]==0 and pos[1]==pos[2]>0)
    chord(56, 38)  # Alt+L transfers focus to the browser's original address bar.
    wait_result(lambda:model(app)['notesFocused'],lambda focused:not focused)
    previous = command('selection-state')['serial']
    chord(56, 46)
    wait_result(lambda:command('selection-state'),
                lambda state:state['serial']!=previous and state['owned'] and not state['pending'])
    desktop.key(1)
    desktop.click(*editor_point)
    wait_result(lambda:model(app)['notesFocused'],bool)
    chord(56, 30)
    chord(56, 47)
    wait_result(lambda:model(app)['pastedURL'],bool)
    checks.append(dict(browser=app, original_editor_select_all=True, original_address_clipboard=True))

report = dict(complete=True, scale=scale, checks=checks)
(args.root/'ordinary-browser-scrollbars.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report))
