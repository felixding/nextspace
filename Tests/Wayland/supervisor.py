#!/usr/bin/env python3
"""Exercise the real C supervisor, shell recovery and owned-child cleanup."""
import argparse
import json
import os
from pathlib import Path
import select
import signal
import shlex
import subprocess
import tempfile
import hashlib
import time
from urllib.parse import unquote
from integration import until


def run(supervisor, compositor, shell_probe, client, artifacts, xwayland=False, compositor_loss=False, input_method_probe=None,
        private_bus=False, bus_loss=False, launcher=None, capture_probe=None):
    assert not bus_loss or private_bus, 'Bus-loss checks require --private-bus'
    artifacts.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nextspace-supervisor-%, " if private_bus else "nextspace-supervisor-") as runtime:
        env = dict(os.environ, XDG_RUNTIME_DIR=runtime, WLR_BACKENDS="headless",
                   WLR_HEADLESS_OUTPUTS="2", WLR_RENDERER="pixman", GDK_BACKEND="wayland",
                   NEXTSPACE_SESSION_ID="invalid/inherited", WAYLAND_SOCKET="999999",
                   NEXTSPACE_SHELL_SOCKET="999999", DISPLAY=":999999")
        if private_bus:
            from session_activation import prepare
            env.update(prepare(artifacts))
            env.update(DBUS_SESSION_BUS_ADDRESS='unix:path=/nonexistent-inherited-bus', XAUTHORITY='/nonexistent-inherited-authority')
        if launcher:
            assert private_bus, 'The native user launcher owns a private bus'
            env['PATH'] = str(Path(supervisor).resolve().parent) + os.pathsep + env['PATH']
            env['GREETD_SOCK'] = '/nonexistent-inherited-greeter-socket'
        marker = artifacts / "inherited-marker"
        marker.write_text("Must not reach compositor or shell\n")
        marker_fd = os.open(marker, os.O_RDONLY)
        method_arguments = []
        method_log = artifacts.resolve() / "input-method.jsonl"
        if input_method_probe:
            wrapper = Path(runtime) / "input-method"
            wrapper.write_text("#!/bin/sh\nexec " + shlex.quote(input_method_probe) +
                               " --input-method-daemon >> " + shlex.quote(str(method_log)) + "\n")
            wrapper.chmod(0o700)
            method_arguments = ["--input-method", str(wrapper)]
        capture_log = artifacts.resolve() / 'capture.jsonl'
        if capture_probe:
            wrapper = Path(runtime) / 'capture-backend'
            wrapper.write_text('#!/bin/sh\nexec ' + shlex.quote(capture_probe) +
                ' --daemon >> ' + shlex.quote(str(capture_log)) + '\n')
            wrapper.chmod(0o700)
            method_arguments += ['--capture-backend', str(wrapper)]
        with (artifacts / "session.log").open("w") as log:
            started = time.time()
            session = subprocess.Popen([launcher or supervisor, "--compositor", compositor,
                *(["--xwayland"] if xwayland else []), *(["--private-bus"] if private_bus and not launcher else []), *method_arguments, "--", shell_probe],
                env=env, pass_fds=[marker_fd], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log)
        os.close(marker_fd)
        os.set_blocking(session.stdout.fileno(), False)
        pending = b""
        events, environment = [], {}
        activated_pid = None

        def pump():
            nonlocal pending
            while select.select([session.stdout], [], [], 0)[0]:
                chunk = os.read(session.stdout.fileno(), 65536)
                if not chunk: break
                pending += chunk
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    line = line.decode()
                    if line.startswith("{"):
                        events.append(json.loads(line))
                        (artifacts / "events.json").write_text(json.dumps(events, indent=2) + "\n")
                    elif "=" in line:
                        key, value = line.split("=", 1); environment[key] = value
            return events

        def wait(predicate, description):
            def check():
                pump()
                assert session.poll() is None, (artifacts / "session.log").read_text()[-6000:]
                return predicate()
            return until(check, description, timeout=15)

        def send(command):
            session.stdin.write((command + "\n").encode()); session.stdin.flush()

        def children():
            return [int(pid) for pid in Path(f"/proc/{session.pid}/task/{session.pid}/children").read_text().split()]

        def executable(pid):
            try: return Path(f"/proc/{pid}/exe").resolve()
            except FileNotFoundError: return None

        def mapping(pid):
            libraries = sorted({line.split()[-1] for line in Path(f'/proc/{pid}/maps').read_text().splitlines()
                if any(name in line for name in ('libgnustep-base.so.', 'libgnustep-gui.so.', 'libgnustep-wayland-',
                                                'libobjc.so.', 'libwlroots-', 'libgio-2.0.so.'))})
            return dict(pid=pid, executable=str(executable(pid)), libraries=libraries)

        try:
            wait(lambda: any(e["event"] == "ready" for e in events), "session shell readiness")
            assert next(e for e in events if e["event"] == "ready")["restore_settings"]
            assert environment["NEXTSPACE_SESSION_ID"].startswith("wayland-")
            assert environment["NEXTSPACE_SESSION_ID"] != env["NEXTSPACE_SESSION_ID"]
            if xwayland: assert environment["DISPLAY"].startswith(":") and environment["DISPLAY"] != env["DISPLAY"]
            else: assert "DISPLAY" not in environment
            server_pid = next(pid for pid in children() if executable(pid) == Path(compositor))
            old_shell = next(pid for pid in children() if executable(pid) == Path(shell_probe))
            runtime_maps = dict(shell_initial=mapping(old_shell), compositor=mapping(server_pid))
            if private_bus:
                from session_activation import check
                activated_pid = check(environment, artifacts, xwayland, marker, runtime)
                runtime_maps['activated_service'] = mapping(activated_pid)
            for pid in (server_pid, old_shell):
                targets = [p.resolve() for p in Path(f"/proc/{pid}/fd").iterdir()]
                assert marker.resolve() not in targets
            send("launch " + client)
            wait(lambda: any(e["event"] == "launched" for e in events), "session-owned GTK launch")
            client_pid = next(e["pid"] for e in events if e["event"] == "launched")
            wait(lambda: any(e["event"] == "windows" and any(w["pid"] == client_pid for w in e["windows"])
                             for e in events), "session-owned native client mapped")
            send("snapshot")
            state = wait(lambda: next((e["windows"] for e in reversed(events)
                                      if e["event"] == "windows" and e["windows"]), None), "shell snapshot")
            before_ready = sum(e["event"] == "ready" for e in events)
            os.kill(old_shell, signal.SIGKILL)
            wait(lambda: sum(e["event"] == "ready" for e in events) > before_ready, "automatic Workspace restart")
            assert not next(e for e in reversed(events) if e["event"] == "ready")["restore_settings"]
            assert Path(f"/proc/{client_pid}").exists()
            recovered = next(e["windows"] for e in reversed(events) if e["event"] == "ready")
            assert recovered == state
            service_pids=[]
            for enabled, label, path in ((input_method_probe,'Input method',method_log),
                                         (capture_probe,'Capture backend',capture_log)):
                if not enabled: continue
                def services():
                    return [json.loads(line) for line in path.read_text().splitlines()
                            if line.startswith('{"event":"ready"')] if path.exists() else []
                wait(lambda: len(services()) == 1, 'authorized '+label)
                for index in range(3):
                    row = services()[-1]
                    if label == 'Capture backend':
                        assert row['manager_visible'] and row['fd_cloexec'] and not row['socket_environment']
                    # Capture probe readiness reports its pid just like the IME.
                    service_pid = row['pid']
                    assert marker.resolve() not in [p.resolve() for p in Path(f'/proc/{service_pid}/fd').iterdir()]
                    os.kill(service_pid, signal.SIGKILL)
                    if index < 2: wait(lambda: len(services()) == index + 2, label+' restart')
                wait(lambda: label+' repeatedly failed' in (artifacts/'session.log').read_text(),
                     'bounded '+label+' restart')
                assert all(not Path(f"/proc/{row['pid']}").exists() for row in services())
                if label == 'Capture backend':
                    wait(lambda:len(services())==4,'capture backend recovers after bounded backoff')
                    assert Path(f"/proc/{services()[-1]['pid']}").exists()
                service_pids += [row['pid'] for row in services()]
                assert Path(f'/proc/{client_pid}').exists()
            send("stubborn")
            wait(lambda: sum(e["event"] == "launched" for e in events) == 2, "uncooperative owned child")
            stubborn_pid = next(e["pid"] for e in reversed(events) if e["event"] == "launched")
            wait(lambda: any(e["event"] == "stubborn-ready" for e in events), "child ignores graceful termination")
            new_shell = next(pid for pid in children() if executable(pid) == Path(shell_probe))
            runtime_maps['shell_recovered'] = mapping(new_shell)
            if bus_loss:
                bus = next(pid for pid in children() if executable(pid) and executable(pid).name == 'dbus-daemon')
                os.kill(bus, signal.SIGKILL)
            elif compositor_loss: os.kill(server_pid, signal.SIGKILL)
            else: send("quit")
            session.wait(timeout=10)
            stopped = time.time()
            pump()
            assert session.returncode == (1 if compositor_loss or bus_loss else 0), (artifacts / "session.log").read_text()
            assert "Forcing remaining session processes" in (artifacts / "session.log").read_text()
            assert all(not Path(f"/proc/{pid}").exists() for pid in (server_pid, client_pid, stubborn_pid, new_shell))
            assert all(not Path(f'/proc/{pid}').exists() for pid in service_pids)
            if activated_pid: assert not Path(f'/proc/{activated_pid}').exists(), 'Activated D-Bus client escaped session cleanup'
            if private_bus:
                socket_path = Path(unquote(environment['DBUS_SESSION_BUS_ADDRESS'].split('unix:path=', 1)[1].split(',', 1)[0]))
                assert not socket_path.exists() and not socket_path.parent.exists(), 'Private bus socket directory escaped cleanup'
            record = dict(environment=environment, recovered=recovered, private_bus=private_bus, bus_loss=bus_loss,
                activated_pid=activated_pid, lifetime=dict(started_unix=started, stopped_unix=stopped),
                supervisor=dict(path=supervisor, sha256=hashlib.sha256(Path(supervisor).read_bytes()).hexdigest()),
                launcher=launcher, runtime=runtime_maps,
                passed=["fresh session environment", "private capability delivery", "inherited descriptors closed",
                        "automatic shell restart preserves native client",
                        "bus loss ends session" if bus_loss else "compositor loss ends session" if compositor_loss else "normal shell exit ends session",
                        "orphan reaping and forced owned-child cleanup"] +
                        (["actual D-Bus activation environment", "uncooperative activated client reaped", "private socket directory removed"] if private_bus else []))
            if private_bus and not xwayland and not compositor_loss and not bus_loss:
                from session_activation import failures
                failures(supervisor, compositor, shell_probe, env, artifacts)
            if not xwayland and not compositor_loss and not bus_loss:
                failures = [
                    ([supervisor, "--compositor", "/bin/false", "--", shell_probe], "compositor-failure"),
                    ([supervisor, "--compositor", compositor, "--", "/bin/false"], "shell-failure"),
                ]
                for arguments, name in failures:
                    failure = subprocess.run(arguments, env=env, capture_output=True, timeout=15)
                    (artifacts / (name + ".log")).write_bytes(failure.stderr)
                    assert failure.returncode == 1, failure.stderr.decode()
                    if name == "shell-failure":
                        assert failure.stderr.count(b"restarting") == 2
                        assert b"Workspace repeatedly failed" in failure.stderr
                unsafe = Path(runtime) / "unsafe"
                unsafe.mkdir(mode=0o755)
                rejected = subprocess.run([supervisor, "--compositor", compositor, "--", shell_probe],
                    env=dict(env, XDG_RUNTIME_DIR=str(unsafe)), capture_output=True, timeout=5)
                assert rejected.returncode == 1 and b"private directory" in rejected.stderr
            (artifacts / "results.json").write_text(json.dumps(record, indent=2) + "\n")
            print("Session environment, shell recovery and owned process cleanup: PASS")
        finally:
            if session.poll() is None:
                session.terminate()
                try: session.wait(timeout=10)
                except subprocess.TimeoutExpired: session.kill(); session.wait(timeout=5)
            for event in events:
                if event["event"] == "stubborn-ready" and executable(event["pid"]) == Path(shell_probe):
                    try: os.kill(event["pid"], signal.SIGKILL)
                    except ProcessLookupError: pass
            session.stdin.close(); session.stdout.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for name in ("supervisor", "compositor", "shell-probe", "client"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--xwayland", action="store_true")
    parser.add_argument("--compositor-loss", action="store_true")
    parser.add_argument("--input-method-probe")
    parser.add_argument("--capture-probe")
    parser.add_argument("--private-bus", action="store_true")
    parser.add_argument("--bus-loss", action="store_true")
    parser.add_argument("--launcher")
    run(**vars(parser.parse_args()))
