"""Private shared-component resources, owned by the normal launch lifetime."""
import os
import errno
from pathlib import Path
import shutil
import tempfile


def private_application(executable, files, lifetime, storage=None):
    executable = Path(executable).resolve()
    storage = Path('/var/tmp/nextspace-native-ui') if storage is None else Path(storage)
    if storage.stat().st_dev != executable.stat().st_dev:
        raise ValueError('Native WebUI launch storage must share the executable filesystem')
    required = sum(len(value) for value in files.values()) + 64 * 1024**2
    if shutil.disk_usage(storage).free < required:
        raise OSError(errno.ENOSPC, 'Insufficient VM space for private browser resources', str(storage))
    temporary = tempfile.TemporaryDirectory(prefix='webui-', dir=storage)
    root = Path(temporary.name)
    def populate(source, target, prefix=''):
        target.mkdir(exist_ok=True)
        for item in source.iterdir():
            name = prefix + item.name
            destination = target / item.name
            if item == executable:
                os.link(item, destination)
            elif name in files:
                destination.write_bytes(files[name])
            elif item.is_dir() and any(key.startswith(name + '/') for key in files):
                populate(item, destination, name + '/')
            else:
                destination.symlink_to(item, target_is_directory=item.is_dir())
    try:
        populate(executable.parent, root)
    except BaseException:
        # Reclaim an interrupted copy immediately, even if the caller keeps its
        # launch lifetime open while handling the error.
        temporary.cleanup()
        raise
    lifetime.callback(temporary.cleanup)
    return root
