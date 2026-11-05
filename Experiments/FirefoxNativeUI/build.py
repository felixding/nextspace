#!/usr/bin/env python3
"""Build only the optional Linux ARM64 adapter, never Firefox or AppKit."""
import argparse,platform,subprocess
from pathlib import Path

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--cc',default='clang')
args=parser.parse_args()
if platform.system()!='Linux' or platform.machine() not in ('aarch64','arm64'):
    parser.error('The audited Firefox binary requires Linux ARM64')
args.output.parent.mkdir(parents=True,exist_ok=True)
temporary=args.output.with_suffix(args.output.suffix+'.next')
subprocess.run([args.cc,'-shared','-fPIC','-O2','-mbranch-protection=standard',
    '-Wall','-Wextra','-Wno-unused-parameter','-Wno-unused-function',
    '-o',str(temporary),str(Path(__file__).with_name('hook.c')),'-ldl','-lpthread','-lm'],check=True)
temporary.replace(args.output)
print(args.output)
