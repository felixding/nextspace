#!/usr/bin/env python3
"""Check native gamma capability and failure replies without pretending headless LUT support."""
import argparse
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import tempfile
from shell import Shell


def run(compositor, probe, artifacts, workspace_probe=None):
    artifacts.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='nextspace-gamma-') as runtime:
        env = dict(os.environ, XDG_RUNTIME_DIR=runtime, WLR_BACKENDS='headless',
            WLR_HEADLESS_OUTPUTS='2', WLR_RENDERER='pixman')
        for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'WAYLAND_SOCKET'): env.pop(key, None)
        control, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        broker, capability = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        control.settimeout(5)
        with (artifacts / 'compositor.log').open('w') as log:
            server = subprocess.Popen([compositor, '-c', str(child.fileno()), '-S', str(capability.fileno())],
                env=env, pass_fds=[child.fileno(), capability.fileno()], stdout=subprocess.PIPE, stderr=log, text=True)
        child.close(); capability.close(); owners = []
        def command(value):
            control.sendall(value.encode()); return json.loads(control.recv(65536))
        try:
            assert select.select([server.stdout], [], [], 10)[0]
            line = server.stdout.readline().strip(); assert line.startswith('WAYLAND_DISPLAY=')
            env['WAYLAND_DISPLAY'] = line.split('=', 1)[1]
            owner = Shell(probe, broker, env, artifacts, 0, version=18); owners.append(owner)
            before = len(owner.events); batches = owner.output_batches; owner.send('outputs')
            owner.wait(lambda: owner.output_batches > batches, 'gamma inventory batch')
            gamma = {e['id']:e for e in owner.events[before:] if e['event']=='output-gamma'}
            assert len(gamma)==len(owner.outputs)==2
            assert all(e['size']==0 and all(e[k]==1 for k in ('red','green','blue','brightness')) for e in gamma.values())
            head = next(iter(gamma))
            requests = [(head,1,1,1,1), (head,0.5,1.5,2,0.75), (head,1,1,1,0),
                (0,1,1,1,1), (4294967295,1,1,1,1), (head,0,1,1,1),
                (head,-1,1,1,1), (head,11,1,1,1), (head,1,1,1,-1), (head,1,1,1,3)]
            results = []
            for serial, values in enumerate(requests, 1):
                before = len(owner.events); owner.send('gamma '+str(serial)+' '+' '.join(map(str,values)))
                reply = owner.wait(lambda: next((e for e in owner.events[before:]
                    if e['event']=='gamma-result' and e['serial']==serial),None), 'correlated gamma rejection')
                assert not reply['success'] and reply['reason'], reply
                current = {e['id']:e for e in owner.events[before:] if e['event']=='output-gamma'}
                assert current==gamma, (values,current)
                assert server.poll() is None
                results.append(dict(request=values,reply=reply))
            owner.stop(); owners.remove(owner)
            legacy = Shell(probe, broker, env, artifacts, 1, version=16); owners.append(legacy)
            batches = legacy.output_batches; legacy.send('outputs')
            legacy.wait(lambda: legacy.output_batches>batches, 'older shell output inventory')
            assert len(legacy.outputs)==2 and not any(e['event'].startswith('gamma-') or
                e['event']=='output-gamma' for e in legacy.events)
            legacy.stop(); owners.remove(legacy)
            rpc_cases = []
            if workspace_probe:
                for mode in range(4):
                    client = Shell(workspace_probe, broker, env, artifacts, mode+2,
                        workspace_mode=mode); owners.append(client)
                    client.wait(lambda: len(client.outputs)==2, 'Objective-C gamma inventory')
                    assert all(h['gamma_size']==0 and all(h['gamma'][k]==1 for k in
                        ('red','green','blue','brightness')) for h in client.outputs.values())
                    settings = dict(red=0.5,green=1.5,blue=2,brightness=0.75)
                    cases = [(head,settings), (head,dict(settings,red=-1)),
                        (head,dict(settings,red='invalid')), (0,settings), ('invalid',settings)]
                    for identifier, values in cases:
                        before = len(client.events)
                        client.send(json.dumps(dict(action='gamma',id=identifier,settings=values)))
                        reply = client.wait(lambda: next((e for e in client.events[before:]
                            if e['event']=='gamma-result'),None), 'Objective-C gamma result')
                        assert not reply['success'], reply
                        if identifier==head and values==settings:
                            assert reply['serial']>0 and reply['reason'] and all(v==1 for v in reply['gamma'].values())
                        rpc_cases.append(dict(mode=mode,request=dict(id=identifier,settings=values),reply=reply))
                    client.stop(); owners.remove(client)
            (artifacts/'results.json').write_text(json.dumps(dict(rejections=results,
                rpc_cases=rpc_cases,unsupported_heads=2,older_protocol_works=True,hardware_gamma_tested=False),indent=2)+'\n')
            print('Native gamma capability, correlated rejection and older shell protocol: PASS')
        finally:
            for owner in owners: owner.stop()
            if server.poll() is None: command('quit'); server.wait(timeout=5)
            server.stdout.close();control.close();broker.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compositor',required=True);parser.add_argument('--probe',required=True)
    parser.add_argument('--artifacts',required=True,type=Path)
    parser.add_argument('--workspace-probe')
    args=parser.parse_args();run(args.compositor,args.probe,args.artifacts,args.workspace_probe)
