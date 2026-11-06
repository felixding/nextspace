"""Exercise actual browser windows through the shared compositor frame."""
from titlebar import title_click


def run(command, wait, check, desktop, identifier, content_check=None):
    def window():
        return next(w for w in command('windows') if w['id'] == identifier)

    def title_point(w):
        return w['x'] + w['frame_width'] // 2, w['y'] + w['frame_top'] // 2

    def point(x, y):
        assert command(f'pointer {x} {y}')['ok']

    def button(state):
        assert command(f'button 272 {state}')['ok']

    def double_title():
        # An ordinary content click ends any preceding title-click sequence.
        w = window()
        point(w['x'] + w['width'] // 2, w['y'] + w['height'] // 2)
        assert command('button 272')['ok']
        title_click(command, window, count=2)

    original = window()
    x, y = title_point(original)
    point(x, y)
    button(1)
    check('native-frame-title-starts-move', command('move-state') == dict(id=identifier, mode=1))
    point(x + 48, y + 24)
    button(0)
    moved = window()
    check('native-frame-title-moves-browser', (moved['x'], moved['y']) == (original['x'] + 48, original['y'] + 24))
    point(moved['x'] + moved['width'] // 2, moved['y'] + moved['height'] // 2)
    assert command('button 272')['ok']
    x, y = title_point(moved)
    point(x, y)
    button(1)
    point(x + 40, y + 20)
    for event in ['key 1 1', 'key 1 0']:
        assert command(event)['ok']
    button(0)
    check('native-frame-escape-restores-move', (window()['x'], window()['y']) == (moved['x'], moved['y']))
    double_title()
    shaded = wait(window, lambda w: w['shaded'])
    check('native-frame-double-click-shades', command(f"hit {shaded['x'] + 50} {shaded['y'] + shaded['frame_top'] + 50}")['id'] != identifier)
    desktop('native-frame-shaded')
    # The shaded frame has no content to click; a resize-area click is outside
    # it and ends the sequence without invoking a browser control.
    point(shaded['x'] + shaded['width'] // 2, shaded['y'] + shaded['height'] + 10)
    assert command('button 272')['ok']
    title_click(command, window, count=2)
    wait(window, lambda w: not w['shaded'])
    check('native-frame-double-click-unshades', not window()['shaded'])
    before = wait(window, lambda w: not w['shaded'] and w['frame_height'] > w['frame_top'] + w['frame_bottom'] and
        command(f"hit {w['x'] + w['frame_width'] - 5} {w['y'] + w['frame_height'] - 5}")['id'] == identifier)
    x, y = before['x'] + before['frame_width'] - 5, before['y'] + before['frame_height'] - 5
    point(x, y)
    button(1)
    moving = command('move-state')
    check('native-frame-resize-starts', moving == dict(id=identifier, mode=2), state=moving, window=before)
    point(x + 32, y + 20)
    button(0)
    resized = wait(window, lambda w: (w['frame_width'], w['frame_height']) == (before['frame_width'] + 32, before['frame_height'] + 20))
    check('native-frame-resizes-browser-content', (resized['surface_width'], resized['surface_height']) == (before['surface_width'] + 32, before['surface_height'] + 20))
    desktop('native-frame-resized')
    if content_check:content_check('resized')
    for event in ['key 87 1', 'key 87 0']:
        assert command(event)['ok']
    head = command('outputs')[0]
    fullscreen = wait(window, lambda w: w['fullscreen'] and not w['server_decorated'] and
        (w['frame_width'], w['frame_height'], w['surface_width'], w['surface_height']) == (head['width'], head['height'], head['width'], head['height']))
    # Inventory retains the negotiated insets for restoring a normal window;
    # effective fullscreen geometry and frame visibility prove their omission.
    check('native-frame-fullscreen-uses-content-bounds', not fullscreen['server_decorated'], window=fullscreen)
    desktop('native-frame-fullscreen')
    for event in ['key 87 1', 'key 87 0']:
        assert command(event)['ok']
    restored = wait(window, lambda w: not w['fullscreen'] and w['server_decorated'] and
        (w['frame_width'], w['frame_height']) == (resized['frame_width'], resized['frame_height']))
    check('native-frame-restored-after-fullscreen', restored['server_decorated'] and (restored['frame_width'], restored['frame_height']) == (resized['frame_width'], resized['frame_height']))
    if content_check:content_check('restored-fullscreen')
    point(restored['x'] + 10, restored['y'] + 10)
    assert command('button 272')['ok']
    wait(window, lambda w: w['minimized'])
    check('native-frame-minimize-button', window()['minimized'])
    assert command(f'minimize {identifier} 0')['ok']
    assert command(f'focus {identifier}')['ok']
    wait(window, lambda w: not w['minimized'] and w['focused'])
    restored = window()
    desktop('native-frame-restored')
    point(restored['x'] + restored['frame_width'] - 10, restored['y'] + 10)
    assert command('button 272')['ok']
    wait(lambda: command('windows'), lambda windows: not any(w['id'] == identifier for w in windows))
    check('native-frame-close-button', not any(w['id'] == identifier for w in command('windows')))
