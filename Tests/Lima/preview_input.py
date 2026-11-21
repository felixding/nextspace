"""Give the graphics preview private aliases for its VM keyboard devices."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

PREVIEW = '/workspace/.build/native-ui/macbook-preview.py'
DEVICES = 'NEXTSPACE_TOSHY_DEVICES'


def enable():
    if os.environ.get('NEXTSPACE_TOSHY') == 'off' or os.environ.get('NEXTSPACE_PREVIEW_HEADLESS') == '1':
        return False
    if DEVICES in os.environ:
        return True

    settings = {key: value for key, value in os.environ.items()
                if key.startswith('NEXTSPACE_PREVIEW_')}
    os.execv('/usr/bin/sudo', [
        'sudo', '-n', '/usr/bin/unshare', '--mount', '--propagation', 'private',
        '--', '/usr/bin/python3', '-I', str(Path(__file__).resolve()), json.dumps(settings),
    ])


def launch(settings):
    uid, gid = int(os.environ['SUDO_UID']), int(os.environ['SUDO_GID'])
    if uid == 0 or os.readlink('/proc/self/ns/mnt') == os.readlink('/proc/1/ns/mnt'):
        raise RuntimeError('Preview input requires a private mount namespace and a desktop user')

    by_path = Path('/dev/input/by-path')
    keyboards = sorted({link.resolve(strict=True) for link in by_path.glob('*-event-kbd')})
    if not keyboards or any(key.parent != by_path.parent or
                            not key.name.removeprefix('event').isdigit() for key in keyboards):
        raise RuntimeError('No VM keyboard found for the preview')

    with tempfile.TemporaryDirectory(prefix='nextspace-input-', dir='/dev') as temporary:
        for device in [Path('/dev/uinput'), *keyboards]:
            original = device.stat()
            if not stat.S_ISCHR(original.st_mode):
                raise RuntimeError(f'{device} is not a character device')
            alias = Path(temporary) / device.name
            os.mknod(alias, stat.S_IFCHR | 0o600, original.st_rdev)
            os.chown(alias, uid, gid)
            subprocess.run(['/usr/bin/mount', '--bind', alias, device], check=True)

    environment = [f'{key}={value}' for key, value in settings.items() if key.startswith('NEXTSPACE_PREVIEW_')]
    environment.append(f'{DEVICES}={json.dumps(list(map(str, keyboards)))}')
    os.execv('/usr/bin/setpriv', [
        'setpriv', f'--reuid={uid}', f'--regid={gid}', '--init-groups', '--reset-env',
        '--', '/usr/bin/env', *environment, '/usr/bin/python3', PREVIEW,
    ])


if __name__ == '__main__':
    launch(json.loads(sys.argv[1]))
