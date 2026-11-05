"""Shared Debian package payload and receipt helpers."""
import hashlib
from pathlib import Path
import os
import shutil
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(repo, cache, relative, url, checksum):
    archive = cache / Path(relative).name
    if not archive.exists():
        bundled = repo / relative
        if bundled.is_file():
            shutil.copyfile(bundled, archive)
        else:
            subprocess.run(['curl', '-fLsS', url, '-o', str(archive)], check=True)
    if digest(archive) != checksum:
        raise ValueError('Source archive checksum: ' + relative)
    return archive


def source_digest(path):
    """Record a source link's literal target instead of its resolved contents."""
    return 'link:' + os.readlink(path) if path.is_symlink() else digest(path)


def snapshot_sources(files, destination, expected):
    for name, path in files.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target, follow_symlinks=False)
    root = destination.resolve()
    for name, value in expected.items():
        target = destination / name
        assert target.is_file() and target.resolve().is_relative_to(root) and \
            source_digest(target) == value, ('Modified or incomplete source snapshot', name)


def run(command, log, **kwargs):
    subprocess.run(command, stdout=log, stderr=log, check=True, **kwargs)


def source_files(repo, directories, extra=()):
    """Collect clean repository inputs, also working in an unpacked source tree."""
    if (repo / '.git').exists():
        names = subprocess.check_output(['git', '-c', 'safe.directory=' + str(repo), '-C', str(repo),
            'ls-files', '--cached', '--others', '--exclude-standard', '-z', '--', *directories]).split(b'\0')
        paths = [repo / os.fsdecode(name) for name in names if name]
    else:
        paths = [path for directory in directories for path in (repo / directory).rglob('*')]
    paths.extend(repo / relative for relative in extra)
    result = {}
    def include(path, required=False):
        relative = path.relative_to(repo)
        if any(part.startswith('.') or part in ('obj', '__pycache__', 'autom4te.cache') or
               part.endswith(('.app', '.framework', '.preferences', '.wsprefs', '.viewer', '.bundle'))
               for part in relative.parts):
            if required:
                raise ValueError('Source link target is excluded: ' + str(path))
            return
        if not path.is_file():
            if required:
                raise ValueError('Source link has no file target: ' + str(path))
            return
        if not path.resolve().is_relative_to(repo):
            raise ValueError('Source link leaves the repository: ' + str(path))
        if str(relative) in result:
            return
        result[str(relative)] = path
        if path.is_symlink():
            include(Path(os.path.abspath(path.parent / os.readlink(path))), required=True)
    for path in paths:
        include(path)
    return dict(sorted(result.items()))


def write_binary(root, output, fields, description, conffiles=()):
    """Package an already assembled tree, preserving link targets in receipts."""
    if output.exists():
        raise FileExistsError(output)
    hashes, links = {}, {}
    for path in sorted(root.rglob('*')):
        relative = str(path.relative_to(root))
        if path.is_symlink():
            links[relative] = os.readlink(path)
        elif path.is_file():
            hashes[relative] = digest(path)
    installed_size = (sum(p.stat().st_size for p in root.rglob('*') if p.is_file() and not p.is_symlink()) + 1023) // 1024
    control = root / 'DEBIAN'
    control.mkdir()
    if conffiles:
        for name in conffiles:
            if not name.startswith('/') or name[1:] not in hashes:
                raise ValueError('Conffile must name a packaged regular file: ' + name)
        (control / 'conffiles').write_text(''.join(name + '\n' for name in conffiles))
    values = dict(fields, **{'Installed-Size': str(installed_size)})
    for name, value in values.items():
        if '\n' in value or '\r' in value:
            raise ValueError('Invalid Debian control field: ' + name)
    (control / 'control').write_text(''.join(f'{name}: {value}\n' for name, value in values.items()) +
        'Description: ' + description.splitlines()[0] + '\n' +
        ''.join(' ' + line + '\n' for line in description.splitlines()[1:]))
    subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(root), str(output)], check=True)
    return dict(binary=str(output), binary_sha256=digest(output), payload_hashes=hashes, payload_links=links)
