#!/usr/bin/env python3
"""Run fake-bus power UI tests as a real greetd/PAM user in a disposable guest."""
import argparse
import json
import os
import shutil
from pathlib import Path

import login_pam
from lock_logind_guest import UserSessionProcess


def validate(context,candidate,supervised=False):
    account=context['user_account']
    artifacts=context['artifacts']/'power-ui';artifacts.mkdir()
    os.chown(artifacts,account.pw_uid,account.pw_gid)
    sources=artifacts/'sources';sources.mkdir()
    for name in ('workspace_power_pam.py','workspace_power_session.py','workspace_power.py','login_native_pam.py',
                 'login_pam.py','lock_logind_guest.py','power-service-probe.c','alerts.py','workspace.py'):
        shutil.copy2(candidate/'source/Tests/Wayland'/name,sources/name)
    shutil.copy2(candidate/'workspace.py',sources/'workspace-wrapper.py')
    environment=dict(os.environ,**context['environment'])
    environment.update(PATH='/usr/NextSpace/bin:/usr/local/bin:/usr/bin:/bin',HOME=str(context['user_home']),
        GNUSTEP_CONFIG_FILE=str(candidate/'GNUstep.conf'),
        LD_LIBRARY_PATH=str(candidate/'candidate/lib')+':/usr/NextSpace/lib:/usr/local/lib',
        GTK_A11Y='none',GSK_RENDERER='cairo')
    arguments=['python3',str(candidate/'source/Tests/Wayland/workspace_power.py'),
        '--compositor',str(candidate/'candidate/bin/nextspace-compositor'),
        '--workspace',str(candidate/'workspace.py'),'--probe',str(candidate/'candidate/bin/WorkspaceProbe'),
        '--artifacts',str(artifacts/'workflow')]
    if supervised:
        arguments=['python3',str(candidate/'source/Tests/Wayland/workspace_power_session.py'),
            '--candidate',str(candidate),'--artifacts',str(artifacts/'workflow'),
            '--expected-session',context['session']]
    process=UserSessionProcess(context,arguments,environment,artifacts/'workflow.log')
    assert process.wait(timeout=180)==0,(artifacts/'workflow.log').read_text()[-5000:]
    power=json.loads((artifacts/('workflow/ui/results.json' if supervised else 'workflow/workspace/power/results.json')).read_text())
    assert power['complete'] and len(power['cases'])==9 and not power['actual_power_calls']
    assert all(row['desktop_preserved'] for row in power['cases'] if row['behavior']!='accept')
    result=dict(session=context['session'],driver_pid=process.pid,uid=account.pw_uid,
        inherited_pam_session_verified=True,native=power,
        scope='Real PAM/logind user scope and unprivileged native Workspace UI; every power method uses the owned fake bus. Actual power authorization and shutdown remain untested.')
    if supervised:result['supervised']=json.loads((artifacts/'workflow/sessions.json').read_text())
    (artifacts/'scope.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('candidate','greetd','probe','wrapper','artifacts'):parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--disposable-guest',action='store_true')
    parser.add_argument('--supervised',action='store_true')
    args=parser.parse_args()
    login_pam.run(args.greetd.resolve(),args.probe.resolve(),args.wrapper.resolve(),args.artifacts.resolve(),
        args.disposable_guest,user_hook=lambda context:validate(context,args.candidate.resolve(),args.supervised))
