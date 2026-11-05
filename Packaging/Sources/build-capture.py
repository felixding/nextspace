#!/usr/bin/env python3
"""Build the pinned capture portal into a package stage without installing it live."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(repo, work, stage):
    manifest=json.loads((repo/'Protocols/manifest.json').read_text())['desktop_portal']
    work.mkdir(parents=True,exist_ok=True)
    archive=work/f"xdg-desktop-portal-wlr-{manifest['version']}.tar.gz"
    if not archive.exists():
        bundled=repo/'sources'/archive.name
        if bundled.is_file():shutil.copy2(bundled,archive)
        else:subprocess.run(['curl','-fLsS',manifest['source'],'-o',str(archive)],check=True)
    assert digest(archive)==manifest['sha256'],'Portal source checksum mismatch'
    for patch in manifest['patches']:
        assert digest(repo/patch['path'])==patch['sha256'],patch['path']
    key=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()[:16]
    root=work/key;root.mkdir(exist_ok=True);source=root/'source'
    if not source.exists():
        with tempfile.TemporaryDirectory(prefix='unpack-',dir=root) as directory:
            directory=Path(directory)
            with tarfile.open(archive) as package:package.extractall(directory,filter='data')
            unpacked=directory/f"xdg-desktop-portal-wlr-{manifest['version']}"
            with (root/'patch.log').open('w') as log:
                for patch in manifest['patches']:
                    with (repo/patch['path']).open('rb') as stream:
                        subprocess.run(['patch','-p1'],cwd=unpacked,stdin=stream,stdout=log,stderr=log,check=True)
            unpacked.rename(source)
        inputs={str(p.relative_to(source)):digest(p) for p in source.rglob('*') if p.is_file()}
        (root/'source-inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
    inputs=json.loads((root/'source-inputs.json').read_text())
    assert {str(p.relative_to(source)):digest(p) for p in source.rglob('*') if p.is_file()}==inputs,'Portal source changed'
    output=root/'build'
    commands=[('configure',['meson','setup',*(['--reconfigure'] if output.exists() else []),str(output),str(source),
        '--wrap-mode=nodownload','--buildtype=release','--prefix=/usr/NextSpace',
        '--libexecdir=libexec/nextspace-wayland/portal','--datadir=share/nextspace-wayland/portal',
        '-Dsystemd=disabled','-Dman-pages=disabled','-Dsd-bus-provider=libsystemd']),
        ('compile',['meson','compile','-C',str(output)]),
        ('install',['meson','install','-C',str(output),'--no-rebuild','--destdir',str(stage)])]
    for name,command in commands:
        with (root/(name+'.log')).open('w') as log:subprocess.run(command,stdout=log,stderr=log,check=True)
    binary=stage/'usr/NextSpace/libexec/nextspace-wayland/portal/xdg-desktop-portal-wlr'
    license_path=stage/'usr/share/doc/nextspace-session-wayland/upstream-licenses/xdg-desktop-portal-wlr-LICENSE'
    license_path.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/'LICENSE',license_path)
    result=dict(manifest=manifest,source=str(source),inputs=inputs,binary=str(binary),sha256=digest(binary),stage=str(stage))
    (work/'capture-build.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(binary=str(binary),sha256=result['sha256'])))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('repo','build','stage'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args();build(args.repo.resolve(),args.build.resolve(),args.stage.resolve())
