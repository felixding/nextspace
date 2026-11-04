#!/usr/bin/env python3
"""Render qualified shared icon artwork into a component's resource directory."""
import argparse
from pathlib import Path
from vector_art import Artwork,SVG,write_resource_images


def run(source,output,component,artwork=None):
    artwork=artwork or Artwork(source);output.mkdir(parents=True,exist_ok=True);states=0;resources=0;seen=set()
    for name,symbol in artwork.symbols.items():
        if symbol.tag!=f'{{{SVG}}}symbol' or symbol.get('data-reconstructed')!='true':
            continue
        names=symbol.get('data-'+component+'-files','').split()
        if not names:
            continue
        if seen.intersection(names) or len(set(names))!=len(names) or any(Path(n).name!=n or Path(n).suffix!='.tiff' for n in names):
            raise ValueError('Icon targets must be unique TIFF basenames')
        seen.update(names)
        logical=tuple(map(float,symbol.get('viewBox').split()[2:]));write_resource_images(artwork,name,output,names,logical)
        states+=1;resources+=len(names)
    print(f'Shared icon artwork: {states} states, {resources} resource paths, 5 backing densities')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[2]/'Applications/Artwork/Folder.svg')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--component',choices=('workspace','desktopkit','theme'),required=True)
    parser.add_argument('--nextspirit',type=Path,help='Personal-use complete NeXTSpirit sets; see Applications/Artwork/NextSpirit.json')
    args=parser.parse_args();artwork=None
    if args.nextspirit:
        from nextspirit_art import NextSpiritFolders
        artwork=NextSpiritFolders(args.source,args.nextspirit)
    run(args.source,args.output,args.component,artwork)
