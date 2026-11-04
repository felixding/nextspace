"""Exercise overwrite, skip and Stop replies against owned existing files."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from gnustep import private_defaults


def snapshot(path):
    if not path.exists() and not path.is_symlink():
        return None
    stat = path.lstat()
    return dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                inode=stat.st_ino, mtime_ns=stat.st_mtime_ns, mode=stat.st_mode,
                symlink=os.readlink(path) if path.is_symlink() else None)


def run(tool, artifacts):
    artifacts.mkdir(parents=True)
    cases = []
    for operation in ('Copy', 'Link', 'Move'):
        for action, reply in (('stop', 't'), ('disconnect', ''), ('skip', 'S'), ('overwrite', 'O')):
            directory = artifacts / (operation.lower() + '-' + action)
            source, target = directory / 'source', directory / 'target'
            source.mkdir(parents=True)
            target.mkdir()
            names = ('first.txt', 'second.txt')
            for name in names:
                (source / name).write_bytes(('Source ' + name + '\n').encode())
                (target / name).write_bytes(('Existing destination ' + name + '\n').encode())
            before = {scope + '/' + name: snapshot(path / name)
                      for scope, path in (('source', source), ('target', target)) for name in names}
            env = dict(os.environ, HOME=str(directory), Files='("first.txt", "second.txt")')
            private_defaults(env, directory)
            command = [str(tool), '-Operation', operation, '-Source', str(source.resolve()),
                       '-Destination', str(target.resolve())]
            result = subprocess.run(command, input=reply + '\n' if reply else '', text=True, env=env,
                                    capture_output=True, timeout=10)
            (directory / 'stdout.log').write_text(result.stdout)
            (directory / 'stderr.log').write_text(result.stderr)
            after = {scope + '/' + name: snapshot(path / name)
                     for scope, path in (('source', source), ('target', target)) for name in names}
            failure = None
            try:
                assert result.returncode == 0
                assert any(line.startswith('E') for line in result.stdout.splitlines()), 'Existing destination was not encountered'
                if action in ('stop', 'disconnect', 'skip'):
                    assert after == before, 'Existing files changed after ' + action
                else:
                    for name in names:
                        assert after['target/' + name]['sha256'] == before['source/' + name]['sha256']
                        if operation == 'Move':
                            assert after['source/' + name] is None
                        else:
                            assert after['source/' + name] == before['source/' + name]
                        assert (after['target/' + name]['symlink'] is not None) == (operation == 'Link')
                assert ('Operation Stopped' in result.stdout) == (action in ('stop', 'disconnect'))
            except AssertionError as error:
                failure = str(error)
            row = dict(operation=operation, action=action, passed=failure is None,
                       failure=failure, returncode=result.returncode, before=before, after=after)
            cases.append(row)
            (directory / 'result.json').write_text(json.dumps(row, indent=2) + '\n')
    result = dict(passed=all(c['passed'] for c in cases), cases=cases,
                  tool_sha256=hashlib.sha256(Path(tool).read_bytes()).hexdigest(), owned_fixtures_only=True)
    (artifacts / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tool', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.tool, args.artifacts)
    assert result['passed'], result
    print('Copy/Link/Move Stop, disconnected controller, Skip and Overwrite: twelve cases PASS')
