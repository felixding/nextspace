#!/usr/bin/env python3
"""Run the shared pinned dependency builder inside the disposable Linux image."""
from pathlib import Path
import subprocess
import sys


def build(repo, destination):
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Use the disposable Linux test image')
    subprocess.run([sys.executable, str(repo / 'Applications/Compositor/build-wlroots.py'),
                    str(repo), str(destination), '--update-loader-cache'], check=True)


if __name__ == '__main__':
    build(*(Path(path).resolve() for path in sys.argv[1:]))
