"""Kernel keyboard VT round trip inside the disposable native PAM fixture."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time


def activate(number):
    assert 1 <= number <= 63
    fd=os.open('/dev/tty0',os.O_RDWR)
    deadline=time.monotonic()+10
    try:
        while Path('/sys/class/tty/tty0/active').read_text().strip()!='tty'+str(number):
            assert time.monotonic()<deadline,'Timed out activating VT'+str(number)
            # logind can finish releasing the old VT after its process exits.
            fcntl.ioctl(fd,0x5606,number)  # VT_ACTIVATE
            time.sleep(.05)
    finally:os.close(fd)


def run(command,context,session,viewer):
    from integration import until
    from linux_input import Input
    artifacts=context['artifacts']/'kernel-vt';artifacts.mkdir()
    active=Path('/sys/class/tty/tty0/active')
    target=int(context['active_vt'].removeprefix('tty'))
    function_keys={**{n:58+n for n in range(1,11)},11:87,12:88}
    assert target in function_keys and active.read_text().strip()=='tty'+str(context['vt'])
    device=Input(*context['kernel_input'],artifacts)
    def user_active():
        return subprocess.check_output(['loginctl','show-session',session['environment']['XDG_SESSION_ID'],
            '--property=Active','--value'],text=True).strip()
    def round_trip():
        device.key(29,1);device.key(56,1);device.key(function_keys[target],1)
        until(lambda:active.read_text().strip()==context['active_vt'],'kernel Ctrl-Alt-Fn switches VT')
        device.key(function_keys[target],0);device.key(56,0);device.key(29,0)
        until(lambda:user_active()=='no','logind deactivates the user session')
        inactive=dict(vt=active.read_text().strip(),user_active=user_active())
        activate(context['vt']);until(lambda:user_active()=='yes','logind reactivates the user session')
        return inactive
    def locked():
        state=command('lock-state');surfaces=command('lock-surfaces')
        return state if state['locked'] and state['acknowledged'] and not state['desktop_visible'] and \
            surfaces and all(s['mapped'] for s in surfaces) else None
    try:
        assert command(f"focus {viewer['id']}")['ok']
        before={w['id'] for w in command('windows')}
        device.key(56,1);device.key(16,1);device.key(16,0);device.key(56,0)
        panel=until(lambda:next((w for w in command('windows') if w['pid']==viewer['pid'] and
            w['visible'] and w['focused'] and w['id'] not in before and w['style']&1),None),
            'kernel keyboard opens Workspace logout panel')
        assert command(f"pointer {panel['x']+panel['width']-220} {panel['y']+panel['height']-20}")['ok']
        assert command('button 272 1')['ok'];time.sleep(.02);assert command('button 272 0')['ok']
        until(lambda:not any(w['id']==panel['id'] and w['visible'] for w in command('windows')),
            'cancel kernel-keyboard logout panel')
        inactive=round_trip()
        returned=until(lambda:next((w for w in command('windows') if w['id']==viewer['id'] and
            w['pid']==viewer['pid'] and w['visible'] and w['presented'] and
            (w['buffer_width'],w['buffer_height'])==(viewer['buffer_width'],viewer['buffer_height'])),None),
            'same Workspace viewer returns after VT switch')
        assert (Path('/proc')/str(session['compositor_pid'])).exists()
        device.key(29,1);device.key(56,1);device.key(38,1)
        device.key(38,0);device.key(56,0);device.key(29,0)
        locked_before=until(locked,'kernel Ctrl-Alt-L maps the native PAM locker')
        locked_inactive=round_trip();locked_after=until(locked,'locker remains mapped after VT return')
        assert locked_before['epoch']==locked_after['epoch']
        device.text(context['secret']+'\n')
        until(lambda:not command('lock-state')['locked'] and command('lock-state')['desktop_visible'],
            'authenticated PAM unlock after VT return')
        record=dict(passed=True,kernel_command_q_verified=True,kernel_ctrl_alt_fn_switch=True,
            input_devices=device.ready,inactive=inactive,returned_vt=active.read_text().strip(),
            returned_user_active=user_active(),viewer_before=viewer,viewer_after=returned,
            compositor_pid=session['compositor_pid'],compositor_pid_unchanged=True,
            locked_before=locked_before,locked_inactive=locked_inactive,locked_after=locked_after,
            authenticated_unlock_after_vt=True,return_via_kernel_ioctl=True,full_plan_complete=False)
        (artifacts/'results.json').write_text(json.dumps(record,indent=2)+'\n')
        return record
    finally:
        if active.read_text().strip()!='tty'+str(context['vt']):activate(context['vt'])
        device.close()
