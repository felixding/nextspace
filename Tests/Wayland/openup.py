"""Exercise OpenUp's existing extraction, information and modal-panel workflow."""
import io
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import zipfile
from PIL import Image
from gnustep import process_runtime, capture_process_failure
from integration import until, read_json_lines


def decoder_integrity(helper, artifacts):
    """The bundled decoder must preserve forks and reject damaged checksums."""
    artifacts.mkdir()
    fixtures = Path(__file__).parent / 'fixtures/openup'
    payload = (fixtures / 'legacy.txt').read_bytes()
    resource = (fixtures / 'resource.txt').read_bytes()
    cases = []
    for suffix in ('sit', 'pit', 'cpt'):
        original = (fixtures / ('legacy.' + suffix)).read_bytes()
        header_crc = {'sit': 132, 'pit': 96,
                      'cpt': int.from_bytes(original[4:8], 'big')}[suffix]
        data_start = {'sit': 134 + len(resource), 'pit': 98,
                      'cpt': 8 + len(resource)}[suffix]
        for mutation in ('none', 'header-crc', 'data-crc'):
            directory = artifacts / (suffix + '-' + mutation)
            directory.mkdir()
            data = bytearray(original)
            if mutation != 'none':
                data[header_crc if mutation == 'header-crc' else data_start] ^= 1
            archive = directory / ('input.' + suffix)
            archive.write_bytes(data)
            reply = subprocess.run([str(helper), '-3', str(archive.resolve())],
                cwd=directory, capture_output=True, text=True, timeout=10)
            assert (reply.returncode == 0) == (mutation == 'none'), (suffix, mutation, reply.stderr)
            if mutation == 'none':
                assert (directory / 'legacy.txt.data').read_bytes() == payload
                assert (directory / 'legacy.txt.rsrc').read_bytes() == resource
            else:
                assert 'CRC' in reply.stderr, (suffix, mutation, reply.stderr)
            cases.append(dict(format=suffix, mutation=mutation, returncode=reply.returncode,
                              stderr=reply.stderr))
    result = dict(passed=True, helper_sha256=hashlib.sha256(helper.read_bytes()).hexdigest(), cases=cases)
    (artifacts / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def archive_formats(env, command, query, temporary, directory, member, payload, artifacts):
    """Extract the other advertised common formats through the actual application."""
    artifacts.mkdir()
    archives = []
    for suffix in ('zip', 'ZIP', 'tar', 'tgz', 'gz'):
        archive = temporary / ('native archive日本語.' + suffix)
        expected_member = member
        if suffix.lower() == 'zip':
            with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
                bundle.writestr(member, payload)
        elif suffix in ('tar', 'tgz'):
            with tarfile.open(archive, 'w:gz' if suffix == 'tgz' else 'w') as bundle:
                entry = tarfile.TarInfo(member)
                entry.size = len(payload)
                bundle.addfile(entry, io.BytesIO(payload))
        else:
            archive.write_bytes(gzip.compress(payload, mtime=0))
            expected_member = archive.stem
        archives.append((suffix, archive, expected_member, payload, hashlib.sha256(archive.read_bytes()).hexdigest()))
    fixtures = Path(__file__).parent / 'fixtures/openup'
    legacy_payload = (fixtures / 'legacy.txt').read_bytes()
    for suffix, original in (('lha', 'lzh'), ('lzh', 'lzh'), ('arj', 'arj'),
                             ('hqx', 'hqx'), ('bin', 'bin'), ('macbin', 'bin'),
                             ('sit', 'sit'), ('pit', 'pit'), ('cpt', 'cpt')):
        archive = temporary / ('native archive日本語.' + suffix)
        shutil.copyfile(fixtures / ('legacy.' + original), archive)
        expected_member = 'legacy.txt.data' if original in ('hqx', 'bin', 'sit', 'pit', 'cpt') else 'legacy.txt'
        archives.append((suffix, archive, expected_member, legacy_payload, hashlib.sha256(archive.read_bytes()).hexdigest()))
    cases = []
    for density in (120, 150, 180, 210, 240):
        for output in command('outputs'):
            assert command(f"test-scale {output['name']} {density} 10000")['ok']
            assert command('confirm')['ok']
        for suffix, archive, expected_member, expected_payload, digest in archives:
            before = set(directory.glob('*/' + expected_member))
            query('--openup', 'extract', str(archive))
            extracted, = until(lambda: list(set(directory.glob('*/' + expected_member)) - before),
                'OpenUp extracts ' + suffix + ' with Unicode names')
            assert extracted.read_bytes() == expected_payload
            resource_sha256 = None
            if suffix in ('sit', 'pit', 'cpt'):
                resource = extracted.with_suffix('.rsrc').read_bytes()
                assert resource == (fixtures / 'resource.txt').read_bytes()
                resource_sha256 = hashlib.sha256(resource).hexdigest()
            root = directory / extracted.relative_to(directory).parts[0]
            def rendered():
                for window in command('windows'):
                    if window['app_id'] != 'org.nextspace.Workspace' or str(root) not in window['title']:
                        continue
                    size = tuple((window[key] * density + 60) // 120 for key in ('width', 'height'))
                    if window['preferred_scale'] != density or (window['buffer_width'], window['buffer_height']) != size:
                        continue
                    capture = Path(env['NEXTSPACE_WAYLAND_CAPTURE_DIR']) / f"window-{window['client_id']}-{density}.png"
                    try:
                        with Image.open(capture) as image:
                            if image.size != size:
                                continue
                    except OSError:
                        continue
                    return window, capture
                return None
            viewer, capture = until(rendered, 'Extracted ' + suffix + ' opens in native Workspace')
            assert not viewer['legacy']
            shutil.copyfile(capture, artifacts / f'{suffix}-{density}.png')
            assert hashlib.sha256(archive.read_bytes()).hexdigest() == digest
            assert command(f"close {viewer['id']}")['ok']
            until(lambda: not any(w['id'] == viewer['id'] and w['visible'] for w in command('windows')),
                'Format-test viewer closes')
            cases.append(dict(format=suffix, density=density, source_sha256=digest,
                resource_sha256=resource_sha256,
                extracted_sha256=hashlib.sha256(extracted.read_bytes()).hexdigest(),
                expected_sha256=hashlib.sha256(expected_payload).hexdigest(), extracted_bytes=len(expected_payload), member=expected_member, viewer=viewer,
                viewer_closed=True, source_unchanged=True))
            (artifacts / 'results.json').write_text(json.dumps(dict(passed=False, cases=cases), indent=2) + '\n')
    result = dict(passed=True, cases=cases, formats=[v[0] for v in archives],
        extracted_bytes=len(payload), payload_sha256=hashlib.sha256(payload).hexdigest())
    (artifacts / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def drag_archives(probe, env, command, windows, archive, directory, member, payload, artifacts, generic=False, move=False):
    """Drop a real file offer onto OpenUp's application icon across mixed DPI."""
    artifacts.mkdir()
    source_log = artifacts / 'openup-drag.log'
    arguments = [str(Path(probe).with_name('DragProbe')), '-GSBackend', 'libgnustep-wayland',
        '-GSTheme', 'NextSpace', '-NSUseRunningCopy', 'NO', '-GSSuppressAppIcon', 'YES',
        '-DragSource', 'YES', '-DragFile', str(archive), '-GenericDrag', 'YES' if generic else 'NO',
        '-MoveDrag', 'YES' if move else 'NO']
    (artifacts / 'openup-drag-command.json').write_text(json.dumps(arguments, indent=2) + '\n')
    with source_log.open('w') as log, (artifacts / 'openup-drag.stderr').open('w') as errors:
        source = subprocess.Popen(arguments, env=env, stdout=log, stderr=errors)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    records = []
    try:
        def source_window():
            assert source.poll() is None, (artifacts / 'openup-drag.stderr').read_text()
            return next((w for w in command('windows') if w['pid'] == source.pid and
                         w['title'] == 'NativeDragSource'), None)
        window = until(source_window, 'OpenUp file-drag source')
        icon = until(lambda: next((w for w in windows() if w['style'] & 64 and w['visible']), None),
                     'OpenUp application icon in the IconYard')
        target = next(o for o in command('outputs') if o['x'] <= icon['x']+32 < o['x']+o['width'] and
                      o['y'] <= icon['y']+32 < o['y']+o['height'])
        other = next(o for o in command('outputs') if o['name'] != target['name'])
        assert command(f"test-scale {other['name']} 120 10000")['ok'] and command('confirm')['ok']
        for density in (120, 150, 180, 210, 240):
            assert command(f"test-scale {target['name']} {density} 10000")['ok'] and command('confirm')['ok']
            other = next(o for o in command('outputs') if o['name'] == other['name'])
            assert command(f"move {window['id']} {other['x']+400} {other['y']+300}")['ok']
            window = until(lambda: (lambda w: w if w and (w['x'], w['y']) == (other['x']+400, other['y']+300)
                and w['preferred_scale'] == 120 else False)(source_window()), 'File source follows the other output')
            icon = until(lambda: next((w for w in windows() if w['style'] & 64 and w['visible']), None),
                         'OpenUp application icon accepts file drag')
            icon = until(lambda: next((w for w in windows() if w['id'] == icon['id'] and
                w['preferred_scale'] == density and (w['buffer_width'], w['buffer_height']) ==
                tuple((w[k]*density+60)//120 for k in ('width', 'height'))), None), 'OpenUp icon backing density')
            assert not icon['legacy']
            for cancel in ((False,) if move else (True, False)):
                before = set(directory.glob('*/' + member))
                begun = len([v for v in read_json_lines(source_log) if v['event'] == 'drag-begin'])
                ended = len([v for v in read_json_lines(source_log) if v['event'] == 'drag-end'])
                window = source_window()
                assert window and not window['legacy'] and window['preferred_scale'] == 120
                assert command(f"focus {window['id']}")['ok']
                assert command(f"pointer {window['x']+50} {window['y']+100}")['ok']
                assert command('button 272 1')['ok']
                until(lambda: len([v for v in read_json_lines(source_log) if v['event'] == 'drag-begin']) > begun,
                      'OpenUp source begins a real file drag')
                until(lambda: command('drag-state')['active'], 'OpenUp drag transport starts')
                icon = next(w for w in windows() if w['id'] == icon['id'])
                assert command(f"pointer {icon['x']+32} {icon['y']+32}")['ok']
                def accepted():
                    nonlocal icon
                    # Workspace can finish laying out IconYard after the new
                    # scale's buffer arrives. Follow the live drop target.
                    icon = next(w for w in windows() if w['id'] == icon['id'])
                    assert command(f"pointer {icon['x']+32} {icon['y']+32}")['ok']
                    drag = command('drag-state')
                    (artifacts / 'openup-hover-state.json').write_text(json.dumps(dict(
                        scale=density, cancelled=cancel, expected_icon=icon, drag=drag,
                        outputs=command('outputs'), windows=command('windows')), indent=2) + '\n')
                    # Action negotiation and MIME acceptance are separate;
                    # a successful drop requires both.
                    return drag if drag['active'] and drag['target'] == icon['id'] and \
                        drag['action'] == (0 if move else 1) and drag['accepted'] == (not move) else False
                drag = until(accepted, 'OpenUp negotiates the offered file operation')
                if cancel:
                    assert command('key 1 1')['ok'] and command('key 1 0')['ok']
                assert command('button 272 0')['ok']
                until(lambda: not command('drag-state')['active'], 'OpenUp drag finishes')
                endings = until(lambda: (lambda v: v if len(v) > ended else False)(
                    [v for v in read_json_lines(source_log) if v['event'] == 'drag-end']), 'OpenUp source gets completion')
                assert endings[-1]['action'] == (0 if cancel or move else 1), endings[-1]
                viewer = None
                if cancel or move:
                    assert set(directory.glob('*/' + member)) == before, 'Cancelled or rejected drag extracted an archive'
                else:
                    extracted, = until(lambda: list(set(directory.glob('*/' + member)) - before),
                                       'OpenUp extracts the dropped Unicode archive')
                    assert extracted.read_bytes() == payload
                    viewer = until(lambda: next((w for w in command('windows') if
                        w['app_id'] == 'org.nextspace.Workspace' and str(extracted.parents[1]) in w['title']), None),
                        'Dropped archive opens its extracted folder in Workspace')
                    assert not viewer['legacy']
                assert hashlib.sha256(archive.read_bytes()).hexdigest() == digest
                records.append(dict(scale=density, cancelled=cancel, target=icon, source=window,
                    drag=drag, completion=endings[-1], viewer=viewer, source_unchanged=True))
        (artifacts / 'openup-drag-runtime.json').write_text(json.dumps(process_runtime(source.pid), indent=2) + '\n')
    except BaseException:
        capture_process_failure(source, artifacts, 'drag-failure')
        try:
            (artifacts / 'failure-state.json').write_text(json.dumps(dict(
                drag=command('drag-state'), windows=command('windows')), indent=2) + '\n')
        except (OSError, ValueError):
            pass
        raise
    finally:
        command('key 1 1'); command('key 1 0'); command('button 272 0')
        if source.poll() is None:
            source.terminate(); source.wait(timeout=5)
    return dict(cases=records, generic_source=generic, move_only_source=move,
                cancelled_drags=0 if move else 5, completed_archive_drops=0 if move else 5,
                rejected_move_offers=5 if move else 0,
                source_sha256=digest, source_reaped=source.poll() is not None)


def run(executable, probe, env, command, query, processes, artifacts):
    decoder_integrity(Path(executable).resolve().parent / 'Resources/macunpack', artifacts / 'openup-decoder')
    captures = artifacts / "openup-captures"
    captures.mkdir(exist_ok=True)
    temporary = Path(env["XDG_RUNTIME_DIR"]) / "archives"
    temporary.mkdir()
    log_path = artifacts / "openup.log"
    with log_path.open("w") as log:
        process = subprocess.Popen([executable, "-GSBackend", "libgnustep-wayland", "-GSTheme", "NextSpace",
            "-NSUseRunningCopy", "NO", "-GSWorkspaceApplication", "Workspace",
            "-TempFilesDirectory", str(temporary), "-DeleteTempFilesOnQuit", "YES"],
            env=dict(env, NEXTSPACE_WAYLAND_CAPTURE_DIR=str(captures.resolve())), stdout=log, stderr=log)
    processes.append(process)

    def windows():
        assert process.poll() is None, log_path.read_text()[-8000:]
        return [w for w in command("windows") if w["pid"] == process.pid]

    until(lambda: any(w["style"] & 64 for w in windows()), "native OpenUp application icon")
    def ready():
        assert process.poll() is None, log_path.read_text()[-8000:]
        return subprocess.run([probe, "--openup", "state"], env=env, capture_output=True, timeout=15).returncode == 0
    until(ready, "OpenUp finishes application initialization", timeout=30)
    (artifacts / 'openup-runtime.json').write_text(json.dumps(process_runtime(process.pid), indent=2) + '\n')
    state = query("--openup", "info")
    directory = Path(state["directory"])
    assert state["formats"] > 5 and directory.is_dir() and directory.parent == temporary
    info = until(lambda: next((w for w in windows() if w["width"] > 200), None), "OpenUp supported-format panel")
    extent = (info["width"], info["height"])
    measurements = []
    for scale in (120, 180, 240):
        for output in command("outputs"):
            assert command(f"test-scale {output['name']} {scale} 10000")["ok"]
            assert command("confirm")["ok"]
        def rendered():
            window = next((w for w in windows() if w["id"] == info["id"]), None)
            if not window: return None
            assert (window["width"], window["height"]) == extent
            expected = tuple((size * scale + 60) // 120 for size in extent)
            capture = captures / f"window-{window['client_id']}-{scale}.png"
            if (window["buffer_width"], window["buffer_height"]) != expected or not capture.exists(): return None
            with Image.open(capture) as image:
                if image.size != expected or image.convert("RGB").getextrema() == ((0, 0),) * 3: return None
            return window, capture
        window, capture = until(rendered, f"OpenUp native information pixels at {scale}/120")
        shutil.copyfile(capture, artifacts / f"openup-info-{scale}.png")
        measurements.append(dict(scale=scale, logical=extent, buffer=(window["buffer_width"], window["buffer_height"])))

    before = {w["id"] for w in windows()}
    with (artifacts / "openup-panel.stderr").open("w") as errors:
        panel_action = subprocess.Popen([probe, "--openup", "panel", "-GSWorkspaceApplication", "Workspace"],
            env=env, stdout=subprocess.PIPE, stderr=errors, text=True)
        try:
            panel = until(lambda: next((w for w in windows() if w["id"] not in before and w["width"] > 200), None),
                          "OpenUp native archive chooser")
            for output in command("outputs"):
                assert command(f"test-scale {output['name']} 180 10000")["ok"]
                assert command("confirm")["ok"]
            until(lambda: any(w["id"] == panel["id"] and w["preferred_scale"] == 180 for w in windows()),
                  "OpenUp modal panel follows scale change")
            assert command(f"focus {panel['id']}")["ok"]
            # The existing NXTOpenPanel places Cancel beside OK in the footer.
            assert command(f"pointer {panel['x'] + panel['width'] - 123} {panel['y'] + panel['height'] - 28}")["ok"]
            assert command("button 272")["ok"]
            stdout, _ = panel_action.communicate(timeout=10)
            assert panel_action.returncode == 0, stdout
            until(lambda: not any(w["id"] == panel["id"] and w["visible"] for w in windows()), "OpenUp archive chooser cancels")
        finally:
            if panel_action.poll() is None: panel_action.kill(); panel_action.wait(timeout=5)
            panel_action.stdout.close()

    archive = temporary / "native archive日本語.tar.gz"
    payload = ("OpenUp native extraction: 日本語\n" * 3000).encode()
    member = "folder with spaces/日本語.txt"
    with tarfile.open(archive, "w:gz") as bundle:
        entry = tarfile.TarInfo(member)
        entry.size = len(payload)
        bundle.addfile(entry, io.BytesIO(payload))
    query("--openup", "extract", str(archive))
    extracted = until(lambda: next(directory.glob("*/" + member), None), "OpenUp extracts Unicode archive member")
    assert extracted.read_bytes() == payload
    root = extracted.parents[1]
    viewer = until(lambda: next((w for w in command("windows") if w["app_id"] == "org.nextspace.Workspace" and
                                str(root) in w["title"]), None), "OpenUp opens the extracted folder in Workspace")
    formats = archive_formats(env, command, query, temporary, directory, member, payload,
        artifacts / 'openup-formats')
    drags = {name: drag_archives(probe, env, command, windows, archive, directory, member, payload,
                               artifacts / ('openup-' + name + '-drag'), generic, move)
             for name, generic, move in (('copy', False, False), ('generic', True, False), ('move-only', False, True))}
    query("--openup", "info")
    assert command(f"focus {info['id']}")["ok"]
    for code, pressed in ((56, 1), (16, 1), (16, 0), (56, 0)):
        assert command(f"key {code} {pressed}")["ok"]
    process.wait(timeout=10)
    assert process.returncode == 0 and not directory.exists(), "OpenUp normal quit did not clean its temporary directory"
    until(lambda: not any(w["pid"] == process.pid for w in command("windows")), "OpenUp surfaces close")
    processes.remove(process)
    for output in command("outputs"):
        assert command(f"test-scale {output['name']} 120 10000")["ok"]
        assert command("confirm")["ok"]
    (artifacts / "openup-results.json").write_text(json.dumps(dict(densities=measurements,
        archive_bytes=len(payload), member=member, viewer=viewer["title"], drags=drags, formats=formats,
        normal_quit_cleanup=True), indent=2) + "\n")
    print("OpenUp native common/legacy archive extraction, 25 file drags, Workspace handoff, modal chooser and density changes: PASS")
