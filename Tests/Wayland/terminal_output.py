#!/usr/bin/env python3
"""Acknowledge that the terminal parsed all PTY output preceding this request."""
import argparse
import json
import os
from pathlib import Path
import re
import select
import termios
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--ack', type=Path, required=True)
args = parser.parse_args()
assert os.isatty(0) and os.isatty(1), 'Requires the owned Terminal PTY'
saved = termios.tcgetattr(0)
attributes = list(saved)
attributes[6] = list(saved[6])
attributes[3] &= ~(termios.ECHO | termios.ICANON)
attributes[6][termios.VMIN] = 1
attributes[6][termios.VTIME] = 0
response = b''
started = time.monotonic()
try:
    termios.tcsetattr(0, termios.TCSANOW, attributes)
    assert os.write(1, b'\x1b[6n') == 4
    deadline = started + 5
    while not response.endswith(b'R'):
        remaining = deadline - time.monotonic()
        assert remaining > 0 and select.select([0], [], [], remaining)[0], 'Terminal output acknowledgement timed out'
        value = os.read(0, 1)
        assert value and len(response) < 64, 'Invalid terminal output acknowledgement'
        response += value
    assert re.fullmatch(rb'\x1b\[[1-9][0-9]*;[1-9][0-9]*R', response), response
finally:
    termios.tcsetattr(0, termios.TCSANOW, saved)
args.ack.write_text(json.dumps(dict(request='cursor-position-report', response_hex=response.hex(), started=started, acknowledged=time.monotonic(), tty_restored=termios.tcgetattr(0) == saved)) + '\n')
