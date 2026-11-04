#!/usr/bin/env python3
"""Generate personal-use resource artwork from the complete NeXTSpirit sets."""
import argparse
import hashlib
from pathlib import Path
import shutil
from nextspirit_art import NextSpiritArtwork
from vector_art import write_resource_images


def preserve_sources(pack, destination, artwork):
    """Retain both complete original sets and readmes with a packaged build."""
    destination.mkdir(parents=True, exist_ok=True)
    for name, expected in artwork.manifest['files'].items():
        target = destination/name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copyfile(pack/name, target)
        if target.is_symlink() or not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise ValueError('Preserved NeXTSpirit source differs: ' + str(target))
    shutil.copyfile(artwork.source, destination/'NextSpirit.json')


def run(pack, output, component, source_copy=None):
    group = 'workspace_icons' if component in ('workspace', 'desktopkit', 'theme', 'inspectors') else 'application_icons'
    art = NextSpiritArtwork(pack, group)
    if source_copy:
        preserve_sources(pack, source_copy, art)
    count = 0
    for name, case in art.entries.items():
        targets = case['targets'].get(component, [])
        if targets:
            write_resource_images(art, name, output, targets, case['logical'])
            count += len(targets)
    if not count:
        raise ValueError('No NeXTSpirit mapping for component: ' + component)
    print(f'NeXTSpirit {component}: {count} resource paths, 5 backing densities')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pack', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--component', choices=('terminal', 'preferences', 'review', 'workspace', 'desktopkit', 'theme', 'inspectors'), required=True)
    parser.add_argument('--source-copy', type=Path,
        help='Retain both complete original sets and readmes with a package')
    args = parser.parse_args()
    run(args.pack, args.output, args.component, args.source_copy)
