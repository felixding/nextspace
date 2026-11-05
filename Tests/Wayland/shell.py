#!/usr/bin/env python3
"""Exercise shell authority, compositor-owned state and supervisor reconnection."""
import argparse
import array
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import tempfile
from integration import until


class Shell:
    def __init__(self, executable, broker, env, directory, index, version=4, workspace_mode=None):
        server, client = socket.socketpair()
        broker.sendmsg([b"C"], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [server.fileno()]))])
        server.close()
        self._track(directory,index,workspace_mode is not None)
        with (directory / f"shell-{index}.stderr").open("w") as errors:
            arguments = [str(workspace_mode), "--nextspace-shell-fd", str(client.fileno())] if self.workspace else (
                [f"--version{version}"] if version != 4 else [])
            connection_env = dict(env) if self.workspace else dict(env, WAYLAND_SOCKET=str(client.fileno()))
            self.process = subprocess.Popen([executable, *arguments], env=connection_env,
                pass_fds=[client.fileno()], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors)
        client.close()
        os.set_blocking(self.process.stdout.fileno(), False)
        self.wait(lambda: self.global_id is not None, "authorized shell binding")

    def _track(self,directory,index,workspace):
        self.events = []
        self.outputs = {}
        self.output_revision = 0
        self.output_batches = 0
        self.configuration_results = []
        self.input_settings = None
        self.input_batches = 0
        self.input_results = []
        self.windows = {}
        self.done = 0
        self.resets = 0
        self.snapshot_pending = False
        self.global_id = None
        self.pending = b""
        self.workspace = workspace
        self.log = (directory / f"shell-{index}.jsonl").open("w")
        self.environment = {}

    @classmethod
    def from_process(cls,process,directory,workspace=True):
        item=cls.__new__(cls)
        item._track(directory,'supervisor',workspace)
        item.process=process
        os.set_blocking(process.stdout.fileno(),False)
        item.wait(lambda:item.global_id is not None,'supervised shell binding')
        return item

    def pump(self):
        while select.select([self.process.stdout], [], [], 0)[0]:
            chunk = os.read(self.process.stdout.fileno(), 65536)
            if not chunk:
                break
            self.pending += chunk
            while b"\n" in self.pending:
                line, self.pending = self.pending.split(b"\n", 1)
                self.log.write(line.decode() + "\n"); self.log.flush()
                if not line.startswith(b'{') and b'=' in line:
                    key,value=line.decode().split('=',1);self.environment[key]=value
                    continue
                event = json.loads(line)
                self.events.append(event)
                if self.workspace:
                    if event["event"] in ("ready", "windows"):
                        self.windows = {w["id"]: w for w in event["windows"]}
                        self.resets += 1; self.done += 1
                        if event["event"] == "ready": self.global_id = "workspace"
                        continue
                    if event["event"] == "outputs":
                        self.outputs = {h["id"]: h for h in event["outputs"]}
                        self.output_revision = event["revision"]; self.output_batches += 1
                        continue
                    if event["event"] == "closed": continue
                if event["event"] == "input-settings":
                    self.input_settings = event; self.input_batches += 1
                elif event["event"] == "input-result": self.input_results.append(event)
                elif event["event"] == "outputs-reset":
                    self.outputs.clear(); self.output_revision = event["revision"]
                elif event["event"] == "output": self.outputs[event["id"]] = event
                elif event["event"] == "output-identity": self.outputs[event["id"]].update(event)
                elif event["event"] == "output-work-area": self.outputs[event["id"]].update(
                    {k: event[k] for k in ("work_x", "work_y", "work_width", "work_height")})
                elif event["event"] == "output-mode":
                    self.outputs[event["id"]].setdefault("modes", []).append(event)
                elif event["event"] == "outputs-done": self.output_batches += 1
                elif event["event"] == "configuration-result": self.configuration_results.append(event)
                elif event["event"] == "reset":
                    self.windows.clear(); self.resets += 1; self.snapshot_pending = True
                elif event["event"] == "window": self.windows[event["id"]] = event
                elif event["event"] == "window-info": self.windows[event["id"]].update(event)
                elif event["event"] == "window-desktop": self.windows[event["id"]].update(
                    desktop=event["desktop"], sticky=event["sticky"])
                elif event["event"] == "closed": self.windows.pop(event["id"], None)
                elif event["event"] == "done":
                    self.done += 1; self.snapshot_pending = False
                elif event["event"] == "ready": self.global_id = event["global"]

    def wait(self, predicate, description):
        def check():
            self.pump()
            assert self.process.poll() is None, f"Shell exited: {self.process.returncode}"
            return predicate()
        return until(check, description)

    def send(self, command):
        self.process.stdin.write((command + "\n").encode()); self.process.stdin.flush()

    def snapshot(self):
        self.pump()
        before = self.resets
        self.send("snapshot")
        self.wait(lambda: self.resets > before and not self.snapshot_pending, "complete shell snapshot")
        return dict(self.windows)

    def configure_outputs(self, layout, timeout=10000):
        """Apply and confirm a complete privileged output transaction."""
        self.send(f"configure {self.output_revision}")
        keys = ('id','enabled','primary','width','height','refresh','scale','transform','x','y')
        for head in layout: self.send('head '+' '.join(str(head[key]) for key in keys))
        for request, status in ((f'apply {timeout}',1),('confirm',2)):
            before = len(self.configuration_results); self.send(request)
            self.wait(lambda:len(self.configuration_results)>before,'output '+request)
            assert self.configuration_results[-1]['status']==status,self.configuration_results[-1]

    def stop(self):
        if self.process.poll() is None:
            self.process.terminate(); self.process.wait(timeout=5)
        self.pump()
        self.process.stdin.close(); self.process.stdout.close(); self.log.close()


def run(compositor, shell_probe, registry_probe, artifacts, gui_probe=None, workspace_shell_probe=None):
    artifacts.mkdir(parents=True, exist_ok=True)
    processes, shells = [], []
    with tempfile.TemporaryDirectory(prefix="nextspace-shell-") as runtime:
        env = dict(os.environ, XDG_RUNTIME_DIR=runtime, WLR_BACKENDS="headless",
                   WLR_HEADLESS_OUTPUTS="2", WLR_RENDERER="pixman")
        for key in ("DISPLAY", "WAYLAND_DISPLAY", "WAYLAND_SOCKET"):
            env.pop(key, None)
        control, control_child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        broker, broker_child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        control.settimeout(5)
        with (artifacts / "compositor.log").open("w") as log:
            server = subprocess.Popen([compositor, "-c", str(control_child.fileno()),
                "-S", str(broker_child.fileno())], pass_fds=[control_child.fileno(), broker_child.fileno()],
                env=env, stdout=subprocess.PIPE, stderr=log, text=True)
        control_child.close(); broker_child.close()

        def command(value):
            control.sendall(value.encode())
            return json.loads(control.recv(65536))

        def keys(*sequence):
            for key, pressed in sequence: assert command(f"key {key} {pressed}")["ok"]

        def connect(version=4, workspace_mode=None):
            executable = workspace_shell_probe if workspace_mode is not None else shell_probe
            shell = Shell(executable, broker, env, artifacts, len(shells), version, workspace_mode)
            shells.append(shell)
            return shell

        def check_desktops(owner, identifier):
            def state(request, current, count=4):
                before = len(owner.events); owner.send(request)
                reply = "desktop-result" if owner.workspace else "desktops"
                result = owner.wait(lambda: next((e for e in reversed(owner.events[before:]) if e["event"] == reply), None),
                                    "desktop request reply")
                assert (result["current"], result["count"]) == (current, count), result
            def moved(index, sticky=False):
                owner.send(f"window-desktop {identifier} {index} {int(sticky)}")
                owner.wait(lambda: owner.windows[identifier].get("desktop") == index and
                           owner.windows[identifier].get("sticky") == sticky, "window desktop metadata")
            def visible(expected):
                return until(lambda: (w if (w := next(w for w in command("windows") if w["id"] == identifier))["visible"] == expected else None),
                             "desktop scene visibility")
            state("desktop-count 4", 0)
            state("desktop-count 0", 0)
            state("desktop 32", 0)
            original = owner.windows[identifier]
            moved(2); hidden = visible(False)
            assert command(f"hit {hidden['x'] + 10} {hidden['y'] + 10}")["id"] != identifier
            densities = command("outputs") if original["width"] > 100 else []
            scale = 120 if hidden["preferred_scale"] != 120 else 240
            for output in densities:
                assert command(f"test-scale {output['name']} {scale} 10000")["ok"]
                assert command("confirm")["ok"]
            state("desktop 2", 2); visible(True)
            if densities:
                until(lambda: (w := next(w for w in command("windows") if w["id"] == identifier))["buffer_width"] ==
                      (w["width"] * scale + 60) // 120, "returning desktop redraws a native window at its new density")
                for output in densities:
                    assert command(f"test-scale {output['name']} {output['scale']} 10000")["ok"]
                    assert command("confirm")["ok"]
            owner.send(f"minimize {identifier} 1")
            owner.wait(lambda: owner.windows[identifier]["flags"] & 8, "hidden desktop miniwindow")
            state("desktop 0", 0); state("desktop 2", 2); visible(False)
            owner.send(f"activate {identifier}")
            owner.wait(lambda: not owner.windows[identifier]["flags"] & 8, "desktop activation restores miniwindow")
            moved(2, True); state("desktop 0", 0); visible(True)
            moved(2); visible(False)
            owner.send(f"activate {identifier}")
            owner.wait(lambda: any(e["event"] == "desktops" and e["current"] == 2 for e in owner.events[-8:]),
                       "activation switches to the window desktop")
            visible(True)
            # Existing Window Maker defaults use Control+Left/Right and digits.
            keys((29, 1), (105, 1), (105, 0), (29, 0))
            owner.wait(lambda: any(e["event"] == "desktops" and e["current"] == 1 for e in owner.events[-8:]),
                       "Control+Left switches desktop")
            keys((29, 1), (5, 1), (5, 0), (29, 0))
            owner.wait(lambda: any(e["event"] == "desktops" and e["current"] == 3 for e in owner.events[-8:]),
                       "Control+4 selects desktop")
            state("desktop 3", 3)
            keys((56, 1), (1, 1), (1, 0), (56, 0))
            assert server.poll() is None, "Alt+Escape must not end a desktop session"
            moved(3); state("desktop-count 2", 1, 2)
            owner.wait(lambda: owner.windows[identifier].get("desktop") == 1, "removed desktop recovers its windows")
            visible(True)
            state("desktop-count 4", 1)
            moved(0); state("desktop 0", 0)
            current = visible(True)
            assert (current["width"], current["height"]) == (original["width"], original["height"])

        try:
            assert select.select([server.stdout], [], [], 10)[0], "No compositor socket"
            line = server.stdout.readline().strip()
            assert line.startswith("WAYLAND_DISPLAY="), line
            env["WAYLAND_DISPLAY"] = line.split("=", 1)[1]
            shell = connect()
            subprocess.run([registry_probe, "--activation"], env=env, check=True, capture_output=True, timeout=20)
            shell.wait(lambda: not shell.windows, "activation fixture closes its windows")
            subprocess.run([registry_probe], env=env, check=True, capture_output=True)
            subprocess.run([shell_probe, "--guess", str(shell.global_id)], env=env, check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            # Neither a public connection nor an application claiming Workspace
            # is the authorized connection. Its ordinary window remains usable.
            for name, level in (("ShellClientA", 0), ('ShellClientB: "日本語"', 2)):
                with (artifacts / f"client-{len(processes)}.log").open("w") as log:
                    processes.append(subprocess.Popen([registry_probe, "--window", name, str(level)],
                        env=env, stdout=log, stderr=log))
            shell.wait(lambda: len(shell.windows) == 2, "live shell window enumeration")
            initial = shell.snapshot()
            assert {w["pid"] for w in initial.values()} == {p.pid for p in processes}
            assert all(w["app_id"] == "Workspace" for w in initial.values())
            subprocess.run([registry_probe], env=env, check=True, capture_output=True)
            first = next(w for w in initial.values() if w["title"] == "ShellClientA")
            shell.send(f"move {first['id']} 220 140")
            shell.wait(lambda: (shell.windows[first["id"]]["x"], shell.windows[first["id"]]["y"]) == (220, 140),
                       "authorized logical placement")
            floating = next(w for w in initial.values() if w["id"] != first["id"])
            shell.send(f"move {floating['id']} 220 140")
            shell.wait(lambda: (shell.windows[floating["id"]]["x"], shell.windows[floating["id"]]["y"]) == (220, 140),
                       "overlapping floating window")
            shell.send(f"activate {first['id']}")
            shell.wait(lambda: shell.windows[first["id"]]["flags"] & 1, "authorized activation")
            until(lambda: next(w for w in command("windows") if w["id"] == first["id"])["focused"],
                  "compositor keyboard focus")
            keys((56, 1), (15, 1), (15, 0), (56, 0))
            shell.wait(lambda: shell.windows[floating["id"]]["flags"] & 1, "Command+Tab selects the next process group")
            keys((56, 1), (42, 1), (15, 1), (15, 0), (42, 0), (56, 0))
            shell.wait(lambda: shell.windows[first["id"]]["flags"] & 1, "Command+Shift+Tab reverses process groups")
            assert command("hit 240 160")["id"] == floating["id"], "Focus must preserve window levels"
            assert command("pointer 240 160")["ok"]
            assert command("pointer-focus")["id"] == floating["id"]
            shell.send(f"minimize {floating['id']} 1")
            shell.wait(lambda: shell.windows[floating["id"]]["flags"] & 8, "shell observes minimization")
            assert command("hit 240 160")["id"] == first["id"], "Minimized windows must leave hit testing"
            assert command("pointer-focus")["id"] == first["id"], "Pointer focus must leave the hidden surface without motion"
            shell.send(f"activate {floating['id']}")
            shell.wait(lambda: shell.windows[floating["id"]]["flags"] & 1 and
                       not shell.windows[floating["id"]]["flags"] & 8, "activation restores a minimized window")
            assert command("hit 240 160")["id"] == floating["id"]
            shell.send(f"present {floating['id']} 0")
            shell.wait(lambda: shell.windows[floating["id"]]["flags"] & 32,
                       "shell presentation suppresses a mapped window")
            hidden = shell.windows[floating["id"]]
            assert not hidden["flags"] & 8, "Presentation must not miniaturize the application"
            assert command("hit 240 160")["id"] == first["id"]
            assert command("pointer-focus")["id"] == first["id"]
            shell.send(f"activate {floating['id']}")
            shell.wait(lambda: shell.windows[floating["id"]]["flags"] & 1 and
                       not shell.windows[floating["id"]]["flags"] & 32, "activation restores shell presentation")
            assert command("hit 240 160")["id"] == floating["id"]

            # Invalid messages/fd types must leave the current connection intact
            # and close all received descriptors, including extra SCM_RIGHTS fds.
            before_fds = len(list(Path(f"/proc/{server.pid}/fd").iterdir()))
            shell.send(f"present {floating['id']} 0")
            shell.wait(lambda: shell.windows[floating["id"]]["flags"] & 32,
                       "presentation state before shell replacement")
            broker.send(b"invalid")
            a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            read_fd, write_fd = os.pipe()
            try:
                for descriptors in ([a.fileno()], [read_fd], [a.fileno(), b.fileno()], [read_fd] * 32):
                    broker.sendmsg([b"C"], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", descriptors))])
            finally:
                a.close(); b.close(); os.close(read_fd); os.close(write_fd)
            # A following valid broker packet creates a processing barrier.
            replacement = connect()
            shell.process.wait(timeout=5)
            assert shell.process.returncode != 0
            recovered = replacement.snapshot()
            assert set(recovered) == set(initial)
            assert (recovered[first["id"]]["x"], recovered[first["id"]]["y"]) == (220, 140)
            assert recovered[floating["id"]]["flags"] & 32
            assert command("hit 240 160")["id"] == first["id"]
            until(lambda: len(list(Path(f"/proc/{server.pid}/fd").iterdir())) <= before_fds,
                  "replaced connection and invalid descriptors released")
            assert all(p.poll() is None for p in processes)

            # Crash the shell. A supervisor-issued fresh connection recovers
            # compositor state without recreating or disconnecting applications.
            replacement.process.kill(); replacement.process.wait(timeout=5)
            restarted = connect()
            assert restarted.snapshot() == recovered
            restarted.send("close 4294967295")  # A stale ID is harmless.
            restarted.snapshot()
            restarted.send(f"close {first['id']}")
            processes[0].wait(timeout=5)
            assert processes[0].returncode == 0
            restarted.wait(lambda: first["id"] not in restarted.windows, "shell receives window removal")
            assert processes[1].poll() is None
            version2 = connect(version=2)
            version2_state = version2.snapshot()
            assert "client_id" not in version2_state[floating["id"]]
            version2.send(f"minimize {floating['id']} 1")
            version2.wait(lambda: version2.windows[floating["id"]]["flags"] & 8, "version 2 minimization")
            version2.send(f"activate {floating['id']}")
            version2.wait(lambda: version2.windows[floating["id"]]["flags"] & 1, "version 2 restore")
            legacy = connect(version=1)
            restarted.process.wait(timeout=5)
            legacy_state = legacy.snapshot()
            assert set(legacy_state) == {floating["id"]}
            assert command(f"minimize {floating['id']} 1")["ok"]
            assert not legacy.snapshot()[floating["id"]]["flags"] & 8, "Version 1 must retain its flag contract"
            legacy.send(f"activate {floating['id']}")
            legacy.wait(lambda: legacy.windows[floating["id"]]["flags"] & 1, "version 1 activation restores visibility")
            version3 = connect(version=3)
            assert "client_id" in version3.snapshot()[floating["id"]]
            owner = version3
            version5 = connect(version=5)
            previous_level = version5.snapshot()[floating["id"]]["level"]
            version5.send(f"level {floating['id']} 7")
            version5.wait(lambda: version5.windows[floating["id"]]["level"] == 7, "version 5 icon stacking")
            version5.send(f"level {floating['id']} {previous_level}")
            version5.wait(lambda: version5.windows[floating["id"]]["level"] == previous_level, "version 5 restores stacking")
            owner = version5
            native_window = None
            if gui_probe:
                owner = connect()
                with (artifacts / "native-client.log").open("w") as log:
                    gui = subprocess.Popen([gui_probe, "-GSBackend", "libgnustep-wayland", "-GSTheme", "NextSpace",
                        "-NSUseRunningCopy", "NO"], env=env, stdout=log, stderr=log)
                    processes.append(gui)
                native_window = owner.wait(lambda: next((w for w in owner.windows.values()
                    if w["pid"] == gui.pid and w["width"] == 801 and w.get("title_height", 0) > 0), None),
                    "native window identity and frame metadata")
                native_id = native_window["id"]
                owner.send(f"move {native_id} 400 200")
                owner.wait(lambda: (owner.windows[native_id]["x"], owner.windows[native_id]["y"]) == (400, 200),
                           "native shell placement")
                assert command("pointer 600 500")["ok"]
                owner.send(f"shade {native_id} 1")
                owner.wait(lambda: owner.windows[native_id]["flags"] & 16, "native shading through shell protocol")
                assert command("hit 600 205")["id"] == native_id
                assert command("hit 600 500")["id"] != native_id
                assert command("pointer-focus")["id"] != native_id
                owner.send(f"activate {native_id}")
                owner.wait(lambda: owner.windows[native_id]["flags"] & 1 and
                           not owner.windows[native_id]["flags"] & 16, "activation unshades a native window")
                assert command("hit 600 500")["id"] == native_id
                entries = [json.loads(line) for line in (artifacts / "native-client.log").read_text().splitlines()
                           if line.startswith('{"event":')]
                button = next(e for e in entries if e["event"] == "popup-button")
                assert command(f"pointer {400 + int(button['x'])} {801 - int(button['y'])}")["ok"]
                assert command("button 272")["ok"]
                until(lambda: len(command("popups")) == 1, "native popup before shading")
                owner.send(f"shade {native_id} 1")
                until(lambda: not command("popups"), "shading dismisses popup and its grab")
                owner.send(f"activate {native_id}")
                owner.wait(lambda: not owner.windows[native_id]["flags"] & 16, "native document unshaded again")
                owner.send(f"present {native_id} 0")
                owner.wait(lambda: owner.windows[native_id]["flags"] & 32, "native presentation suppressed")
                assert command("hit 600 500")["id"] != native_id
                retained = owner.windows[native_id]
                assert (retained["width"], retained["height"]) == (801, 601)
                assert not retained["flags"] & 8
                owner.send(f"activate {native_id}")
                owner.wait(lambda: owner.windows[native_id]["flags"] & 1 and
                           not owner.windows[native_id]["flags"] & 32, "native presentation restored")
                owner = connect(version=11)
                check_desktops(owner, native_id)
                owner.send(f"close {native_id}")
                gui.wait(timeout=10)
                assert gui.returncode == 0
                owner.wait(lambda: native_id not in owner.windows, "native closed event")
            owner = connect(version=10)
            check_desktops(owner, floating["id"])
            owner.send(f"window-desktop {floating['id']} 2 0")
            owner.wait(lambda: owner.windows[floating["id"]].get("desktop") == 2, "desktop assignment before shell replacement")
            owner.send("desktop 2")
            until(lambda: command("desktops")["current"] == 2, "active desktop before shell replacement")
            owner = connect(version=10)
            assert command("desktops") == dict(current=2, count=4)
            assert owner.snapshot()[floating["id"]]["desktop"] == 2
            owner.send(f"window-desktop {floating['id']} 0 0")
            owner.send("desktop 0")
            until(lambda: command("desktops")["current"] == 0, "desktop restored after shell replacement")
            if workspace_shell_probe:
                # This is the real Workspace client implementation, driven in
                # each AppKit run-loop mode, including modal/menu tracking.
                for mode in range(4):
                    owner = connect(workspace_mode=mode)
                    state = owner.snapshot()
                    assert set(state) == {floating["id"]}
                    identifier = floating["id"]
                    check_desktops(owner, identifier)
                    owner.send(f"move {identifier} {310 + mode} {170 + mode}")
                    owner.wait(lambda: (owner.windows[identifier]["x"], owner.windows[identifier]["y"]) ==
                               (310 + mode, 170 + mode), "Workspace run-loop placement")
                    before = owner.windows[identifier].copy()
                    start = len(owner.events)
                    owner.send(f"snapshot-move {identifier} {330 + mode} {190 + mode}")
                    snapshot = owner.wait(lambda: next((e for e in owner.events[start:]
                        if e["event"] == "window-snapshot"), None), "window snapshot survives nested dispatch")
                    assert snapshot["before"] == before
                    assert (snapshot["after"]["x"], snapshot["after"]["y"]) == (330 + mode, 190 + mode)
                    owner.send(f"minimize {identifier} 1")
                    owner.wait(lambda: owner.windows[identifier]["flags"] & 8, "Workspace minimization event")
                    owner.send(f"activate {identifier}")
                    owner.wait(lambda: owner.windows[identifier]["flags"] & 1 and
                               not owner.windows[identifier]["flags"] & 8, "Workspace activation event")
                    owner.send(f"present {identifier} 0")
                    owner.wait(lambda: owner.windows[identifier]["flags"] & 32, "Workspace presentation event")
                    assert not owner.windows[identifier]["flags"] & 8
                    owner.send(f"activate {identifier}")
                    owner.wait(lambda: not owner.windows[identifier]["flags"] & 32, "Workspace restores presentation")
                # A public socket endpoint still does not become a shell merely
                # because Workspace receives it through the expected variable.
                endpoint = socket.socket(socket.AF_UNIX)
                endpoint.connect(str(Path(runtime) / env["WAYLAND_DISPLAY"]))
                try:
                    result = subprocess.run([workspace_shell_probe, "--nextspace-shell-fd", str(endpoint.fileno())],
                        env=env,
                        pass_fds=[endpoint.fileno()], capture_output=True, timeout=10)
                    assert result.returncode == 3, result.stderr.decode()
                    same_fd = subprocess.run([workspace_shell_probe, "--nextspace-shell-fd", str(endpoint.fileno())],
                        env=dict(env, WAYLAND_SOCKET=str(endpoint.fileno())),
                        pass_fds=[endpoint.fileno()], capture_output=True, timeout=10)
                    assert same_fd.returncode == 2
                finally:
                    endpoint.close()
            broker.close()
            owner.process.wait(timeout=5)
            assert owner.process.returncode == 3
            assert processes[1].poll() is None and server.poll() is None
            subprocess.run([registry_probe], env=env, check=True, capture_output=True)
            (artifacts / "results.json").write_text(json.dumps(dict(initial=initial, recovered=recovered,
                native_window=native_window,
                workspace_run_loop_modes=4 if workspace_shell_probe else 0,
                passed=["public registry and guessed bind rejected", "spoofed app ID has no authority",
                        "snapshot, activate, move and close", "invalid broker fds released",
                        "window snapshots survive reentrant metadata replacement",
                        "focus preserves floating level", "minimize and restore", "connection replacement",
                        "shell crash and state recovery", "version 1/2/3/4/5 compatibility",
                        "retained shell presentation and hit testing", "broker revocation",
                        "input-authorized activation and single-use tokens",
                        "desktop visibility, sticky windows, retained minimization, count reduction and activation",
                        "Control desktop shortcuts and safe Alt+Escape",
                        "native redraw after a density change on an inactive desktop"]),
                indent=2, ensure_ascii=False) + "\n")
            print("Shell capability, state recovery and client survival: PASS")
        finally:
            for shell in shells: shell.stop()
            for process in processes:
                if process.poll() is None: process.terminate(); process.wait(timeout=5)
            if server.poll() is None:
                server.terminate(); server.wait(timeout=5)
            server.stdout.close(); control.close(); broker.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--compositor", required=True)
    parser.add_argument("--shell-probe", required=True)
    parser.add_argument("--registry-probe", required=True)
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--gui-probe")
    parser.add_argument("--workspace-shell-probe")
    args = parser.parse_args()
    run(args.compositor, args.shell_probe, args.registry_probe, args.artifacts, args.gui_probe,
        args.workspace_shell_probe)
