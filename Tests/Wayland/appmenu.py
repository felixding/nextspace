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
p.add_argument('--workspace-probe',type=Path,help='Also verify Workspace metadata and active-menu role handoff')
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
        send(process,directory,'menu-duplicate');shell.snapshot()
        current=next(e for e in reversed(shell.events) if e['event']=='window-appmenu' and e['id']==identifier)
        check('overlapping-objects-preserve-first-owner',process.poll() is None and current['service']==':1.43' and current['path']=='/updated/menu',event=current)
        send(process,directory,'menu-promote')
        check('release-promotes-surviving-object',bool(address(shell,identifier,':1.44','/replacement/menu')))
        send(process,directory,'menu-replace :1.45 /new/menu')
        check('replacement-before-release-survives',process.poll() is None and bool(address(shell,identifier,':1.45','/new/menu')))
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
        send(process,directory,'menu-duplicate')
        process.stdin.write('quit\n');process.stdin.flush();process.wait(timeout=5)
        check('overlapping-objects-preserve-legacy-client',process.returncode==0,stderr=(directory/'stderr').read_text())
        legacy.snapshot()
        check('compositor-survives-object-replacement',compositor.poll() is None)
        legacy.log.close()
        if a.workspace_probe:
            menu_peer,menu_endpoint=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
            menu_peer.setblocking(False)
            owner=Shell(str(a.workspace_probe),broker,env,a.output,'workspace-menu',workspace_mode=0,menu_endpoint=menu_endpoint)
            children.append(owner.process);menu_endpoint.close()
            def receive(operation,identifier=None,accepted=True):
                def read():
                    owner.pump()
                    if not select.select([menu_peer],[],[],0)[0]:return None
                    packet=json.loads(menu_peer.recv(8192))
                    assert packet['operation']==operation,packet
                    if identifier is not None:assert packet['window']==identifier,packet
                    if accepted is not None:menu_peer.send(json.dumps(dict(accepted=accepted)).encode())
                    return packet
                return until(read,'Workspace active-menu handoff')
            receive('clear')
            host_pid=os.getpid()
            menu_peer.send(json.dumps(dict(operation='host',pid=host_pid)).encode())
            first,first_dir=actor('workspace-first')
            owner.wait(lambda:any(w['pid']==first.pid for w in owner.windows.values()),'Workspace first window')
            first_id=next(w['id'] for w in owner.windows.values() if w['pid']==first.pid)
            message=receive('bind',first_id)
            check('workspace-authenticated-menu-metadata',message['pid']==first.pid and message['service']==':1.42' and message['path']=='/test/menu')
            owner.wait(lambda:any(e.get('event')=='menu-selection' and e['host_pid']==host_pid for e in owner.events),'acknowledged host identity')
            check('session-host-notice-selects-acknowledged-menu',True)
            second,second_dir=actor('workspace-second')
            owner.wait(lambda:any(w['pid']==second.pid for w in owner.windows.values()),'Workspace second window')
            second_id=next(w['id'] for w in owner.windows.values() if w['pid']==second.pid)
            check('workspace-focus-selects-second-menu',receive('bind',second_id)['pid']==second.pid)
            control('focus '+str(first_id))
            check('workspace-focus-restores-first-menu',receive('bind',first_id)['pid']==first.pid)
            send(first,first_dir,'menu :1.43 /changed/menu')
            message=receive('bind',first_id)
            check('workspace-active-address-update',message['service']==':1.43' and message['path']=='/changed/menu')
            send(first,first_dir,'menu :1.44 /rejected/menu')
            receive('bind',first_id,accepted=False);receive('clear')
            owner.snapshot()
            check('rejected-active-address-clears-previous-menu',not select.select([menu_peer],[],[],.05)[0])
            send(first,first_dir,'menu :1.45 /recovered/menu')
            receive('bind',first_id,accepted=None)
            control('focus '+str(second_id));control('focus '+str(first_id))
            owner.snapshot()
            check('workspace-remains-responsive-during-delayed-menu-reply',owner.process.poll() is None)
            before=len(owner.events)
            menu_peer.send(json.dumps(dict(operation='host',pid=host_pid+1)).encode())
            owner.wait(lambda:any(e.get('event')=='menu-selection' for e in owner.events[before:]),'host replacement during pending reply')
            check('host-replacement-does-not-acknowledge-pending-selection',
                [e for e in owner.events[before:] if e.get('event')=='menu-selection'][-1]['host_pid']==0)
            menu_peer.send(json.dumps(dict(accepted=True)).encode())
            owner.snapshot()
            owner.wait(lambda:any(e.get('event')=='menu-selection' and e['host_pid']==host_pid+1 for e in owner.events[before:]),'replacement host selection')
            check('unchanged-selection-uses-replacement-session-host',True)
            check('pending-focus-updates-coalesce-to-latest-address',not select.select([menu_peer],[],[],.05)[0])
            control('move '+str(first_id)+' 100 100')
            owner.snapshot()
            check('unchanged-window-metadata-does-not-rebind',not select.select([menu_peer],[],[],.05)[0])
            before=len(owner.events);menu_peer.send(json.dumps(dict(operation='host',pid=0)).encode())
            owner.wait(lambda:any(e.get('event')=='menu-selection' and e['host_pid']==0 for e in owner.events[before:]),'host unavailable notification')
            check('host-unavailable-clears-presentation-without-closing-shell',owner.process.poll() is None)
            send(first,first_dir,'menu-release')
            check('workspace-address-removal-clears-menu',receive('clear')['operation']=='clear')
            control('focus '+str(second_id));receive('bind',second_id)
            second.stdin.write('quit\n');second.stdin.flush();second.wait(timeout=5)
            receive('clear')
            check('workspace-closed-owner-retires-menu',second.poll()==0)
            menu_peer.close()
            owner.snapshot()
            check('menu-peer-loss-preserves-workspace',owner.process.poll() is None)
            owner.send('quit');owner.process.wait(timeout=5);owner.log.close()
        print(json.dumps(dict(passed=len(rows))))
    finally:
        for process in reversed(children[1:]):
            stop(process)
        if compositor.poll() is None:
            control('quit')
        stop(compositor)
        parent.close();broker.close()
        (a.output/'cleanup.json').write_text(json.dumps([dict(pid=p.pid,exit=p.returncode) for p in children],indent=2)+'\n')
