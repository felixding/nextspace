#!/usr/bin/env python3
"""Check the shared folder target map, generated frames and literal source aliases."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork
from artwork_reference import assert_svg_representations


def run(artifacts):
    repo=Path(__file__).resolve().parents[2];source=repo/'Applications/Artwork/Folder.svg';art=Artwork(source)
    spec=importlib.util.spec_from_file_location('folder_builder',repo/'Packaging/Sources/build-folder-images.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    group=json.loads((repo/'Tests/Wayland/artwork-originals/manifest.json').read_text())['folders']
    originals=[('closed',group['cases']['closed']),('bad',group['cases']['bad']),*(('closed',value) for value in group['aliases'].values())]
    expected={}
    for name,case in originals:
        path=Path(case['source']);component='workspace' if path.parts[0]=='Applications' else 'desktopkit' if path.parts[0]=='Frameworks' else 'theme';expected[component+'/'+path.name]=(name,path)
    actual={}
    for name in ('closed','bad'):
        for component in ('workspace','desktopkit','theme'):
            for filename in art.symbols[name].get('data-'+component+'-files','').split():
                key=component+'/'+filename;assert key not in actual,('Duplicate folder target',key);actual[key]=name
    assert actual=={key:name for key,(name,path) in expected.items()} and len(actual)==17
    artifacts.mkdir(parents=True);links={};hashes={}
    for component in ('workspace','desktopkit','theme'):
        directory=artifacts/component;directory.mkdir();sentinel=directory/'Unrelated.tiff';sentinel.write_bytes(b'Preserve unrelated resource\n');before=hashlib.sha256(sentinel.read_bytes()).hexdigest()
        for key,(name,path) in expected.items():
            if key.startswith(component+'/'):
                shutil.copy2(repo/path,directory/path.name,follow_symlinks=False)
                if (repo/path).is_symlink():links[key]=os.readlink(repo/path)
        builder.run(source,directory,component)
        assert hashlib.sha256(sentinel.read_bytes()).hexdigest()==before
        for key,(name,path) in expected.items():
            if not key.startswith(component+'/'):continue
            target=directory/path.name;assert_svg_representations(art,name,target,(48,48));hashes[key]=hashlib.sha256(target.read_bytes()).hexdigest()
            if key in links:assert target.is_symlink() and os.readlink(target)==links[key]
    assert len(links)==4
    for name in ('closed','bad'):assert len({value for key,value in hashes.items() if actual[key]==name})==1
    rejected=[]
    for label,value in (('parent-traversal','../outside.tiff'),('absolute-path','/tmp/outside.tiff'),('duplicate-target','same.tiff same.tiff')):
        root=ET.parse(source).getroot();root.find('.//*[@id="closed"]').set('data-workspace-files',value);mutated=artifacts/(label+'.svg');ET.ElementTree(root).write(mutated,encoding='unicode')
        try:builder.run(mutated,artifacts/label,'workspace')
        except ValueError:rejected.append(label)
        else:raise AssertionError(('Unsafe folder target accepted',label))
    for label,canonical in (('canonical-symlink',True),('foreign-alias',False)):
        directory=artifacts/label;directory.mkdir();foreign=directory/'foreign.tiff';foreign.write_bytes(b'Preserve foreign target\n')
        target=directory/('common_Folder.tiff' if canonical else 'common_DownloadFolder.tiff');target.symlink_to('foreign.tiff')
        try:builder.run(source,directory,'workspace')
        except ValueError:rejected.append(label)
        else:raise AssertionError(('Unsafe folder link accepted',label))
        assert foreign.read_bytes()==b'Preserve foreign target\n'
    result=dict(passed=True,resource_paths=17,representation_frames=85,source_links=links,resource_hashes=hashes,rejected_mutations=rejected,unrelated_resources_preserved=True,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),native_display_qualified=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n');print('Shared folder resources: 17 paths, 85 frames, four literal aliases and five negative controls PASS')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--artifacts',type=Path,required=True);run(parser.parse_args().artifacts)
