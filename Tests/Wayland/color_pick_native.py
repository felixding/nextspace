"""Exercise NSColorPanel's actual magnifier across independent Wayland clients."""
import json
from pathlib import Path

from color_panel import color_panel
from integration import until
from text_input import Client
from timemon_pause import application_action


def run(compositor, application, probe, registry_probe, artifacts):
    cases = []
    with color_panel(compositor, application, probe, artifacts/'panel') as panel:
        source = Client(str(registry_probe), '--color-source', panel.env, artifacts, 'source')
        try:
            command = panel.command

            def source_window():
                return next(w for w in command('windows') if w['pid'] == source.process.pid)

            def color():
                return panel.controls()['color_rgba']

            def equal(actual, expected):
                return max(abs(a-b) for a,b in zip(actual, expected)) < 1/255

            def start():
                state = panel.controls()
                button = next(b for b in state['buttons'] if b['action'] == '_magnify:')
                panel.click(button['base'])
                return until(lambda: (value if (value := command('color-pick-state'))['active'] else None),
                    'NSColorPanel starts the compositor pick')

            def preview(argb, expected):
                source.send('color '+argb); source.sync()
                w = source_window()
                assert command(f"pointer {w['x']+20} {w['y']+40}")['ok']
                return until(lambda: (value if equal(value := color(), expected) else None),
                    'NSColorPanel previews an independent client pixel')

            for density in (120,150,180,210,240):
                for output in command('outputs'):
                    assert command(f"test-scale {output['name']} {density} 10000")['ok']
                    assert command('confirm')['ok']
                heads = sorted(command('outputs'), key=lambda h:h['x'])
                w = panel.window()
                assert command(f"move {w['id']} {heads[0]['x']+40} {heads[0]['y']+100}")['ok']
                w = source_window()
                assert command(f"move {w['id']} {heads[-1]['x']+40} {heads[-1]['y']+100}")['ok']
                until(lambda: panel.captured(density), 'Native picker density')
                initial = color()
                active = start()
                assert active['density'] == density
                before = source.sync()
                chosen = [38/255,144/255,208/255,1]
                selected_preview = preview('ff2690d0', chosen)
                assert command('button 272')['ok']
                until(lambda:not command('color-pick-state')['active'], 'Native selection finishes')
                selected = color(); assert equal(selected, chosen)
                source.sync()
                assert not any(e['event']=='button' for e in source.events[before:])
                cancellations = []
                for mode in ('escape', 'right'):
                    application_action(probe, panel.env, panel.artifacts, 'seed-alpha', '0.35')
                    original = color(); active = start()
                    assert abs(original[3]-.35) < .001
                    shown = preview('ffffffff', [1,1,1,1])
                    assert not equal(shown, original)
                    if mode == 'escape':
                        assert command('key 1 1')['ok']; assert command('key 1 0')['ok']
                    else: assert command('button 273')['ok']
                    until(lambda:not command('color-pick-state')['active'], 'Native cancellation finishes')
                    restored = until(lambda:(value if equal(value := color(), original) else None),
                        'Native cancellation restores the original color')
                    assert command('color-pick-state')['seat_buttons'] == 0
                    cancellations.append(dict(mode=mode,original=original,preview=shown,restored=restored))
                # Tab to the magnifier, then activate without a fresh click.
                assert command(f"focus {panel.window()['id']}")['ok']
                for _ in range(32):
                    if panel.controls().get('first_responder_action') == '_magnify:':break
                    for state in (1,0):assert command(f'key 15 {state}')['ok']
                else:raise AssertionError(('Magnifier is absent from the keyboard loop',panel.controls()))
                for state in (1,0):assert command(f'key 57 {state}')['ok']
                until(lambda:command('color-pick-state')['active'],'Space activates the focused native magnifier')
                keyboard_preview=preview('ff2690d0',chosen)
                for state in (1,0):assert command(f'key 28 {state}')['ok']
                until(lambda:not command('color-pick-state')['active'],'Enter selects a native color')
                assert equal(color(),chosen)
                # Tab clears the native focus ring before the next density.
                assert command(f"focus {panel.window()['id']}")['ok']
                for state in (1,0):assert command(f'key 15 {state}')['ok']
                cases.append(dict(density=density,initial=initial,preview=selected_preview,
                    selected=selected,cancellations=cancellations,selection_click_suppressed=True,
                    keyboard_preview=keyboard_preview,keyboard_space_activation=True,keyboard_enter_selection=True))
            source.send('quit'); source.process.wait(timeout=5)
        finally:
            source.stop()
    result = dict(passed=True,cases=cases,normal_keyboard_quit=panel.normal_keyboard_quit,
        all_processes_reaped=panel.app.poll() is not None and source.process.poll() is not None,
        application_runtime=panel.runtime,hardware_tested=False,full_plan_complete=False)
    (artifacts/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
