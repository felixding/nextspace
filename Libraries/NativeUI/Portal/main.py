#!/usr/bin/env python3
"""Run the session FileChooser backend using the selected native UI library."""
import argparse
import json
import os
from pathlib import Path
import signal
from native_files import load
from file_chooser import FileChooser


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('-GSBackend', dest='backend', required=True)
    parser.add_argument('-GSTheme', dest='theme')
    args = parser.parse_args()
    if os.environ.get('XDG_SESSION_TYPE') != 'wayland' or not os.environ.get('WAYLAND_DISPLAY'):
        parser.error('The native file portal requires a Wayland session')
    service = FileChooser(load(args.library))
    previous_wakeup = signal.set_wakeup_fd(service.writer)
    def finish(*unused):
        service.enqueue('stop')
    signal.signal(signal.SIGTERM, finish)
    signal.signal(signal.SIGINT, finish)
    print(json.dumps(dict(event='ready', pid=os.getpid())), flush=True)
    try:
        service.run()
    finally:
        signal.set_wakeup_fd(previous_wakeup)
        service.close()


if __name__ == '__main__':
    main()
