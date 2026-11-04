"""Client size requests supersede an in-progress compositor move."""
import json
from integration import until
from titlebar import click_content, point_at_title, title_click


def run(command, window, send, events, sync, shell, target, artifacts):
    artifacts.mkdir()
    rows = []
    held = False
    frame = lambda w: tuple(w[k] for k in ('x', 'y', 'width', 'height'))

    def expected(axes, fullscreen, normal, head):
        if fullscreen:
            return tuple(head[k] for k in ('x', 'y', 'width', 'height'))
        return (head['work_x'] if axes & 1 else normal['x'],
                head['work_y'] if axes & 2 else normal['y'],
                head['work_width'] if axes & 1 else normal['width'],
                head['work_height'] if axes & 2 else normal['height'])

    def state(axes, fullscreen, normal, head, label):
        def matches():
            w = window()
            return w if w['maximized_axes'] == axes and w['fullscreen'] == fullscreen and \
                frame(w) == expected(axes, fullscreen, normal, head) else None
        return until(matches, label)

    try:
        for density in (120, 150, 180, 210, 240):
            assert command(f'test-scale {target} {density} 10000')['ok']
            assert command('confirm')['ok']
            head = next(h for h in command('outputs') if h['name'] == target)
            w = window()
            command(f"move {w['id']} {head['x'] + 100} {head['y'] + 50}")
            until(lambda: window().get('decoration_scale') == density, 'request fixture density')
            normal = window()
            for axes, modifiers in ((0, ()), (1, (42,)), (2, (29,)), (3, (29, 42))):
                for mode in (0, 1, 2, 3):
                    shell.send(f'maximized-drag {mode}'); shell.snapshot()
                    for request in ('maximize', 'restore', 'fullscreen'):
                        for moved in (False, True):
                            if axes:
                                click_content(command, window)
                                title_click(command, window, modifiers=modifiers, count=2)
                            state(axes, False, normal, head, 'initial requested axis state')
                            click_content(command, window); sync()
                            buttons = len([e for e in events() if e['event'] == 'button'])
                            point_at_title(command, window)
                            before = window()
                            command('button 272 1'); held = True
                            active = not (axes and mode == 3)
                            assert command('move-state') == dict(id=before['id'] if active else 0, mode=1 if active else 0)
                            if moved:
                                command(f"pointer {before['x'] + before['width'] // 2 + 41} {before['y'] + 40}")
                            during = window()
                            send(request); sync()
                            requested_axes = 3 if request == 'maximize' else 0 if request == 'restore' else axes
                            requested = state(requested_axes, request == 'fullscreen', normal, head,
                                f'client {request} supersedes axes={axes} mode={mode} moved={moved}')
                            assert command('move-state') == dict(id=0, mode=0), 'Client state request left its move active'
                            command('button 272 0'); held = False; sync()
                            assert len([e for e in events() if e['event'] == 'button']) == buttons, \
                                'A superseded frame move leaked its release into client content'
                            if request == 'fullscreen':
                                send('unfullscreen'); sync()
                                state(axes, False, normal, head, 'fullscreen restores state from before canceled move')
                            send('restore'); sync()
                            restored = state(0, False, normal, head, 'client restore retains pre-move floating geometry')
                            rows.append(dict(density=density, axes=axes, drag_mode=mode, moved=moved,
                                request=request, before=before, during=during, requested=requested, restored=restored))
                            (artifacts / 'partial-results.json').write_text(json.dumps(rows, indent=2) + '\n')
        (artifacts / 'results.json').write_text(json.dumps(rows, indent=2) + '\n')
        return rows
    except BaseException:
        (artifacts / 'failure.json').write_text(json.dumps(dict(windows=command('windows'),
            move=command('move-state'), completed=len(rows)), indent=2) + '\n')
        raise
    finally:
        if held: command('button 272 0')
        shell.send('maximized-drag 0'); shell.snapshot()
