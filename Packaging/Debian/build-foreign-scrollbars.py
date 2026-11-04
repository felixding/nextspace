#!/usr/bin/env python3
"""Build the optional GTK/Qt adapters against an installed native NEXTSPACE SDK."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

from common import digest, source_digest, source_files, snapshot_sources, write_binary

PACKAGE = 'nextspace-foreign-scrollbars'


def build(repo, work, output, version):
    subprocess.run(['dpkg','--validate-version',version],check=True)
    work.mkdir(parents=True)
    output.mkdir(parents=True,exist_ok=True)
    files=source_files(repo,('Libraries/ForeignScrollers','Tests/ForeignScrollers'),
        ['LICENSE','Packaging/Debian/build-foreign-scrollbars.py','Packaging/Debian/common.py'])
    expected={name:source_digest(path) for name,path in sorted(files.items())}
    snapshot=work/'source'
    snapshot_sources(files,snapshot,expected)
    (snapshot/'build-inputs.json').write_text(json.dumps(expected,indent=2)+'\n')
    stage=work/'stage'
    commands=[['cmake','-S',str(snapshot/'Libraries/ForeignScrollers'),'-B',str(work/'build'),
               '-DCMAKE_OBJC_COMPILER=clang','-DCMAKE_BUILD_TYPE=Release'],
              ['cmake','--build',str(work/'build'),'-j',os.environ.get('JOBS','2')],
              ['cmake','--install',str(work/'build')]]
    with (work/'build.log').open('w') as log:
        for command in commands:
            subprocess.run(command,env=dict(os.environ,DESTDIR=str(stage)),stdout=log,stderr=log,check=True)
    architecture=subprocess.check_output(['dpkg','--print-architecture'],text=True).strip()
    debian=work/'debian';debian.mkdir()
    maintainer='NEXTSPACE local build <root@localhost>'
    (debian/'control').write_text(f'Source: {PACKAGE}\nMaintainer: {maintainer}\n\nPackage: {PACKAGE}\nArchitecture: any\nDescription: NEXTSPACE native scrollbar adapters\n')
    overrides=debian/'shlibs.local'
    overrides.write_text('libgnustep-gui 0 nextspace-runtime\nlibgnustep-base 1.31 nextspace-runtime\n'
        'libobjc 4.6 nextspace-runtime\n'+f'libnextspace-native-scroller 1 {PACKAGE} (= {version})\n')
    libraries=stage/'usr/NextSpace/lib/nextspace-scrollbars'
    elfs=[path for path in stage.rglob('*') if path.is_file() and not path.is_symlink()
          and path.read_bytes()[:4]==b'\x7fELF']
    command=['dpkg-shlibdeps','-O','-L'+str(overrides),'-l'+str(libraries),
             '-l/usr/NextSpace/lib','-l/Library/Libraries','-x'+PACKAGE]+['-e'+str(path) for path in elfs]
    # Identify the staging root so $ORIGIN resolves as it will after install.
    (stage/'DEBIAN').mkdir()
    dependencies=subprocess.run(command,cwd=work,text=True,capture_output=True)
    (stage/'DEBIAN').rmdir()
    (work/'dependencies.log').write_text(dependencies.stdout+dependencies.stderr)
    dependencies.check_returncode()
    depends=dependencies.stdout.strip().removeprefix('shlibs:Depends=')
    docs=stage/'usr/share/doc'/PACKAGE;docs.mkdir(parents=True)
    shutil.copy2(snapshot/'LICENSE',docs/'LICENSE.nextspace')
    shutil.copy2(snapshot/'Libraries/ForeignScrollers/README.md',docs/'README.md')
    shutil.copy2(snapshot/'build-inputs.json',docs/'build-inputs.json')
    name=f'{PACKAGE}_{version}_{architecture}'
    package=output/(name+'.deb')
    result=write_binary(stage,package,dict(Package=PACKAGE,Version=version,Architecture=architecture,
        Section='gui',Priority='optional',Maintainer=maintainer,Depends=depends),
        'Use the existing NEXTSPACE NSScroller in GTK3, GTK4 and Qt6 Widgets applications.\n'
        'Applications keep their binaries, text direction, content and scroll models.')
    assert all(source_digest(snapshot/name)==value for name,value in expected.items()),'Changed source snapshot'
    source=output/(name+'.source.tar.gz')
    with tarfile.open(source,'w:gz') as archive:
        archive.add(snapshot,arcname='nextspace')
    receipt=dict(result,package=PACKAGE,version=version,architecture=architecture,dependencies=depends,
        inputs=expected,source=str(source),source_sha256=digest(source))
    (output/(name+'.json')).write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--build-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--version',required=True)
    args=parser.parse_args()
    print(json.dumps(build(args.repo.resolve(),args.build_dir.resolve(),args.output.resolve(),args.version),indent=2))
