#!/usr/bin/env python3
"""External CPU and private kernel-event profiling for one owned compositor."""

import argparse
import json
import signal
import subprocess
import time
from pathlib import Path


class Profile:
    def __init__(self, root, pid):
        self.root = root / "profile"
        self.root.mkdir()
        self.pid = pid
        self.instance = Path("/sys/kernel/tracing/instances") / (
            "nextspace-burst-" + str(pid)
        )
        self.instance.mkdir()
        self.process = None
        self.log = None
        self.events = []
        self.record = {
            "pid": pid,
            "started": time.monotonic(),
            "external_instrumentation": True,
        }

    def start(self):
        instance = self.instance
        (instance / "tracing_on").write_text("0")
        (instance / "trace_clock").write_text("mono")
        (instance / "buffer_size_kb").write_text("4096")
        filters = {
            "sched/sched_switch": f"prev_pid == {self.pid} || next_pid == {self.pid}",
            "sched/sched_wakeup": f"pid == {self.pid}",
            "syscalls/sys_enter_read": f"common_pid == {self.pid}",
            "syscalls/sys_exit_read": f"common_pid == {self.pid}",
        }
        for name, condition in filters.items():
            event = instance / "events" / name
            (event / "filter").write_text(condition)
            (event / "enable").write_text("1")
            self.events.append(event)
        self.record["fd_targets"] = {}
        for fd in Path("/proc", str(self.pid), "fd").iterdir():
            try:
                self.record["fd_targets"][fd.name] = str(fd.readlink())
            except FileNotFoundError:
                pass
        (instance / "tracing_on").write_text("1")
        self.log = (self.root / "perf-record.log").open("w")
        command = [
            "perf",
            "record",
            "--no-buildid-cache",
            "-e",
            "cpu-clock:u",
            "-F",
            "999",
            "--call-graph",
            "fp",
            "--clockid",
            "mono",
            "-p",
            str(self.pid),
            "-o",
            str(self.root / "compositor.perf.data"),
        ]
        self.process = subprocess.Popen(command, stdout=self.log, stderr=self.log)
        time.sleep(0.1)
        assert self.process.poll() is None, (self.root / "perf-record.log").read_text()
        self.record["command"] = command

    def stop(self):
        try:
            if self.process is not None:
                if self.process.poll() is None:
                    self.process.send_signal(signal.SIGINT)
                self.record["perf_returncode"] = self.process.wait(timeout=10)
            if self.log:
                self.log.close()
            (self.instance / "tracing_on").write_text("0")
            (self.root / "kernel-events.txt").write_text(
                (self.instance / "trace").read_text()
            )
            self.record["kernel_buffers"] = {
                str(p.relative_to(self.instance)): p.read_text()
                for p in (self.instance / "per_cpu").glob("cpu*/stats")
            }
            if (self.root / "compositor.perf.data").exists():
                for filename, arguments in [
                    ("cpu-samples.txt", ["script", "--ns"]),
                    (
                        "cpu-report.txt",
                        [
                            "report",
                            "--stdio",
                            "--no-children",
                            "--sort=dso,symbol",
                            "--percent-limit=1",
                        ],
                    ),
                ]:
                    with (
                        (self.root / filename).open("w") as out,
                        (self.root / (filename + ".errors")).open("w") as errors,
                    ):
                        result = subprocess.run(
                            [
                                "perf",
                                *arguments,
                                "-i",
                                str(self.root / "compositor.perf.data"),
                            ],
                            stdout=out,
                            stderr=errors,
                            check=False,
                        )
                    self.record[filename + "_returncode"] = result.returncode
        finally:
            for event in self.events:
                (event / "enable").write_text("0")
            self.instance.rmdir()
            self.record.update(
                finished=time.monotonic(),
                private_trace_instance_removed=not self.instance.exists(),
            )
            (self.root / "profile.json").write_text(
                json.dumps(self.record, indent=2) + "\n"
            )


def start_profile(root, pid):
    profile = Profile(root, pid)
    try:
        profile.start()
    except BaseException:
        profile.stop()
        raise
    return profile


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=10)
    args = parser.parse_args()
    if not 0 < args.seconds <= 60:
        parser.error("--seconds must be greater than zero and at most 60")
    executable = Path("/proc", str(args.pid), "exe").resolve()
    if executable.name != "nextspace-compositor":
        parser.error("--pid must name a running nextspace-compositor")
    args.artifacts.mkdir(parents=True)
    profile = start_profile(args.artifacts.resolve(), args.pid)
    try:
        time.sleep(args.seconds)
    finally:
        profile.stop()
    print(json.dumps(profile.record, indent=2))
