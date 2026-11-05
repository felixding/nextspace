#!/usr/bin/env python3
"""Verify cursor alias chains through source snapshots and archive replay."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'Packaging/Debian'))
from common import digest, snapshot_sources, source_digest, source_files
from package_source import unpack_source


def run(repo, artifacts):
    artifacts.mkdir(parents=True)
    cursor_root = 'OS/Linux/usr/share/icons/NextSpace/cursors'
    specification = 'OS/Linux/usr/share/icons/NextSpace/scalable/cursors.json'
    files = source_files(repo, (cursor_root,), (specification,))
    expected = {name:source_digest(path) for name,path in files.items()}
    links = {name:str(path.readlink()) for name,path in files.items() if path.is_symlink()}
    declared = {cursor_root+'/'+name for cursor in json.loads((repo/specification).read_text())['cursors']
        for name in cursor['aliases']}
    assert set(links) == declared and len(links) == 57
    snapshot = artifacts/'snapshot/nextspace'
    snapshot_sources(files, snapshot, expected)
    (snapshot/'build-inputs.json').write_text(json.dumps(expected,indent=2)+'\n')

    def archive_source(name, root, inputs, manifest=True):
        archive = artifacts/(name+'.tar.gz')
        with tarfile.open(archive,'w:gz') as output:
            if manifest:output.add(root/'build-inputs.json',arcname='nextspace/build-inputs.json')
            for relative in inputs:output.add(root/relative,arcname='nextspace/'+relative)
        receipt = artifacts/(name+'.json')
        receipt.write_text(json.dumps(dict(inputs=inputs,source_sha256=digest(archive)),indent=2)+'\n')
        return archive,receipt

    archive,receipt = archive_source('preserved',snapshot,expected)
    restored,_ = unpack_source(archive,receipt,artifacts/'replayed')
    assert {name:str((restored/name).readlink()) for name in links} == links
    assert {name:source_digest(path) for name,path in source_files(restored,(cursor_root,),(specification,)).items()} == expected

    chain = next(name for name in links if Path(links[name]).name != (snapshot/name).resolve().name)
    rejected = []
    for name in ('flattened-alias','flattened-chain'):
        variant = artifacts/name/'nextspace';shutil.copytree(snapshot,variant,symlinks=True)
        alias = variant/chain
        data = alias.read_bytes();canonical = alias.resolve().name
        alias.unlink()
        if name == 'flattened-alias':alias.write_bytes(data)
        else:alias.symlink_to(canonical)
        assert alias.read_bytes() == data  # Resolved pixels alone cannot detect either change.
        archive,receipt = archive_source(name,variant,expected)
        try:unpack_source(archive,receipt,artifacts/(name+'-replayed'))
        except AssertionError:rejected.append(name)
        else:raise AssertionError(('Altered source alias accepted',name))

    legacy = artifacts/'legacy/nextspace';shutil.copytree(snapshot,legacy,symlinks=True)
    for name in links:
        path = legacy/name;data = path.read_bytes();path.unlink();path.write_bytes(data)
    legacy_inputs = {name:hashlib.sha256((legacy/name).read_bytes()).hexdigest() for name in expected}
    archive,receipt = archive_source('legacy-regular',legacy,legacy_inputs,manifest=False)
    unpack_source(archive,receipt,artifacts/'legacy-replayed')

    closure = artifacts/'target-closure';(closure/'module').mkdir(parents=True)
    (closure/'compile_flags.txt').write_text('-fblocks\n')
    (closure/'module/compile_flags.txt').symlink_to('../compile_flags.txt')
    collected = source_files(closure, ('module',))
    assert set(collected) == {'module/compile_flags.txt','compile_flags.txt'}
    snapshot_sources(collected, artifacts/'closure-snapshot',
        {name:source_digest(path) for name,path in collected.items()})

    # Exercise the compositor's actual source selection outside the checkout.
    # Tests must carry their rendering helper and stock image references too.
    recipe = runpy.run_path(str(repo/'Packaging/Debian/build-wayland.py'))
    component_files = recipe['source_files'](repo)
    component = artifacts/'compositor-source'
    snapshot_sources(component_files, component,
        {name:source_digest(path) for name,path in component_files.items()})
    env = dict(os.environ);env.pop('PYTHONPATH', None)
    process = subprocess.run([sys.executable, str(component/'Tests/Wayland/artwork_fidelity.py'),
        '--artifacts', str(artifacts/'compositor-artwork')], cwd=artifacts, env=env,
        capture_output=True, text=True)
    (artifacts/'compositor-artwork.log').write_text(process.stdout+process.stderr)
    assert process.returncode == 0, process.stdout+process.stderr
    cursor = subprocess.run([sys.executable, str(component/'Applications/Compositor/generate-color-cursor.py'),
        str(artifacts/'isolated-color-cursor.h'), str(component/'Libraries/gnustep/Artwork.svg')],
        cwd=artifacts, env=env, capture_output=True, text=True)
    (artifacts/'compositor-color-cursor.log').write_text(cursor.stdout+cursor.stderr)
    assert cursor.returncode == 0, cursor.stdout+cursor.stderr
    result = dict(passed=True,source_inputs=len(expected),original_aliases=len(links),
        literal_targets_preserved=True,inputs_identical=True,rejected_mutations=rejected,
        legacy_regular_archive_verified=True,transitive_source_targets_included=True,
        isolated_compositor_artwork_verified=True,isolated_compositor_color_cursor_verified=True,
        compositor_source_inputs=len(component_files))
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Source snapshots/replay: 57 literal alias chains, two rejected mutations and legacy receipts PASS')
    print('Isolated compositor sources: original artwork references and rendering helper PASS')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--artifacts',type=Path,required=True)
    args = parser.parse_args();run(args.repo.resolve(),args.artifacts.resolve())
