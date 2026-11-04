#!/usr/bin/env python3
"""Check full-resolution NeXTSpirit imports for the user's personal preview."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
import sys
import tempfile
from PIL import ImageChops
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'Packaging/Sources'))
from nextspirit_art import NextSpiritArtwork, NextSpiritFolders


def run(pack, artifacts):
    source = Path(__file__).resolve().parents[2] / 'Applications/Artwork/Folder.svg'
    art = NextSpiritFolders(source, pack)
    records = []
    apps = NextSpiritArtwork(pack)
    workspace = NextSpiritArtwork(pack, 'workspace_icons')
    for artwork, names in ((art, ('closed', 'open', 'bad')), (apps, tuple(apps.entries)),
            (workspace, tuple(workspace.entries))):
        for name in names:
            master = artwork.images[name]
            logical = tuple(map(int, artwork.symbols[name].get('data-logical-size', '48 48').split()))
            entry = artwork.entries.get(name, {})
            maximum = entry.get('pixels', 1024)
            if entry.get('composition') == 'neighborhood':
                assert entry['source'] == 'set1/Home01.icns' and maximum == 1024
                maximum = 1536  # Two original 1024-pixel houses in their 32/48 layout.
            assert master.size == tuple(round(maximum * axis / max(logical)) for axis in logical)
            for size in (48, 60, 72, 84, 96, 384, maximum):
                target = tuple(round(axis * size / maximum) for axis in master.size)
                actual = artwork.render(name, target)
                assert actual.size == target
                if size == maximum:
                    assert actual.tobytes() == master.tobytes()
                records.append(dict(state=name, size=size,
                    pixel_sha256=hashlib.sha256(actual.tobytes()).hexdigest()))
    assert ImageChops.difference(art.images['closed'].getchannel('A'),
        art.images['bad'].getchannel('A')).getbbox() is None
    rejected = []
    try:
        art.render('closed', 1025)
    except ValueError:
        rejected.append('enlargement')
    else:
        raise AssertionError('Accepted enlargement')
    with tempfile.TemporaryDirectory(prefix='nextspirit-import-') as temporary:
        root = Path(temporary)
        manifest = json.loads(art.source.read_text())
        first = root / next(iter(manifest['files']))
        first.parent.mkdir(parents=True)
        first.write_bytes(b'Altered source')
        try:
            NextSpiritFolders(source, root)
        except ValueError:
            rejected.append('altered-source')
        else:
            raise AssertionError('Accepted altered source')
        first.unlink()
        try:
            NextSpiritFolders(source, root)
        except FileNotFoundError:
            rejected.append('incomplete-set')
        else:
            raise AssertionError('Accepted incomplete set')
    with tempfile.TemporaryDirectory(prefix='nextspirit-preserved-source-') as temporary:
        destination = Path(temporary)/'sources';bad = destination/'set1/DefaultApp.icns'
        bad.parent.mkdir(parents=True);bad.write_bytes(b'Altered preserved artwork')
        process = subprocess.run([sys.executable,str(source.parents[2]/'Packaging/Sources/build-nextspirit-images.py'),
            '--pack',str(pack),'--component','terminal','--output',str(Path(temporary)/'images'),
            '--source-copy',str(destination)],capture_output=True,text=True)
        assert process.returncode != 0 and 'Preserved NeXTSpirit source differs:' in process.stderr
        assert bad.read_bytes() == b'Altered preserved artwork'
        rejected.append('altered-preserved-source')
    artifacts.mkdir(parents=True)
    result = dict(passed=True, source_manifest_sha256=hashlib.sha256(art.source.read_bytes()).hexdigest(),
        verified_source_files=len(manifest['files']), frames=records, rejected_mutations=rejected,
        unrestricted_redistribution_qualified=False, full_plan_complete=False)
    (artifacts / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(f'NeXTSpirit: 48 icons, two readmes, {len(records)} master-derived frames and {len(rejected)} negative controls PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pack', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    args = parser.parse_args()
    run(args.pack, args.artifacts)
