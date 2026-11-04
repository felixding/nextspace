"""Check TimeMon's pause mark and live vector graph through native icon buffers."""
import json
from functools import partial
from pathlib import Path
import subprocess
import time
from PIL import Image, ImageChops
from gnustep import capture_frame, capture_process_failure, headless_session, process_runtime
from integration import until


def application_action(probe, env, artifacts, action, *arguments):
    started = time.monotonic()
    failure = None
    process = subprocess.Popen([str(probe), '--timemon', action, *map(str,arguments)], env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        stdout, stderr = process.communicate(timeout=15)
        elapsed = time.monotonic() - started
    except subprocess.TimeoutExpired as error:
        failure = error
        elapsed = time.monotonic() - started
        try:
            capture_process_failure(process, artifacts, 'failure-timemon-query')
        except Exception as diagnostic_error:
            (artifacts / 'failure-timemon-query-diagnostic.txt').write_text(repr(diagnostic_error) + '\n')
        finally:
            if process.poll() is None:
                process.kill()
            stdout, stderr = process.communicate(timeout=5)
    with (artifacts / 'queries.jsonl').open('a') as log:
        log.write(json.dumps(dict(action=action, arguments=list(map(str,arguments)),returncode=process.returncode,
                                  stdout=stdout, stderr=stderr, elapsed_seconds=elapsed,
                                  timed_out=failure is not None)) + '\n')
    if failure:
        raise failure
    if process.returncode != 0 and action == 'state': return False
    assert process.returncode == 0, stderr
    state = json.loads(stdout); assert state['running']
    return state


def live_timer(compositor, application, probe, artifacts):
    """Observe real timer updates, a frozen pause and updates after resuming."""
    artifacts.mkdir(parents=True)
    with headless_session(compositor, artifacts / 'native') as (env, command):
        with (artifacts / 'application.log').open('w') as log:
            app = subprocess.Popen([str(application), '-GSBackend', 'libgnustep-wayland',
                '-GSTheme', 'NextSpace', '-NSUseRunningCopy', 'NO', '-UpdatePeriod', '0.1',
                '-LagFactor', '1', '-LayerFactor', '4'], env=env, stdout=log, stderr=log)
        load = None
        query = partial(application_action, probe, env, artifacts)
        def capture(paused=False):
            assert app.poll() is None, (artifacts / 'application.log').read_text()
            w = next((w for w in command('windows') if w['pid'] == app.pid and w['style'] & 64 and w['visible']), None)
            if not w or w['preferred_scale'] != 240: return None
            path = artifacts / 'native/captures' / f"window-{w['client_id']}-240.png"
            frame = capture_frame(path,(128,128))
            if not frame: return None
            pixels = frame['image']
            reds = sum(r > g+50 and r > b+50 for r,g,b,a in pixels.getdata())
            return pixels if bool(reds) == paused else None
        try:
            until(lambda: query('state'), 'TimeMon application registration')
            for output in command('outputs'):
                assert command(f"test-scale {output['name']} 240 10000")['ok'] and command('confirm')['ok']
            before = until(capture, 'TimeMon live graph at 200%')
            before.save(artifacts / 'before-load.png')
            load = subprocess.Popen(['yes'], stdout=subprocess.DEVNULL)
            def changed():
                image = capture()
                return image if image and image.tobytes() != before.tobytes() else False
            running = until(changed, 'TimeMon real timer update under CPU load')
            running.save(artifacts / 'running-load.png')
            query('toggle')
            paused = until(lambda: capture(True), 'TimeMon live timer paused')
            paused.save(artifacts / 'paused-load.png')
            deadline = time.monotonic() + 2
            samples = []
            def stable():
                pixels = capture(True)
                assert pixels is not None and pixels.tobytes() == paused.tobytes(), 'Graph updated while paused'
                samples.append(time.monotonic())
                return time.monotonic() >= deadline
            until(stable, 'TimeMon remains frozen under CPU load')
            query('toggle')
            resumed = until(capture, 'TimeMon real timer resumed')
            resumed.save(artifacts / 'resumed.png')
            before = resumed
            until(changed, 'TimeMon graph updates after resuming').save(artifacts / 'resumed-updated.png')
            runtime = process_runtime(app.pid)
            load_runtime = process_runtime(load.pid)
        finally:
            for process in (load, app):
                if process and process.poll() is None: process.terminate(); process.wait(timeout=5)
    result = dict(passed=True, scale=240, real_cpu_load=True, timer_period_seconds=.1,
        frozen_seconds=samples[-1]-samples[0], stable_samples=len(samples),
        graph_updates_before_pause=True, graph_updates_after_resume=True,
        application_runtime=runtime, load_runtime=load_runtime,
        owned_processes_reaped=app.poll() is not None and load.poll() is not None)
    (artifacts / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def run(compositor, application, probe, resources, artifacts, baseline=None):
    artifacts.mkdir(parents=True)
    frames = []
    with Image.open(resources / 'TimeMonP.tiff') as image:
        assert image.n_frames == 5
        for index in range(5):
            image.seek(index); frames.append(image.convert('RGBA'))
    cases = []
    with headless_session(compositor, artifacts / 'native') as (env, command):
        with (artifacts / 'application.log').open('w') as log:
            app = subprocess.Popen([str(application), '-GSBackend', 'libgnustep-wayland',
                '-GSTheme', 'NextSpace', '-NSUseRunningCopy', 'NO', '-UpdatePeriod', '3600'],
                env=env, stdout=log, stderr=log)
        query = partial(application_action, probe, env, artifacts)
        def window():
            assert app.poll() is None, (artifacts / 'application.log').read_text()
            return next((w for w in command('windows') if w['pid'] == app.pid and w['style'] & 64 and w['visible']), None)
        def capture(density, paused):
            def ready():
                current = window()
                if not current or current['preferred_scale'] != density: return False
                path = artifacts / 'native/captures' / f"window-{current['client_id']}-{density}.png"
                frame = capture_frame(path,(current['buffer_width'],current['buffer_height']))
                if not frame: return False
                pixels = frame['image']
                if pixels.size != ((64*density+60)//120,)*2: return False
                reds = sum(r > g+50 and r > b+50 for r,g,b,a in pixels.getdata())
                if bool(reds) != paused: return False
                if not paused and pixels.getpixel((round(37*density/120), round(37*density/120)))[:3] != (255,255,255): return False
                return current, pixels
            return until(ready, 'TimeMon ' + ('paused' if paused else 'running') + ' native pixels')
        try:
            initial = until(window, 'TimeMon application icon')
            until(lambda: query('state'), 'TimeMon application registration')
            capture(120, False); query('toggle')
            for index, density in enumerate((120,150,180,210,240)):
                for output in command('outputs'):
                    assert command(f"test-scale {output['name']} {density} 10000")['ok'] and command('confirm')['ok']
                output = command('outputs')[0]
                assert command(f"move {initial['id']} {output['x']+10} {output['y']+10}")['ok']
                current, paused = capture(density, True)
                assert not current['legacy']
                paused.save(artifacts / f'paused-{density}.png')
                query('toggle')
                _, running = capture(density, False)
                running.save(artifacts / f'running-{density}.png')
                layer = Image.new('RGBA', running.size)
                layer.paste(frames[index], (8*density//120,)*2)
                expected = Image.alpha_composite(running, layer)
                expected.save(artifacts / f'expected-{density}.png')
                maximum = max(v[1] for v in ImageChops.difference(paused, expected).getextrema())
                assert maximum <= 1, (density, maximum)
                original_maximum = None
                if baseline:
                    original = Image.open(baseline / f'paused-{density}.png').convert('RGBA')
                    original_maximum = max(v[1] for v in ImageChops.difference(running, original).getextrema())
                    assert original_maximum <= 1, ('Existing vector rings changed', density, original_maximum)
                cases.append(dict(scale=density, window=current, maximum_channel_difference=maximum,
                                  baseline_graph_channel_difference=original_maximum))
                if index != 4: query('toggle')
            (artifacts / 'application-runtime.json').write_text(json.dumps(process_runtime(app.pid), indent=2) + '\n')
        finally:
            if app.poll() is None: app.terminate(); app.wait(timeout=5)
    live = live_timer(compositor, application, probe, artifacts / 'live-timer')
    result = dict(passed=True, cases=cases, pause_resume_cycles=5, scale_changed_while_paused=True,
                  native_pixel_comparisons=5, baseline_graph_comparisons=5 if baseline else 0,
                  live_timer=live,
                  owned_application_reaped=app.poll() is not None, full_plan_complete=False)
    (artifacts / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
    print('TimeMon pause: five native mark comparisons, resume cycles and paused scale changes PASS.')
    return result
