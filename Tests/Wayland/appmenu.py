#!/usr/bin/env python3
"""Verify application-owned app-menu metadata and versioned shell delivery."""
import argparse
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import tempfile
from integration import until
from shell import Shell

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--build', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=True)
rows, children = [], []


def check(case, passed, **evidence):
    rows.append(dict(case=case, passed=bool(passed), **evidence))
    (a.output / 'results.json').write_text(json.dumps(rows, indent=2) + '\n')
    assert passed, rows[-1]


def stop(child):
    if child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


with tempfile.TemporaryDirectory(prefix='nxs-appmenu-') as runtime:
    env = dict(os.environ, XDG_RUNTIME_DIR=runtime, WLR_BACKENDS='headless', WLR_RENDERER='pixman')
    for key in ['DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','LD_PRELOAD']:
        env.pop(key, None)
    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    broker, peer = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    parent.settimeout(5)
    compositor = subprocess.Popen([str(a.build/'nextspace-compositor'),'-c',str(child.fileno()),'-S',str(peer.fileno())], pass_fds=[child.fileno(),peer.fileno()], env=env, stdout=subprocess.PIPE, stderr=(a.output/'compositor.log').open('w'), text=True)
    children.append(compositor)
    child.close(); peer.close()

    def control(text):
        parent.send(text.encode())
        return json.loads(parent.recv(65536))

    def actor(name):
        directory=a.output/name;directory.mkdir()
        process=subprocess.Popen([str(a.build/'decoration-probe'),'--appmenu'],env=env,stdin=subprocess.PIPE,stdout=(directory/'stdout').open('w'),stderr=(directory/'stderr').open('w'),text=True)
        children.append(process)
        until(lambda:'"event":"configure"' in (directory/'stdout').read_text(), 'app-menu fixture mapping')
        return process,directory

    def send(process, directory, command):
        count=(directory/'stdout').read_text().count('"event":"sync"')
        process.stdin.write(command+'\nsync\n');process.stdin.flush()
        until(lambda:(directory/'stdout').read_text().count('"event":"sync"')>count,'app-menu request roundtrip')

    def address(shell, identifier, service, path):
        def updated():
            shell.pump()
            return next((e for e in reversed(shell.events) if e['event']=='window-appmenu' and e['id']==identifier and e['service']==service and e['path']==path),None)
        return until(updated,'versioned app-menu event')

    try:
        assert select.select([compositor.stdout],[],[],10)[0]
        env['WAYLAND_DISPLAY']=compositor.stdout.readline().strip().split('=',1)[1]
        public=subprocess.run([str(a.build/'shell-probe'),'--version19'],env=env,capture_output=True,timeout=5)
        check('public-client-cannot-bind-shell', public.returncode==2)
        shell=Shell(str(a.build/'shell-probe'),broker,env,a.output,19,version=19)
        children.append(shell.process)
        process,directory=actor('owner')
        shell.wait(lambda:any(w['pid']==process.pid for w in shell.windows.values()),'owned app-menu window')
        identifier=next(w['id'] for w in shell.windows.values() if w['pid']==process.pid)
        event=address(shell,identifier,':1.42','/test/menu')
        check('address-before-map-reaches-authorized-shell',bool(event),event=event)
        # Shell's convenience window dictionaries merge later metadata into the
        # original event. Use the retained wire log to check transaction order.
        wire=[json.loads(line) for line in (a.output/'shell-19.jsonl').read_text().splitlines()]
        window=next(i for i,e in enumerate(wire) if e['event']=='window' and e['id']==identifier)
        menu=next(i for i,e in enumerate(wire) if e==event)
        done=next(i for i,e in enumerate(wire[menu+1:],menu+1) if e['event']=='done')
        check('address-shares-window-batch',window<menu<done)
        send(process,directory,'menu :1.43 /updated/menu')
        check('address-update',bool(address(shell,identifier,':1.43','/updated/menu')))
        send(process,directory,'menu-orphan')
        check('surface-before-appmenu-release-is-safe',process.poll() is None and compositor.poll() is None)
        send(process,directory,'menu-release')
        check('release-clears-address',bool(address(shell,identifier,'','')))
        send(process,directory,'menu-orphan')
        process.stdin.write('quit\n');process.stdin.flush();process.wait(timeout=5)
        shell.wait(lambda:identifier not in shell.windows,'closed owner window')
        check('owner-exit-retires-window',process.returncode==0)
        shell.log.close()
        legacy=Shell(str(a.build/'shell-probe'),broker,env,a.output,18,version=18)
        children.append(legacy.process)
        process,directory=actor('legacy')
        legacy.wait(lambda:any(w['pid']==process.pid for w in legacy.windows.values()),'legacy window snapshot')
        legacy.snapshot()
        check('version18-client-receives-no-new-event',not any(e['event']=='window-appmenu' for e in legacy.events))
        process.stdin.write('menu-duplicate\n');process.stdin.flush();process.wait(timeout=5)
        check('duplicate-owned-surface-object-rejected',process.returncode==1,stderr=(directory/'stderr').read_text())
        legacy.snapshot()
        check('compositor-survives-rejected-client',compositor.poll() is None)
        legacy.log.close()
        print(json.dumps(dict(passed=len(rows))))
    finally:
        for process in reversed(children[1:]):
            stop(process)
        if compositor.poll() is None:
            control('quit')
        stop(compositor)
        parent.close();broker.close()
        (a.output/'cleanup.json').write_text(json.dumps([dict(pid=p.pid,exit=p.returncode) for p in children],indent=2)+'\n')
