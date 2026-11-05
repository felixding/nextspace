#!/usr/bin/env python3
"""Exercise the trusted IME relay with independent protocol clients."""
import argparse
import array
import json
import os
from pathlib import Path
import select
import shlex
import shutil
import socket
import subprocess
import tempfile
from integration import read_json_lines, until


def stop_process(process):
    if process.poll() is None:
        process.terminate()
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait(timeout=5)


class Client:
    def __init__(self, executable, mode, env, artifacts, name, broker=None, broker_role=b"I"):
        self.events, self.pending = [], b""
        self.log = (artifacts / f"{name}.jsonl").open("w")
        connection = None
        if broker:
            server, connection = socket.socketpair()
            broker.sendmsg([broker_role], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [server.fileno()]))])
            server.close()
            env = dict(env, WAYLAND_SOCKET=str(connection.fileno()))
        with (artifacts / f"{name}.stderr").open("w") as errors:
            self.process = subprocess.Popen([executable, *([mode] if mode else [])], env=env,
                pass_fds=[connection.fileno()] if connection else [], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=errors)
        if connection: connection.close()
        os.set_blocking(self.process.stdout.fileno(), False)
        self.wait("ready")

    def pump(self):
        while select.select([self.process.stdout], [], [], 0)[0]:
            data = os.read(self.process.stdout.fileno(), 65536)
            if not data: break
            self.pending += data
            while b"\n" in self.pending:
                line, self.pending = self.pending.split(b"\n", 1)
                self.log.write(line.decode() + "\n"); self.log.flush()
                self.events.append(json.loads(line))

    def wait(self, event, start=0):
        def check():
            self.pump()
            assert self.process.poll() is None, self.process.returncode
            return next((e for e in self.events[start:] if e["event"] == event), None)
        return until(check, f"{event} from protocol client")

    def send(self, command):
        self.process.stdin.write((command + "\n").encode()); self.process.stdin.flush()

    def sync(self):
        self.pump(); start = len(self.events)
        self.send("sync"); self.wait("sync", start)
        return len(self.events)

    def stop(self):
        stop_process(self.process)
        self.pump(); self.log.close()
        self.process.stdin.close(); self.process.stdout.close()


def run_native(executable, method, env, command, artifacts, secure=False, mode=0):
    log_path = artifacts / f"native-{'secure-' if secure else ''}{mode}.log"
    with log_path.open("w") as log:
        process = subprocess.Popen([executable, "-GSBackend", "libgnustep-wayland", "-GSTheme", "NextSpace",
            "-NSUseRunningCopy", "NO", "-TextInputProbe", "YES", "-TextInputRunLoopMode", str(mode),
            "-SecureTextInputProbe", "YES" if secure else "NO"],
            env=env, stdout=log, stderr=log)
    def events():
        assert process.poll() is None, f"Native probe exited {process.returncode}:\n" + log_path.read_text()[-4000:]
        return read_json_lines(log_path, '{"')
    def state(predicate):
        def check():
            states = [e for e in events() if e["event"] == "input-state"]
            return states[-1] if states and predicate(states[-1]) else None
        return until(check, "native text/marked range")
    def send(*commands):
        for value in commands: method.send(value)
        method.send("done"); method.sync()
    def preedit(value, predicate):
        def serial():
            method.pump()
            return next((e['serial'] for e in reversed(method.events) if e['event'] == 'done'), 0)
        sent_serial = serial()
        send(value)
        def check():
            nonlocal sent_serial
            states = [e for e in events() if e['event'] == 'input-state']
            if states and predicate(states[-1]): return states[-1]
            current = serial()
            if current != sent_serial:
                # A concurrent caret/layout update invalidates the method's
                # serial. Rebase this idempotent preedit, never a text commit.
                sent_serial = current
                send(value)
            return None
        try:
            return until(check, 'native preedit at the current input-method serial')
        except AssertionError:
            (artifacts / f'preedit-failure-{secure}-{mode}.json').write_text(json.dumps(dict(
                command=value, base=base, sent_serial=sent_serial, current_serial=serial(),
                states=[e for e in events() if e['event'] == 'input-state'][-5:]), indent=2) + '\n')
            raise
    try:
        field = until(lambda: next((e for e in events() if e["event"] == "text-field"), None), "native field")
        window = until(lambda: next((w for w in command("windows") if w["pid"] == process.pid and
            w["title"] == "WaylandProbe" and w["visible"] and w["width"] > 200), None), "native window")
        assert command(f"raise {window['id']}")["ok"]
        assert command(f"focus {window['id']}")["ok"]
        def field_target():
            current = next(w for w in command("windows") if w["id"] == window["id"])
            x, y = current["x"] + field["start_x"] + 40, current["y"] + current["height"] - field["start_y"]
            hit = command(f"hit {int(x)} {int(y)}")
            (artifacts / "native-target.json").write_text(json.dumps(dict(window=current, x=x, y=y, hit=hit,
                outputs=command("outputs"), windows=command("windows")), indent=2))
            return current if hit["id"] == current["id"] else None
        window = until(field_target, "unobscured native text field")
        start = method.sync()
        assert command(f"pointer {window['x'] + field['start_x'] + 40} {window['y'] + window['height'] - field['start_y']}")["ok"]
        assert command("button 272")["ok"]
        method.wait("activate", start); method.wait("done", start); method.sync()
        if secure:
            assert all(e["hex"] == "" for e in method.events[start:] if e["event"] == "surrounding")
            assert any(e["purpose"] == 8 for e in method.events[start:] if e["event"] == "content")
        # Use field-editor selection; this fixture has no application Edit menu.
        for x, pressed in ((field["start_x"], 1), (field["end_x"], 0)):
            assert command(f"pointer {window['x'] + x} {window['y'] + window['height'] - field['start_y']}")["ok"]
            assert command(f"button 272 {pressed}")["ok"]
        state(lambda s: s["selection"] == len("Selection, keyboard input and text metrics"))
        method.sync()
        send("commit A日本🙂")
        state(lambda s: s["text"] == "A日本🙂" and not s["marked"] and s["cursor"] == 5)
        method.sync()
        if not secure:
            send("delete 4 0", "commit 語")
            state(lambda s: s["text"] == "A日本語" and s["cursor"] == 4)
            method.sync()
            send("delete 1 0")  # A partial UTF-8 character must not delete text.
            state(lambda s: s["text"] == "A日本語" and not s["marked"])
        base = "A日本🙂" if secure else "A日本語"
        for scale in (120, 150, 180, 210, 240):
            for output in command("outputs"):
                assert command(f"test-scale {output['name']} {scale} 10000")["ok"]
                assert command("confirm")["ok"]
            method.sync()
            preedit("preedit 0 6 かな",
                lambda s: s["text"] == base + "かな" and s["marked"] and s["mark_length"] == 2 and s["selection"] == 2)
            method.sync()
            preedit("preedit 3 3 仮名",
                lambda s: s["text"] == base + "仮名" and s["marked"] and s["selection"] == 0)
            method.sync()
            send("commit 字")
            base += "字"
            state(lambda s: s["text"] == base and not s["marked"])
        method.sync()
        if secure:
            assert all(e["hex"] == "" for e in method.events[start:] if e["event"] == "surrounding")
        # Composition is cancelled on focus loss and can restart in the same view.
        preedit("preedit 0 6 消去", lambda s: s["marked"])
        foreign = next(w for w in command("windows") if w["pid"] != process.pid and w["accepts_focus"])
        assert command(f"focus {foreign['id']}")["ok"]
        state(lambda s: not s["marked"] and s["text"] == base)
        start = method.sync()
        assert command(f"focus {window['id']}")["ok"]
        method.wait("activate", start); method.wait("done", start); method.sync()
        send("commit 戻")
        state(lambda s: s["text"] == base + "戻" and not s["marked"])
        print(f"GNUstep {'secure ' if secure else ''}IME preedit, UTF-8 ranges and focus at five densities (mode {mode}): PASS")
    finally:
        stop_process(process)


def run_terminal(executable, query_probe, method, env, command, artifacts):
    directory = artifacts / "terminal"
    directory.mkdir()
    typed, ready = directory.resolve() / "typed", directory.resolve() / "ready"
    script = directory.resolve() / "read-input.sh"
    script.write_text("#!/bin/sh\nstty -echo -icanon min 1 time 0\ntouch " + shlex.quote(str(ready)) +
                      "\nexec cat > " + shlex.quote(str(typed)) + "\n")
    script.chmod(0o700)
    app_env = dict(env, NEXTSPACE_GS_BACKEND="wayland",
                   NEXTSPACE_WAYLAND_CAPTURE_DIR=str(directory.resolve()))
    with (directory / "terminal.log").open("w") as log:
        process = subprocess.Popen([executable, "-Shell", str(script), "-NSUseRunningCopy", "NO", "-GSTheme", "NextSpace"],
                                   env=app_env, stdout=log, stderr=log)
    def state():
        result = subprocess.run([query_probe, "--terminal-input"], env=app_env, capture_output=True, text=True, timeout=10)
        return json.loads(result.stdout) if result.returncode == 0 else None
    try:
        until(ready.exists, "Terminal PTY reader")
        window = until(lambda: next((w for w in command("windows") if w["pid"] == process.pid and w["width"] > 200), None),
                       "Terminal native window")
        assert command(f"focus {window['id']}")["ok"]
        until(state, "Terminal text input client")
        method.sync()
        expected = b""
        for scale in (120, 150, 180, 210, 240):
            for output in command("outputs"):
                assert command(f"test-scale {output['name']} {scale} 10000")["ok"]
                assert command("confirm")["ok"]
            method.sync()
            capture = directory / f"window-{window['client_id']}-{scale}.png"
            previous = capture.stat().st_mtime_ns if capture.exists() else 0
            method.send("preedit 0 6 にほん"); method.send("done"); method.sync()
            until(lambda: (value := state()) and value["preedit"] == "にほん", "Terminal marked overlay")
            value = state()
            (directory / f"preedit-{scale}.json").write_text(json.dumps(value) + "\n")
            assert value["glyphs_covered"], value
            until(lambda: capture.exists() and capture.stat().st_mtime_ns > previous, "Terminal preedit rendered")
            shutil.copyfile(capture, directory / f"preedit-{scale}.png")
            assert typed.read_bytes() == expected, "Preedit leaked into the PTY"
            method.sync(); method.send("commit 日本語"); method.send("done"); method.sync()
            expected += "日本語".encode()
            until(lambda: typed.read_bytes() == expected, "committed Unicode reaches Terminal PTY")
            assert not state()["marked"]
        assert len(expected) == 45
        (directory / "results.json").write_text(json.dumps(dict(bytes=len(expected), scales=[120, 150, 180, 210, 240])) + "\n")
        print("Terminal IME overlay and exact committed PTY bytes at five densities: PASS")
    finally:
        stop_process(process)


def run(compositor, probe, artifacts, native_probe=None, terminal=None, workspace_probe=None,
        pasteboard_server=None, pasteboard_probe=None):
    artifacts.mkdir(parents=True, exist_ok=True)
    clients = []
    with tempfile.TemporaryDirectory(prefix="nextspace-ime-") as runtime:
        env = dict(os.environ, XDG_RUNTIME_DIR=runtime, WLR_BACKENDS="headless",
                   WLR_HEADLESS_OUTPUTS="2", WLR_RENDERER="pixman", NEXTSPACE_SESSION_ID=Path(runtime).name)
        for key in ("DISPLAY", "WAYLAND_DISPLAY", "WAYLAND_SOCKET"): env.pop(key, None)
        control, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        broker, broker_child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        control.settimeout(5)
        with (artifacts / "compositor.log").open("w") as log:
            server = subprocess.Popen([compositor, "-c", str(child.fileno()), "-S", str(broker_child.fileno())],
                env=env, pass_fds=[child.fileno(), broker_child.fileno()], stdout=subprocess.PIPE, stderr=log, text=True)
        child.close(); broker_child.close()

        def command(value):
            control.sendall(value.encode()); return json.loads(control.recv(65536))

        def client(method=False):
            item = Client(probe, "--input-method" if method else "--text-input", env, artifacts,
                          f"client-{len(clients)}", broker if method else None)
            clients.append(item); return item

        def no_event(item, event, start):
            item.sync()
            assert not any(e["event"] == event for e in item.events[start:]), item.events[start:]

        storage = None
        try:
            assert select.select([server.stdout], [], [], 10)[0], "compositor startup"
            env["WAYLAND_DISPLAY"] = server.stdout.readline().strip().split("=", 1)[1]
            if pasteboard_server:
                with (artifacts / "gpbs.log").open("w") as log:
                    storage = subprocess.Popen([pasteboard_server, "--no-fork"], env=env, stdout=log, stderr=log)
                until(lambda: subprocess.run([pasteboard_probe, "--ping"], env=env).returncode == 0,
                      "test-owned pasteboard storage")
            subprocess.run([probe], env=env, check=True, timeout=10)
            text = client(); text.wait("enter")
            text.send("enable"); text.sync()
            method = client(True); method.wait("activate")
            assert method.wait("surrounding")["hex"] == "hello日本".encode().hex()
            assert method.wait("selection") == dict(event="selection", cursor=11, anchor=5)
            method.wait("done")
            global_id = method.wait("ready")["global"]
            subprocess.run([probe, "--forbidden-input-method", str(global_id)], env=env, check=True, timeout=10)

            method.send("preedit 0 6 日本"); method.send("done"); method.sync()
            assert text.wait("preedit")["hex"] == "日本".encode().hex()
            assert text.wait("preedit-cursor") == dict(event="preedit-cursor", begin=0, end=6)
            assert text.wait("done")["serial"] == 1
            start = text.sync()
            method.send("delete 6 0"); method.send("commit 語"); method.send("done"); method.sync()
            assert text.wait("delete", start) == dict(event="delete", before=6, after=0)
            assert text.wait("commit", start)["hex"] == "語".encode().hex()
            assert text.wait("preedit", start)["hex"] == ""

            start = text.sync()
            method.send("commit stale"); method.send("done 0"); method.sync()
            no_event(text, "commit", start)
            start = text.sync(); method_start = method.sync()
            text.send("rectangle 32 28 2 18"); text.sync()
            no_event(method, "done", method_start)
            assert text.wait("done", start)["serial"] == 2
            method.send("commit geometry"); method.send("done"); method.sync()
            assert text.wait("commit", start)["hex"] == "geometry".encode().hex()
            start = method.sync(); text_start = text.sync()
            text.send("state 1 0 0 0 1 1 日本"); text.sync()
            assert method.wait("surrounding", start)["hex"] == "", "Invalid UTF-8 byte boundary reached the IME"
            assert text.wait("done", text_start)["serial"] == 3
            text.send("state 11 5 12 14 2 18 hello日本"); text.sync(); method.sync()

            # Text feedback can pass a composition already in flight. Keep
            # its edits, but reject future serials and old security contexts.
            prior_serial = [e['serial'] for e in method.events if e['event']=='done'][-1]
            method_start = method.sync()
            text.send('state 7 7 12 14 2 18 updated'); text.sync()
            current_serial = method.wait('done', method_start)['serial']; method.sync()
            assert current_serial != prior_serial
            start = text.sync()
            method.send('commit delayed'); method.send(f'done {prior_serial}'); method.sync()
            assert text.wait('commit', start)['hex'] == b'delayed'.hex()
            start = text.sync()
            method.send('commit future'); method.send(f'done {(current_serial+1)&0xffffffff}'); method.sync()
            no_event(text, 'commit', start)
            method.send('preedit 0 3 新'); method.send(f'done {prior_serial}'); method.sync()
            start = text.sync()
            text.send('rectangle 32 28 2 18'); text.sync()
            assert text.wait('preedit', start)['hex'] == '新'.encode().hex()
            text.send('content 192 8'); text.sync(); method.sync()
            start = text.sync()
            method.send('commit old-content'); method.send(f'done {current_serial}'); method.sync()
            no_event(text, 'commit', start)
            text.send('content 0 0'); text.sync(); method.sync()

            # Physical keys reach the method, and forwarded keys reach the client once.
            method.send("grab"); method.wait("keymap"); method.sync()
            start = text.sync(); method_start = method.sync()
            for state in (1, 0): assert command(f"key 30 {state}")["ok"]
            method.wait("key", method_start); method.sync(); no_event(text, "key", start)
            assert [e["state"] for e in method.events[method_start:] if e["event"] == "key"] == [1, 0]
            method_start = method.sync()
            method.send("forward 30 1"); method.send("forward 30 0"); method.sync()
            text.wait("key", start); text.sync()
            assert [e["state"] for e in text.events[start:] if e["event"] == "key"] == [1, 0]
            no_event(method, "key", method_start)

            method.send("popup"); method.wait("rectangle")
            window = next(w for w in command("windows") if w["title"] == "TextInputProbe")
            for scale in (120, 150, 180, 210, 240):
                output = command("outputs")[0]
                assert command(f"test-scale {output['name']} {scale} 10000")["ok"]
                assert command("confirm")["ok"]
                output = next(o for o in command("outputs") if o["name"] == output["name"])
                assert command(f"move {window['id']} {output['x'] + output['width'] - 64} {output['y'] + output['height'] - 64}")["ok"]
                text.send("state 1 1 58 58 2 4 x"); text.sync(); method.sync()
                popup = until(lambda: next(iter(command("input-popups")), None), "candidate popup")
                assert output["x"] <= popup["x"] <= output["x"] + output["width"] - popup["width"], popup
                assert output["y"] <= popup["y"] <= output["y"] + output["height"] - popup["height"], popup

            # Leave invalidates the composition; a stale method transaction cannot enter the next client.
            previous_serial = [e["serial"] for e in method.events if e["event"] == "done"][-1]
            other = client(); other.wait("enter"); text.wait("leave")
            method.wait("deactivate"); method.sync()
            assert command("input-popups") == []
            other.send("enable"); other.sync(); method.sync()
            start = other.sync()
            method.send("commit wrong-focus"); method.send(f"done {previous_serial}"); method.sync()
            no_event(other, "commit", start)
            method.send("commit correct"); method.send("done"); method.sync()
            assert other.wait("commit", start)["hex"] == b"correct".hex()

            start = other.sync()
            replacement = client(True); replacement.wait("activate"); replacement.wait("done")
            until(lambda: method.process.poll() is not None, "previous method revoked")
            assert other.wait("preedit", start)["hex"] == ""
            replacement.send("commit restarted"); replacement.send("done"); replacement.sync()
            assert other.wait("commit", start)["hex"] == b"restarted".hex()
            other.send("disable"); other.sync(); replacement.wait("deactivate")
            start = other.sync()
            replacement.send("commit disabled"); replacement.send("done"); replacement.sync()
            no_event(other, "commit", start)
            if native_probe:
                for mode in range(4):
                    run_native(native_probe, replacement, env, command, artifacts, mode=mode)
                    run_native(native_probe, replacement, env, command, artifacts, secure=True, mode=mode)
            if terminal:
                run_terminal(terminal, workspace_probe, replacement, env, command, artifacts)
            broker.close()
            until(lambda: replacement.process.poll() is not None, "supervisor revokes input method")
            assert other.process.poll() is None and text.process.poll() is None
            (artifacts / "results.json").write_text(json.dumps(dict(
                protocol="text-input-v3/input-method-v2", scales=[120, 150, 180, 210, 240],
                authority=True, focus=True, stale_serials=True, delayed_edits=True,
                content_isolation=True, preedit=True, deletion=True,
                keyboard_forwarding=True, candidate_bounds=True, replacement=True), indent=2) + "\n")
            print("Trusted IME relay, preedit, focus, keyboard forwarding and candidate bounds: PASS")
        finally:
            for item in reversed(clients): item.stop()
            if storage: stop_process(storage)
            stop_process(server)
            control.close(); broker.close(); server.stdout.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--compositor", required=True)
    parser.add_argument("--probe", required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--native-probe")
    parser.add_argument("--terminal")
    parser.add_argument("--workspace-probe")
    parser.add_argument("--pasteboard-server")
    parser.add_argument("--pasteboard-probe")
    args = parser.parse_args()
    if args.terminal and not args.workspace_probe: parser.error("--terminal requires --workspace-probe")
    if bool(args.pasteboard_server) != bool(args.pasteboard_probe): parser.error("Pasteboard server and probe must be supplied together")
    run(args.compositor, args.probe, args.artifacts, args.native_probe, args.terminal, args.workspace_probe,
        args.pasteboard_server, args.pasteboard_probe)
