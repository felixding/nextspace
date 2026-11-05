"""Session-scoped Workspace RPC, notifications, registry and backend choice."""
import json
import os
import select
import subprocess
import uuid


def run(probe, env, artifacts):
    directory = artifacts / "session"
    directory.mkdir(parents=True, exist_ok=True)
    sessions = [dict(env, NEXTSPACE_SESSION_ID="test-" + str(uuid.uuid4())) for _ in range(2)]
    processes = []
    server_name = "NextSpaceWorkspaceSessionServer"

    def query(mode, environment, *extra):
        return json.loads(subprocess.check_output([probe, mode, *extra], env=environment, timeout=10))

    def start(mode, environment, label):
        with (directory / f"{label}.stderr").open("w") as errors:
            process = subprocess.Popen([probe, mode, "-GSTheme", "NextSpace"], env=environment,
                stdout=subprocess.PIPE, stderr=errors, text=True)
        processes.append(process)
        assert select.select([process.stdout], [], [], 10)[0], f"No {label} readiness"
        assert json.loads(process.stdout.readline()) == dict(ready=True)
        return process

    try:
        # The service uses the session choice without a per-process backend flag.
        capture = directory / "server"
        capture.mkdir(exist_ok=True)
        server_env = dict(sessions[0], NEXTSPACE_GS_BACKEND="wayland",
                          NEXTSPACE_WAYLAND_CAPTURE_DIR=str(capture.resolve()))
        server = start("--serve", server_env, "server")
        local = query("--list", sessions[0], "-GSWorkspaceApplication", server_name)
        assert local == [dict(NSApplicationName=server_name, pids=[server.pid])], local
        other = query("--list", sessions[1], "-GSWorkspaceApplication", server_name)
        assert not any(app.get("NSApplicationName") == server_name for app in other), other

        observer = start("--watch", sessions[0], "observer")
        isolated = start("--watch-empty", sessions[1], "isolated")
        start("--notify-hold", sessions[0], "notifier")
        observed, _ = observer.communicate(timeout=10)
        rejected, _ = isolated.communicate(timeout=10)
        assert observer.returncode == isolated.returncode == 0, (observed, rejected)
        assert json.loads(observed) == dict(observed=True)
        assert json.loads(rejected) == dict(observed=False)

        no_workspace = ["-GSWorkspaceApplication", "NextSpaceMissingWorkspaceForTest"]
        records = [query("--list", environment, *no_workspace) for environment in sessions]
        assert any(app.get("NSApplicationName") == "NextSpaceSessionProbe" for app in records[0]), records
        assert not any(app.get("NSApplicationName") == "NextSpaceSessionProbe" for app in records[1]), records
        assert query("--backend", server_env)["backend"] == "wayland"
        assert query("--backend", server_env, "-GSBackend", "cairo")["backend"] == "cairo"
        (directory / "results.json").write_text(json.dumps(dict(local=local, other=other, registry=records,
            notifications=dict(local=True, other=False), session_backend="wayland", explicit_override="cairo"), indent=2) + "\n")
        print("Workspace session RPC, notifications, registry and backend selection: PASS")
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
            process.stdout.close()
        for environment in sessions:
            query("--cleanup-registry", environment)
