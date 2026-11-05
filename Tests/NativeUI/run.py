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
from PIL import Image

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--compositor', default='/usr/NextSpace/bin/nextspace-compositor')
parser.add_argument('--backend')
parser.add_argument('--baseline', type=Path, help='Directory containing the previous legacy shared library')
parser.add_argument('--previous-provider', type=Path, help='Pre-extension NativeUI provider to test ABI compatibility')
parser.add_argument('--previous-client', type=Path, help='Pre-extension native-controls-probe to run unchanged')
parser.add_argument('--previous-loader', type=Path, help='Previous loader directory for the unchanged client/provider-swap check')
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
backend = ['-GSBackend', args.backend] if args.backend else []
with tempfile.TemporaryDirectory(prefix='nextspace-native-ui-') as runtime:
    environment = dict(os.environ, XDG_RUNTIME_DIR=runtime, WLR_BACKENDS='headless', WLR_RENDERER='pixman')
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
    try:
        assert select.select([compositor.stdout], [], [], 10)[0], 'Compositor startup'
        line = compositor.stdout.readline().strip()
        assert line.startswith('WAYLAND_DISPLAY='), line
        environment['WAYLAND_DISPLAY'] = line.split('=', 1)[1]
        def held_probe(binary, arguments, hold, label):
            with (args.output / (label + '.stderr')).open('w') as errors:
                probe = subprocess.Popen([str(binary)] + arguments + backend,
                                         env=dict(environment, **{hold: '1'}), text=True,
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors)
            try:
                assert select.select([probe.stdout], [], [], 15)[0], 'Native host startup'
                first = probe.stdout.readline()
                assert json.loads(first)['event'] == 'host-live', (first, (args.output / (label + '.stderr')).read_text())
                windows = command('windows')
                assert not any(window['buffer_width'] > 0 for window in windows), windows
                probe.stdin.write('\n'); probe.stdin.flush()
                output, _ = probe.communicate(timeout=20)
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
        legacy = subprocess.run([str(args.build / 'native-scroller-probe'), '--track'] + backend,
                                env=environment, text=True, capture_output=True, timeout=15)
        (args.output / 'legacy.stdout').write_text(legacy.stdout)
        (args.output / 'legacy.stderr').write_text(legacy.stderr)
        assert legacy.returncode == 0, (legacy.returncode, legacy.stderr)
        native_tracking = json.loads(legacy.stdout)
        checks = dict(controls=records, legacy_tracking=native_tracking, no_mapped_backing_window=True)
        input_output = held_probe(args.build / 'native-ui/native-input-probe', [str(args.output)],
                                  'NXS_NATIVE_UI_INPUT_HOLD', 'input')
        checks['native_input'] = json.loads(input_output)
        for path in args.output.glob('input-kind-*.argb'):
            Image.frombytes('RGBA', (128, 24), path.read_bytes(), 'raw', 'BGRA').save(path.with_suffix('.png'))
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
        if args.baseline:
            comparisons = []
            def render(arguments, client_env, label):
                child = subprocess.Popen(arguments, env=client_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    stdout, stderr = child.communicate(timeout=10)
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
                    child.kill(); child.communicate()
                    raise AssertionError(f'Probe shutdown timeout; evidence: {evidence}')
                assert child.returncode == 0, (child.returncode, stderr)
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
        if compositor.poll() is None:
            command('quit')
        compositor.wait(timeout=5)
        parent.close()
