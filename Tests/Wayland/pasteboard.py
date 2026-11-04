#!/usr/bin/env python3
"""Prove native storage persistence and isolation without an X server."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid
import plistlib
import shutil

from gnustep import private_defaults


def stop_during_defaults_write(server, delay_library, artifacts):
    """Signal only after the native server holds its private defaults lock."""
    from integration import until

    artifacts.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='nextspace-pasteboard-stop-') as temporary:
        home = Path(temporary)
        marker = home / 'lock-held'
        env = dict(os.environ, HOME=str(home), LD_PRELOAD=str(delay_library),
                   NEXTSPACE_SESSION_ID='test-stop-' + uuid.uuid4().hex,
                   NEXTSPACE_TEST_DEFAULTS_LOCK_MARKER=str(marker))
        env.pop('DISPLAY', None)
        private_defaults(env, home)
        (home / 'defaults/.lck').mkdir(parents=True)
        with (artifacts / 'server.log').open('w') as log:
            process = subprocess.Popen([str(server), '--no-fork'], env=env, stdout=log, stderr=log)
        lock = home / 'defaults/.lck/.GNUstepDefaults.lck'
        try:
            def acquired():
                assert process.poll() is None, 'Pasteboard exited before the controlled lock window'
                return marker.exists() and lock.exists()

            until(acquired, 'pasteboard holds its defaults lock', timeout=10)
            process.terminate()
            assert process.wait(timeout=5) == 0, 'Pasteboard interrupted a defaults write'
            assert not lock.exists(), 'Pasteboard left its defaults database locked'
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
        (artifacts / 'result.txt').write_text('PASS: SIGTERM during defaults write exits successfully and releases the lock\n')
        (artifacts / 'result.json').write_text(json.dumps(dict(passed=True,
            signal_while_defaults_lock_held=True, graceful_exit=True, defaults_lock_released=True), indent=2) + '\n')


def install_service(probe, env):
    library = Path(subprocess.check_output([probe, "--library-dir"], env=env, text=True).strip())
    services = library / "Services"
    services.mkdir(parents=True, exist_ok=True)
    bundle = Path(tempfile.mkdtemp(prefix="NextSpaceWaylandProbe-", suffix=".service", dir=services))
    resources = bundle / "Resources"
    resources.mkdir()
    info = {"NSServices": [{"NSMenuItem": {"default": "NextSpace Wayland Echo"},
        "NSPortName": "WaylandProbe", "NSMessage": "echo", "NSTimeout": "3000",
        "NSSendTypes": ["NSStringPboardType"], "NSReturnTypes": ["NSStringPboardType"]}]}
    (resources / "Info-gnustep.plist").write_bytes(plistlib.dumps(info))
    subprocess.run(["make_services", "--quiet"], env=env, check=True)
    return bundle


def remove_service(bundle, env):
    shutil.rmtree(bundle)
    subprocess.run(["make_services", "--quiet"], env=env, check=True)


def run(server, probe, artifacts):
    artifacts.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.pop("DISPLAY", None)
    env.pop("NEXTSPACE_SESSION_ID", None)
    assert subprocess.check_output([probe, "--name"], env=env, text=True).strip() == "GNUstepGSPasteboardServer"
    processes = []
    logs = []
    try:
        sessions = []
        for _ in range(2):
            session = dict(env, NEXTSPACE_SESSION_ID=str(uuid.uuid4()))
            sessions.append(session)
            log = (artifacts / f"gpbs-{len(sessions)}.log").open("w")
            logs.append(log)
            process = subprocess.Popen([server, "--no-fork"], env=session, stdout=log, stderr=log)
            processes.append(process)
            deadline = time.monotonic() + 10
            while subprocess.run([probe, "--ping"], env=session).returncode:
                assert process.poll() is None, "Native storage exited before registration"
                assert time.monotonic() < deadline, "Native storage did not register"
                time.sleep(0.05)
        a, b = sessions
        subprocess.run([probe, "--empty"], env=a, check=True)
        subprocess.run([probe, "--write"], env=a, check=True)
        subprocess.run([probe, "--read"], env=a, check=True)
        subprocess.run([probe, "--empty"], env=b, check=True)
        subprocess.run([probe, "--write"], env=b, check=True)
        # Storage outlives the writing client and remains independent per session.
        subprocess.run([probe, "--read"], env=a, check=True)
        subprocess.run([probe, "--read"], env=b, check=True)
        # A newer writer must win; only this ownership conflict is retryable.
        assert subprocess.run([probe, "--clear-race"], env=a).returncode == 75
        subprocess.run([probe, "--read"], env=a, check=True)
        subprocess.run([probe, "--clear"], env=a, check=True)
        assert subprocess.check_output([probe, "--export-text"], env=a) == b"pending"
        subprocess.run([probe, "--read"], env=b, check=True)
        with tempfile.TemporaryFile() as errors:
            assert subprocess.run([server, "--no-fork"], env=env, stderr=errors).returncode != 0
        (artifacts / "result.json").write_text(json.dumps(dict(passed=True,
            sessions_isolated=True, unicode_and_opaque_types=True,
            competing_writer_preserved=True, stale_reset_retryable=True,
            fresh_reset_succeeds=True), indent=2) + "\n")
        (artifacts / "result.txt").write_text("PASS: per-session persistence, Unicode and opaque GNUstep data; DISPLAY unset\n")
        print("Native pasteboard storage: persistence, Unicode, opaque types and session isolation PASS")
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
        for log in logs:
            log.close()
    stop_during_defaults_write(server, Path(probe).parent / 'defaults-lock-delay.so', artifacts / 'stop-during-write')


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", required=True)
    parser.add_argument("--probe", required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    run(args.server, args.probe, args.artifacts)
