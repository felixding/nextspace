#!/usr/bin/env python3
"""Run native-provider controls and legacy ABI regression probes on private Wayland."""
import argparse
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import tempfile
import time
import sys
import uuid
from contextlib import ExitStack
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Wayland'))
from gnustep import pasteboard_storage
from PIL import Image

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--compositor', default='/usr/NextSpace/bin/nextspace-compositor')
parser.add_argument('--backend')
parser.add_argument('--pasteboard-server',type=Path,default=Path('/Library/bin/gpbs-wayland'))
parser.add_argument('--baseline', type=Path, help='Directory containing the previous legacy shared library')
parser.add_argument('--previous-provider', type=Path, help='Pre-extension NativeUI provider to test ABI compatibility')
parser.add_argument('--previous-client', type=Path, help='Pre-extension native-controls-probe to run unchanged')
parser.add_argument('--previous-loader', type=Path, help='Previous loader directory for the unchanged client/provider-swap check')
parser.add_argument('--previous-event-provider', type=Path, help='Provider predating optional event dispatch')
parser.add_argument('--previous-range-provider', type=Path, help='Provider predating optional slider step configuration')
parser.add_argument('--previous-popup-provider', type=Path, help='Provider predating optional popup/menu configuration')
parser.add_argument('--previous-popup-open-provider',type=Path,help='Popup provider predating optional explicit open/close')
parser.add_argument('--previous-text-provider',type=Path,help='Provider predating optional native text editing')
parser.add_argument('--previous-text-filter-provider',type=Path,help='Text provider predating optional pre-edit filter')
parser.add_argument('--previous-text-client',type=Path,help='Unchanged text probe from before the pre-edit extension')
parser.add_argument('--previous-text-command-provider',type=Path,help='Provider predating optional native command reporting')
parser.add_argument('--previous-pointer-provider',type=Path,help='Provider predating optional native click-count metadata')
parser.add_argument('--previous-input-client',type=Path,help='Unchanged earlier focus/keyboard client')
parser.add_argument('--transport',action='store_true',help='Exercise the native provider through the browser IPC helper')
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
backend = ['-GSBackend', args.backend] if args.backend else []
with tempfile.TemporaryDirectory(prefix='nextspace-native-ui-') as runtime:
    environment = dict(os.environ, XDG_RUNTIME_DIR=runtime, WLR_BACKENDS='headless', WLR_RENDERER='pixman',
                       NEXTSPACE_SESSION_ID='native-ui-'+uuid.uuid4().hex)
    for name in ('DISPLAY', 'WAYLAND_DISPLAY', 'WAYLAND_SOCKET', 'LD_PRELOAD', 'NEXTSPACE_NATIVE_UI_PROVIDER'):
        environment.pop(name, None)
    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    parent.settimeout(5)
    with (args.output / 'compositor.log').open('w') as errors:
        compositor = subprocess.Popen([args.compositor, '-c', str(child.fileno())], pass_fds=[child.fileno()],
                                      env=environment, stdout=subprocess.PIPE, stderr=errors, text=True)
    child.close()
    def command(text):
        parent.sendall(text.encode())
        return json.loads(parent.recv(65536))
    services=ExitStack()
    try:
        assert select.select([compositor.stdout], [], [], 10)[0], 'Compositor startup'
        line = compositor.stdout.readline().strip()
        assert line.startswith('WAYLAND_DISPLAY='), line
        environment['WAYLAND_DISPLAY'] = line.split('=', 1)[1]
        services.enter_context(pasteboard_storage(args.pasteboard_server,
            args.build/'native-ui/native-pasteboard-probe',environment,args.output))
        def bounded_probe(arguments, client_env, label, timeout=10):
            # Wait for this probe's exit, independently of pipe descriptors a
            # native service could inherit. Preserve output in regular files.
            with tempfile.TemporaryFile(mode='w+') as out, tempfile.TemporaryFile(mode='w+') as err:
                child = subprocess.Popen(arguments, env=client_env, stdout=out, stderr=err, text=True)
                try:
                    child.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    evidence = args.output / (label + '-timeout.txt')
                    with evidence.open('w') as trace:
                        trace.write(f'live probe pid={child.pid} arguments={arguments!r}\n')
                        trace.flush()
                        try:
                            subprocess.run(['sudo', '-n', 'gdb', '-q', '-batch', '-ex', 'thread apply all bt', '-p', str(child.pid)],
                                           stdout=trace, stderr=trace, timeout=8)
                        except subprocess.TimeoutExpired:
                            trace.write('Backtrace collection timed out\n')
                    child.kill(); child.wait()
                    raise AssertionError(f'Probe timeout; evidence: {evidence}')
                out.seek(0); err.seek(0)
                return child.returncode, out.read(), err.read()
        def held_probe(binary, arguments, hold, label):
            with (args.output / (label + '.stderr')).open('w') as errors:
                probe = subprocess.Popen([str(binary)] + arguments + backend,
                                         env=dict(environment, **{hold: '1'}), text=True,
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors)
            try:
                assert select.select([probe.stdout], [], [], 15)[0], 'Native host startup'
                first = probe.stdout.readline()
                assert first,(label,(args.output/(label+'.stderr')).read_text())
                assert json.loads(first)['event'] == 'host-live', (first, (args.output / (label + '.stderr')).read_text())
                windows = command('windows')
                assert not any(window['buffer_width'] > 0 for window in windows), windows
                probe.stdin.write('\n'); probe.stdin.flush()
                if label == 'animation':
                    assert select.select([probe.stdout], [], [], 10)[0], 'Native animation startup'
                    animated = probe.stdout.readline()
                    assert json.loads(animated)['event'] == 'animation-live', animated
                    windows = command('windows')
                    assert not any(window['buffer_width'] > 0 for window in windows), windows
                    probe.stdin.write('\n'); probe.stdin.flush()
                if label.startswith('popup'):
                    for stage, visible in [('popup-live',True),('popup-closed',False)]:
                        assert select.select([probe.stdout],[],[],10)[0], 'Native popup stage'
                        record=probe.stdout.readline();assert json.loads(record)['event']==stage,record
                        deadline=time.monotonic()+2
                        while True:
                            windows=command('windows')
                            shown=[w for w in windows if w.get('visible') and w['buffer_width']>0]
                            if len(shown)==int(visible):break
                            assert probe.poll() is None and time.monotonic()<deadline,windows
                            time.sleep(.01)
                        (args.output/(label+'-'+stage+'-windows.json')).write_text(json.dumps(windows,indent=2)+'\n')
                        probe.stdin.write('\n');probe.stdin.flush()
                try:
                    probe.stdin.close()
                    probe.wait(timeout=20)
                    os.set_blocking(probe.stdout.fileno(), False)
                    output = probe.stdout.read() or ''
                except subprocess.TimeoutExpired:
                    evidence=args.output/(label+'-timeout.txt')
                    with evidence.open('w') as trace:
                        trace.write(f'live probe pid={probe.pid}\n');trace.flush()
                        try:subprocess.run(['sudo','-n','gdb','-q','-batch','-ex','thread apply all bt','-p',str(probe.pid)],stdout=trace,stderr=trace,timeout=8)
                        except subprocess.TimeoutExpired:trace.write('Backtrace collection timed out\n')
                    probe.kill();probe.wait()
                    os.set_blocking(probe.stdout.fileno(),False)
                    output=probe.stdout.read() or ''
                    (args.output/(label+'.stdout')).write_text(output)
                    raise AssertionError(f'Native probe timeout; evidence: {evidence}')
                (args.output / (label + '.stdout')).write_text(output)
                assert probe.returncode == 0, (probe.returncode, (args.output / (label + '.stderr')).read_text())
                return output
            finally:
                if probe.poll() is None:
                    probe.kill(); probe.wait()
        output = held_probe(args.build / 'native-ui/native-controls-probe', [str(args.output)],
                            'NXS_NATIVE_UI_PROBE_HOLD', 'controls')
        records = [json.loads(line) for line in output.splitlines() if line.startswith('{')]
        assert len(records) == 5, records
        for path in args.output.glob('kind-*.argb'):
            scale = 1.5 if path.stem.endswith('-150') else 1
            image = Image.frombytes('RGBA', (round(128 * scale), round(24 * scale)), path.read_bytes(), 'raw', 'BGRA')
            image.save(path.with_suffix('.png'))
        code, stdout, stderr = bounded_probe([str(args.build / 'native-scroller-probe'), '--track'] + backend,
                                            environment, 'legacy-tracking', timeout=15)
        legacy = subprocess.CompletedProcess([],code,stdout,stderr)
        (args.output / 'legacy.stdout').write_text(legacy.stdout)
        (args.output / 'legacy.stderr').write_text(legacy.stderr)
        assert legacy.returncode == 0, (legacy.returncode, legacy.stderr)
        native_tracking = json.loads(legacy.stdout)
        checks = dict(controls=records, legacy_tracking=native_tracking, no_mapped_backing_window=True)
        input_output = held_probe(args.build / 'native-ui/native-input-probe', [str(args.output)],
                                  'NXS_NATIVE_UI_INPUT_HOLD', 'input')
        checks['native_input'] = json.loads(input_output)
        code,stdout,stderr=bounded_probe([str(args.build/'native-ui/native-mouse-probe')]+backend,
            environment,'mouse',timeout=15)
        assert code==0,(code,stderr);checks['native_mouse']=json.loads(stdout)
        if args.previous_pointer_provider:
            code,stdout,stderr=bounded_probe([str(args.build/'native-ui/native-mouse-probe'),'--expect-no-clicks']+backend,
                dict(environment,NEXTSPACE_NATIVE_UI_PROVIDER=str(args.previous_pointer_provider.resolve())),
                'previous-pointer-provider',timeout=15)
            assert code==0,(code,stderr);checks['previous_pointer_provider']=json.loads(stdout)
        if args.previous_input_client:
            code,stdout,stderr=bounded_probe([str(args.previous_input_client.resolve())]+backend,
                environment,'previous-input-client',timeout=15)
            assert code==0,(code,stderr);checks['previous_input_client']=json.loads(stdout)
        text_output=held_probe(args.build/'native-ui/native-text-probe',[str(args.output)],
                                'NXS_NATIVE_UI_TEXT_HOLD','text')
        checks['native_text']=json.loads(text_output)
        if args.previous_text_client:
            old_env=dict(environment,NEXTSPACE_NATIVE_UI_PROVIDER=str((args.build/'native-ui/libnextspace-native-ui-gnustep.so.1').resolve()))
            if args.previous_loader:old_env['LD_LIBRARY_PATH']=str(args.previous_loader.resolve())
            old_output=args.output/'previous-text-client';old_output.mkdir(exist_ok=True)
            code,stdout,stderr=bounded_probe([str(args.previous_text_client.resolve()),str(old_output)]+backend,
                old_env,'previous-text-client',timeout=20)
            assert code==0,(code,stderr)
            checks['previous_text_client_with_new_provider']=json.loads(stdout)
        code,stdout,stderr=bounded_probe([str(args.build/'native-ui/native-text-filter-probe')]+backend,
            environment,'text-filter',timeout=15)
        (args.output/'text-filter.stdout').write_text(stdout);(args.output/'text-filter.stderr').write_text(stderr)
        assert code==0,(code,stderr)
        checks['native_text_filter']=json.loads(stdout)
        if args.previous_text_command_provider:
            code,stdout,stderr=bounded_probe([str(args.build/'native-ui/native-text-filter-probe'),'--expect-no-command']+backend,
                dict(environment,NEXTSPACE_NATIVE_UI_PROVIDER=str(args.previous_text_command_provider.resolve())),
                'previous-text-command-provider')
            assert code==0,(code,stderr)
            checks['previous_provider_accepted_without_command_reporting']=json.loads(stdout)
        if args.previous_text_filter_provider:
            previous=subprocess.run([str(args.build/'native-ui/native-text-filter-probe'),'--expect-no-filter']+backend,
                env=dict(environment,NEXTSPACE_NATIVE_UI_PROVIDER=str(args.previous_text_filter_provider.resolve())),text=True,capture_output=True,timeout=10)
            assert previous.returncode==0,(previous.returncode,previous.stderr)
            checks['previous_text_provider_accepted_without_filter']=json.loads(previous.stdout)
        if args.previous_text_provider:
            previous=subprocess.run([str(args.build/'native-ui/native-text-probe'),'--expect-no-text']+backend,
                env=dict(environment,NEXTSPACE_NATIVE_UI_PROVIDER=str(args.previous_text_provider.resolve())),text=True,capture_output=True,timeout=10)
            assert previous.returncode==0,(previous.returncode,previous.stderr)
            checks['previous_provider_accepted_without_text_extension']=json.loads(previous.stdout)
        for path in args.output.glob('text-*.argb'):
            Image.frombytes('RGBA',(180,24),path.read_bytes(),'raw','BGRA').save(path.with_suffix('.png'))
        range_result=subprocess.run([str(args.build/'native-ui/native-range-probe')]+backend,
            env=environment,text=True,capture_output=True,timeout=10)
        assert range_result.returncode==0,(range_result.returncode,range_result.stderr)
        checks['native_range']=json.loads(range_result.stdout)
        popup_output=held_probe(args.build/'native-ui/native-popup-probe',[str(args.output)],
                                'NXS_NATIVE_UI_POPUP_HOLD','popup')
        checks['native_popup']=json.loads(popup_output)
        if args.previous_popup_open_provider:
            previous=subprocess.run([str(args.build/'native-ui/native-popup-probe'),'--expect-no-popup-open']+backend,
                env=dict(environment,NEXTSPACE_NATIVE_UI_PROVIDER=str(args.previous_popup_open_provider.resolve())),text=True,capture_output=True,timeout=10)
            assert previous.returncode==0,(previous.returncode,previous.stderr)
            checks['previous_popup_provider_accepted_without_explicit_open']=json.loads(previous.stdout)
        for path in args.output.glob('popup-*.argb'):
            scale=1.5 if path.stem.endswith('-150') else 1
            Image.frombytes('RGBA',(round(180*scale),round(24*scale)),path.read_bytes(),'raw','BGRA').save(path.with_suffix('.png'))
        if args.previous_popup_provider:
            previous=subprocess.run([str(args.build/'native-ui/native-popup-probe'),'--expect-no-popup']+backend,
                env=dict(environment,NEXTSPACE_NATIVE_UI_PROVIDER=str(args.previous_popup_provider.resolve())),text=True,capture_output=True,timeout=10)
            assert previous.returncode==0,(previous.returncode,previous.stderr)
            checks['previous_provider_accepted_without_popup_extension']=json.loads(previous.stdout)
        if args.previous_range_provider:
            previous=subprocess.run([str(args.build/'native-ui/native-range-probe'),'--expect-no-step']+backend,
                env=dict(environment,NEXTSPACE_NATIVE_UI_PROVIDER=str(args.previous_range_provider.resolve())),text=True,capture_output=True,timeout=10)
            assert previous.returncode==0,(previous.returncode,previous.stderr)
            checks['previous_provider_accepted_without_range_extension']=json.loads(previous.stdout)
        for path in args.output.glob('input-kind-*.argb'):
            Image.frombytes('RGBA', (128, 24), path.read_bytes(), 'raw', 'BGRA').save(path.with_suffix('.png'))
        animation_output = held_probe(args.build / 'native-ui/native-animation-probe', [str(args.output)],
                                      'NXS_NATIVE_UI_ANIMATION_HOLD', 'animation')
        checks['native_animation'] = json.loads(animation_output)
        for path in args.output.glob('animation-*.argb'):
            Image.frombytes('RGBA', (128,24), path.read_bytes(), 'raw', 'BGRA').save(path.with_suffix('.png'))
        if args.previous_event_provider:
            previous = subprocess.run([str(args.build / 'native-ui/native-animation-probe'), '--expect-no-events'] + backend,
                env=dict(environment, NEXTSPACE_NATIVE_UI_PROVIDER=str(args.previous_event_provider.resolve())),
                text=True, capture_output=True, timeout=10)
            assert previous.returncode == 0, (previous.returncode, previous.stderr)
            checks['previous_provider_accepted_without_event_extension'] = json.loads(previous.stdout)
        if args.previous_provider:
            previous = subprocess.run([str(args.build / 'native-ui/native-input-probe'), '--expect-no-input'] + backend,
                env=dict(environment, NEXTSPACE_NATIVE_UI_PROVIDER=str(args.previous_provider.resolve())),
                text=True, capture_output=True, timeout=10)
            assert previous.returncode == 0, (previous.returncode, previous.stderr)
            checks['previous_provider_accepted_without_input_extension'] = json.loads(previous.stdout)
        if args.previous_client:
            destination = args.output / 'previous-client'
            destination.mkdir(exist_ok=True)
            previous = subprocess.run([str(args.previous_client.resolve()), str(destination)] + backend,
                env=dict(environment, LD_LIBRARY_PATH=str((args.build / 'native-ui').resolve())),
                text=True, capture_output=True, timeout=20)
            assert previous.returncode == 0, (previous.returncode, previous.stderr)
            assert len([line for line in previous.stdout.splitlines() if line.startswith('{')]) == 5
            checks['previous_client_unchanged_with_new_provider'] = True
            if args.previous_loader:
                previous = subprocess.run([str(args.previous_client.resolve()), str(destination)] + backend,
                    env=dict(environment, LD_LIBRARY_PATH=str(args.previous_loader.resolve()),
                             NEXTSPACE_NATIVE_UI_PROVIDER=str((args.build / 'native-ui/libnextspace-native-ui-gnustep.so.1').resolve())),
                    text=True, capture_output=True, timeout=20)
                assert previous.returncode == 0, (previous.returncode, previous.stderr)
                assert len([line for line in previous.stdout.splitlines() if line.startswith('{')]) == 5
                checks['previous_loader_and_client_unchanged_with_new_provider'] = True
        # Load the same clients through an independently selected provider.
        sources = Path(__file__).resolve().parent
        headers = sources.parents[1] / 'Libraries/NativeUI'
        relay = (args.output / 'provider-relay.so').resolve()
        bad = (args.output / 'provider-bad.so').resolve()
        for library, options in [(relay, []), (bad, ['-DTEST_BAD_ABI'])]:
            subprocess.run(['cc', '-shared', '-fPIC', '-I' + str(headers), str(sources / 'provider-relay.c'),
                            '-o', str(library), '-ldl'] + options, check=True)
        provider_env = dict(environment, NEXTSPACE_NATIVE_UI_PROVIDER=str(relay),
                            NXS_TEST_REAL_PROVIDER=str((args.build / 'native-ui/libnextspace-native-ui-gnustep.so.1').resolve()))
        selected = subprocess.run([str(args.build / 'native-scroller-probe'), '--track'] + backend,
                                  env=provider_env, text=True, capture_output=True, timeout=15)
        assert selected.returncode == 0 and 'native-ui-test-provider-selected' in selected.stderr, selected.stderr
        assert json.loads(selected.stdout) == native_tracking
        checks['alternate_provider_same_client_and_native_behavior'] = True
        rejected = subprocess.run([str(args.build / 'native-ui/native-controls-probe'), str(args.output)] + backend,
                                  env=dict(environment, NEXTSPACE_NATIVE_UI_PROVIDER=str(bad)), text=True, capture_output=True, timeout=10)
        assert rejected.returncode == 1 and 'Unsupported native UI provider ABI' in rejected.stderr, rejected.stderr
        checks['wrong_provider_abi_rejected'] = True
        dependencies = subprocess.check_output(['readelf', '-d', str(args.build / 'native-ui/libnextspace-native-ui.so')], text=True)
        assert 'gnustep' not in dependencies and 'libobjc' not in dependencies
        checks['loader_has_no_ui_toolkit_dependency'] = True
        exports = subprocess.check_output(['readelf', '--dyn-syms', '--wide', str(args.build / 'native-ui/libnextspace-native-ui-gnustep.so')], text=True)
        assert 'nxs_native_ui_provider' in exports and 'nxs_gnustep_' not in exports
        checks['provider_internals_not_exported'] = True
        if args.transport:
            scripts=Path(__file__).resolve().parents[2]/'Experiments/ChromiumScrollers'
            endpoint=Path(runtime)/'native-controls.sock'
            with (args.output/'helper.jsonl').open('w') as out,(args.output/'helper.stderr').open('w') as err:
                helper=subprocess.Popen([sys.executable,str(scripts/'helper.py'),'--library',str((args.build/'libnextspace-native-scroller.so.1').resolve()),
                    '--socket',str(endpoint)]+backend,env=environment,stdout=out,stderr=err)
            try:
                deadline=time.monotonic()+30
                while not endpoint.exists():
                    assert helper.poll() is None and time.monotonic()<deadline,'Native helper startup'
                    time.sleep(.01)
                for name in ['transport','input','animation','notifications']:
                    output=args.output/('transport-'+name)
                    if name=='input':output=output.with_suffix('.json')
                    extra=['--helper-pid',str(helper.pid)] if name=='notifications' else []
                    probe=subprocess.run([sys.executable,str(scripts/('check-control-'+name+'.py')),'--socket',str(endpoint),'--output',str(output)]+extra,
                        env=environment,text=True,capture_output=True,timeout=20)
                    (args.output/('transport-'+name+'.stdout')).write_text(probe.stdout)
                    assert probe.returncode==0,(name,probe.stdout,probe.stderr)
                    checks['transport_'+name]=json.loads(probe.stdout)
                output=args.output/'transport-popup'
                popup=held_probe(Path(sys.executable),[str(scripts/'check-control-popup.py'),'--socket',str(endpoint),
                    '--output',str(output),'--references',str(args.output),'--helper-pid',str(helper.pid)],'NXS_NATIVE_UI_POPUP_HOLD','popup-transport')
                checks['transport_popup']=json.loads(popup)
                text=held_probe(Path(sys.executable),[str(scripts/'check-control-text.py'),'--socket',str(endpoint),
                    '--output',str(args.output/'transport-text'),'--references',str(args.output)],
                    'NXS_NATIVE_UI_TEXT_HOLD','text-transport')
                checks['transport_text']=json.loads(text)
                filter_probe=subprocess.run([str(args.build/'native-ui/native-text-transport-probe'),str(endpoint),str(helper.pid)],
                    env=environment,text=True,capture_output=True,timeout=20)
                (args.output/'transport-text-filter.stdout').write_text(filter_probe.stdout)
                (args.output/'transport-text-filter.stderr').write_text(filter_probe.stderr)
                assert filter_probe.returncode==0,(filter_probe.returncode,filter_probe.stderr)
                checks['transport_text_filter']=json.loads(filter_probe.stdout)
            finally:
                if sys.exc_info()[0] is not None and helper.poll() is None:
                    with (args.output/'helper-timeout.txt').open('w') as trace:
                        try:subprocess.run(['sudo','-n','gdb','-q','-batch','-ex','thread apply all bt','-p',str(helper.pid)],stdout=trace,stderr=trace,timeout=8)
                        except subprocess.TimeoutExpired:trace.write('Backtrace collection timed out\n')
                helper.terminate()
                try:helper.wait(timeout=5)
                except subprocess.TimeoutExpired:helper.kill();helper.wait()
        if args.baseline:
            comparisons = []
            def render(arguments, client_env, label):
                code, stdout, stderr = bounded_probe(arguments, client_env, label)
                assert code == 0, (code, stderr)
                return json.loads(stdout)
            for horizontal in (False, True):
                for scale in (1, 1.25, 1.5, 1.75, 2):
                    for state, total, page, value in [('normal', 1000, 200, 300), ('disabled', 200, 200, 0), ('fitting', 100, 200, 0)]:
                        name = f'{"horizontal" if horizontal else "vertical"}-{state}-{scale}'
                        binaries = []
                        for label, client_env in [('baseline', dict(environment, LD_LIBRARY_PATH=str(args.baseline))), ('provider', environment)]:
                            destination = (args.output / (name + '-' + label + '.argb')).resolve()
                            dimensions = render([str(args.build / 'native-scroller-probe'),
                                '--render-horizontal' if horizontal else '--render', '240', str(total), str(page), str(value), str(scale), str(destination)] + backend,
                                client_env, name + '-' + label)
                            binaries.append((dimensions, destination.read_bytes()))
                        assert binaries[0] == binaries[1], name
                        comparisons.append(name)
            checks['unchanged_legacy_pixels'] = comparisons
        (args.output / 'results.json').write_text(json.dumps(checks, indent=2) + '\n')
        print(json.dumps(checks))
    finally:
        try:services.close()
        finally:
            if compositor.poll() is None:
                command('quit')
            compositor.wait(timeout=5)
            parent.close()
