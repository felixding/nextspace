"""Start the toolkit preview through the ordinary desktop launcher."""
from pathlib import Path
import subprocess


def launch(stage, root, runtime, session_env, children):
    adapters = stage / 'toolkit-ui'
    if not adapters.is_dir():
        return
    config = runtime / 'toolkit-config'
    config.mkdir()
    fixture = root / 'Toolkit preview.txt'
    directory = root / 'Toolkit files'
    directory.mkdir()
    for index in range(1, 97):
        (directory / f'Example {index:03d}.txt').touch()
    fixture.write_text(''.join(f'{line:03d}  NEXTSPACE toolkit preview\n' for line in range(1, 181)))
    settings = dict(
        NEXTSPACE_SCROLLER_LIBDIR=str(adapters),
        NEXTSPACE_GTK3_GEOMETRY_LIBRARY=str(stage / 'native-ui/libnextspace-gtk3-geometry.so.1'),
        NEXTSPACE_NATIVE_UI_PROVIDER=str(stage / 'native-ui/libnextspace-native-ui-gnustep.so.1'),
        XDG_CONFIG_HOME=str(config),
        XDG_SESSION_TYPE='wayland',
        XDG_CURRENT_DESKTOP='NEXTSPACE',
        GDK_BACKEND='wayland',
        QT_QPA_PLATFORM='wayland',
        LD_LIBRARY_PATH=':'.join(str(path) for path in (
            stage / 'native-ui', stage, '/Library/Libraries', '/usr/NextSpace/lib'))
    )
    env = dict(session_env, **settings)
    bootstrap = '/workspace/Libraries/ForeignScrollers/session.sh'
    terminal = adapters / 'konsole'
    apps = (
        ('konsole', [str(terminal), '--separate', '-e', 'sh', '-c',
                     'cat "$1"; exec /bin/bash --noprofile --norc', 'preview', str(fixture)]),
        ('mousepad', ['mousepad', '--disable-server', str(fixture)]),
        ('kate', ['kate', '--new', str(fixture)]),
        ('thunar', ['thunar', str(directory)])
    )
    tracked = {}
    for name, argv in apps:
        if not (Path('/usr/bin') / name).is_file():
            print(f'Preview app unavailable: {name}', flush=True)
            continue
        command = ['sh', '-c', '. "$1"; shift; exec "$@"', name, bootstrap, *argv]
        with (root / f'{name}.stdout').open('w') as out, (root / f'{name}.stderr').open('w') as err:
            process = subprocess.Popen(command, env=env, stdout=out, stderr=err)
            tracked[('org.kde.' if name in ('konsole', 'kate') else '') + name] = process
            children.append(process)
    return tracked
