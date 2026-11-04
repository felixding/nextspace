"""Legacy title gestures, exercised through real compositor pointer input."""
import json
import time
from PIL import Image
from integration import until


def point_at_title(command, window):
    w = window()
    command(f"pointer {w['x'] + w['width'] // 2} {w['y'] + 11}")


def title_click(command, window, button=272, modifiers=(), count=1):
    point_at_title(command, window)
    for code in modifiers: command(f"key {code} 1")
    try:
        for _ in range(count): command(f"button {button}")
    finally:
        for code in reversed(modifiers): command(f"key {code} 0")


def click_content(command, window):
    w = window()
    command(f"pointer {w['x'] + 50} {w['y'] + w['frame_top'] + 30}")
    command('button 272')


def run(command, window, send, events, sync, shell, replace_shell, target, captures, artifacts):
    artifacts.mkdir()
    rows = []

    def title():
        point_at_title(command, window)

    def click(button=272, modifiers=()):
        title_click(command, window, button, modifiers)

    def double(modifiers=(), button=272):
        title_click(command, window, button, modifiers, count=2)

    def state(shaded, axes, normal, head):
        expected = (head['work_x'] if axes & 1 else normal['x'],
                    head['work_y'] if axes & 2 else normal['y'],
                    head['work_width'] if axes & 1 else normal['width'],
                    head['work_height'] if axes & 2 else normal['height'])
        def matched():
            w = window()
            return w if w['shaded'] == shaded and w.get('maximized_axes', 0) == axes and tuple(
                w[k] for k in ('x', 'y', 'width', 'height')) == expected else None
        return until(matched, f"title state shaded={shaded} axes={axes}")

    def snapshot(name, scale):
        w = window()
        source = captures / f"frame-{w['id']}-{scale}.png"
        def image():
            try:
                with Image.open(source) as im:
                    if im.size != ((w['width'] * scale + 60) // 120, (w['frame_top'] * scale + 60) // 120):
                        return None
                    return im.copy()
            except OSError:
                return None
        until(image, 'title buffer follows its frame').save(artifacts / f'{name}-{scale}.png')
        rows.append(dict(name=name, scale=scale, window=w))
        (artifacts / 'partial-results.json').write_text(json.dumps(rows, indent=2) + '\n')

    for scale in (120, 150, 180, 210, 240):
        assert command(f'test-scale {target} {scale} 10000')['ok']
        assert command('confirm')['ok']
        head = next(h for h in command('outputs') if h['name'] == target)
        shell.pump()
        identifier = next(identifier for identifier, output in shell.outputs.items() if output['name'] == target)
        shell.send(f"insets {identifier} 7 11 67 64")
        until(lambda: next(h for h in command('outputs') if h['name'] == target)['work_width'] == head['width'] - 74,
              'title work area')
        head = next(h for h in command('outputs') if h['name'] == target)
        w = window()
        command(f"move {w['id']} {head['x'] + 100} {head['y'] + 50}")
        until(lambda: window().get('decoration_scale') == scale, 'title gesture backing density')
        normal = window()
        snapshot('normal', scale)
        double(); state(True, 0, normal, head); snapshot('double-shade', scale)
        double(); state(False, 0, normal, head); snapshot('double-unshade', scale)
        for modifiers, axes, label in (((29,), 2, 'vertical'), ((42,), 1, 'horizontal'), ((29, 42), 3, 'both')):
            double(modifiers); state(False, axes, normal, head); snapshot(label + '-maximize', scale)
            double(modifiers); state(False, 0, normal, head); snapshot(label + '-restore', scale)
        # These four states match the retained legacy wheel baseline.
        title(); command('scroll -1')
        assert not window()['shaded']
        snapshot('first-wheel-up', scale)
        command('scroll -1'); state(True, 0, normal, head); snapshot('second-wheel-up', scale)
        command('scroll 1')
        assert window()['shaded']
        snapshot('first-wheel-down', scale)
        command('scroll 1'); state(False, 0, normal, head); snapshot('second-wheel-down', scale)
        # Toggling one axis must retain the other and the original floating frame.
        for modifiers, axes in (((29,), 2), ((42,), 3), ((29,), 1), ((42,), 0)):
            double(modifiers); state(False, axes, normal, head); snapshot('xor-' + str(axes), scale)
        double((29,)); state(False, 2, normal, head)
        send('fullscreen')
        until(lambda: window()['fullscreen'], 'fullscreen supersedes a vertical maximize')
        send('unfullscreen')
        until(lambda: not window()['fullscreen'], 'fullscreen ends')
        state(False, 2, normal, head); snapshot('vertical-after-fullscreen', scale)
        double((29,)); state(False, 0, normal, head)

    def body_click():
        click_content(command, window)

    for modifiers, axes in (((29,), 2), ((42,), 1), ((29, 42), 3)):
        for mode in (0, 1, 2, 3):
            body_click(); double(modifiers); state(False, axes, normal, head)
            shell.send(f'maximized-drag {mode}'); shell.snapshot()
            body_click(); sync(); title()
            buttons = len([event for event in events() if event['event'] == 'button'])
            before = window()
            command('button 272 1')
            expected_move = dict(id=0, mode=0) if mode == 3 else dict(id=before['id'], mode=1)
            assert command('move-state') == expected_move
            state(False, axes, normal, head)
            command(f"pointer {before['x'] + before['width'] // 2 + 4} {before['y'] + 15}")
            state(False, axes, normal, head)
            command(f"pointer {before['x'] + before['width'] // 2 + 40} {before['y'] + 36}")
            if mode != 3:
                command('key 1 1'); command('key 1 0')
            command('button 272 0')
            sync()
            assert len([event for event in events() if event['event'] == 'button']) == buttons, \
                'A canceled frame gesture leaked a client button event'
            state(False, axes, normal, head)
            snapshot(f'axes-{axes}-drag-{mode}-escape', scale)
            body_click(); double(modifiers); state(False, 0, normal, head)
        shell.send('maximized-drag 0'); shell.snapshot()
        body_click(); double(modifiers); state(False, axes, normal, head)
        body_click(); title()
        before = window()
        command('button 272 1')
        command(f"pointer {before['x'] + before['width'] // 2 + 40} {before['y'] + 36}")
        command('button 272 0')
        body_click(); double(modifiers)
        floating = dict(normal, x=normal['x'] + (0 if axes & 1 else 40),
                        y=normal['y'] + (0 if axes & 2 else 25))
        state(False, 0, floating, head)
        snapshot(f'axes-{axes}-move-restores-unmaximized-coordinate', scale)
        command(f"move {before['id']} {normal['x']} {normal['y']}")
        state(False, 0, normal, head)

    body_click(); title()
    for index in range(4):
        command('scroll-v120 -60')
        assert window()['shaded'] == (index == 3), 'High-resolution wheel steps were lost or counted twice'
        if index % 2: snapshot('half-wheel-up-' + str(index), scale)
    for index in range(4):
        command('scroll-v120 60')
        assert window()['shaded'] == (index != 3)
        if index % 2: snapshot('half-wheel-down-' + str(index), scale)

    for interval in (100, 400, 250):
        shell.send(f'double-click-time {interval}')
        until(lambda: command('decoration-settings')['double_click_time'] == interval, 'shared double-click interval')
    for invalid in (0, 60001):
        shell.send(f'double-click-time {invalid}')
        shell.snapshot()
        assert command('decoration-settings')['double_click_time'] == 250
    shell = replace_shell()
    assert command('decoration-settings')['double_click_time'] == 250
    shell.send('double-click-time 100')
    until(lambda: command('decoration-settings')['double_click_time'] == 100, 'short interval')
    click(); time.sleep(.15); click()
    assert not window()['shaded'], 'Clicks outside the configured interval formed a pair'
    click(); until(lambda: window()['shaded'], 'fresh click pairs with preceding click inside interval')
    double(); until(lambda: not window()['shaded'], 'unshade after timed pair')
    # Shift single-click and middle double-click preserve selection semantics.
    click(modifiers=(42,)); until(lambda: window()['selected'], 'Shift title selects')
    def selected_title():
        w = window()
        try:
            with Image.open(captures / f"frame-{w['id']}-{scale}.png") as im:
                return im.convert('RGB').getpixel((im.width // 2, 0)) == (255, 255, 255)
        except OSError:
            return False
    until(selected_title, 'selection border repaints')
    double(button=274); until(lambda: not window()['selected'], 'middle double-click deselects')
    snapshot('selection-restored', scale)
    # Fixed-size style rejects modifier maximize gestures.
    send('style 1'); sync()
    double((29,)); assert not window()['maximized']
    send('style 15'); sync()
    shell.send('double-click-time 350')
    until(lambda: command('decoration-settings')['double_click_time'] == 350, 'restore frame interval')
    (artifacts / 'results.json').write_text(json.dumps(rows, indent=2) + '\n')
    return rows
