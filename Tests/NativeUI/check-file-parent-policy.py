"""Real foreign-parent modal focus, background refusal and export lifetime."""
import argparse
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Wayland'))
from native_number_fields import ChromiumNumbers

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--fixture',required=True,type=Path)
args=parser.parse_args();root=args.fixture
test=object.__new__(ChromiumNumbers);test.root=root;test.results=[]
env=dict(os.environ,**json.loads((root/'runtime.json').read_text()),GDK_BACKEND='wayland')
env.pop('LD_PRELOAD',None)
portal_pid=next(json.loads(row)['pid'] for row in (root/'file-portal.jsonl').read_text().splitlines()
                if json.loads(row)['event']=='ready')
def receive(process):
    assert select.select([process.stdout],[],[],15)[0], 'Owned client response'
    return json.loads(process.stdout.readline())
def send(process,value):
    process.stdin.write(value+'\n');process.stdin.flush()
def panel():
    return next((w for w in test.command('windows') if w['pid']==portal_pid and w['visible']),None)
def focused():
    return next((w['id'] for w in test.command('windows') if w['focused']),None)
children=[]
try:
    parent=subprocess.Popen(['python3','/workspace/Tests/Wayland/foreign_parent_child.py'],env=env,
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(root/'foreign-parent-child.stderr').open('w'),text=True)
    children.append(parent);exported=receive(parent)['handle']
    owner=test.until(lambda:next((w for w in test.command('windows') if w['pid']==parent.pid
        and w['title']=='Foreign parent source' and w['visible']),None),'exporting original GTK window')
    test.until(lambda:focused()==owner['id'],'original GTK parent focus')
    native_id=None
    for label,identifier,expected_parent in [
            ('foreground-parent',exported,owner['id']),('background-parent',exported,owner['id']),
            ('unparented','',0),('invalid-parent','wayland:not-an-exported-handle',0)]:
        if label=='background-parent':
            send(parent,'other');receive(parent)
            test.until(lambda: any(w['pid']==parent.pid and w['title']=='Other focused window'
                and w['focused'] for w in test.command('windows')),'independent window focus')
        before=focused()
        client=subprocess.Popen(['python3','/workspace/Tests/NativeUI/file-portal-client.py','OpenFile',
            '--title',label,'--parent-window',identifier],env=env,stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=(root/(label+'-client.stderr')).open('w'),text=True)
        children.append(client);assert receive(client)['event']=='request'
        window=test.until(panel,label+' native modal')
        test.check(label+'-preserves-real-parent',test.until(
            lambda: panel() and panel()['parent_id']==expected_parent,label+' original parent'))
        if native_id is None:native_id=window['id']
        else:test.check(label+'-reuses-original-native-panel',window['id']==native_id)
        if label=='foreground-parent':
            test.check(label+'-activates-native-modal',test.until(lambda:panel() and panel()['focused'],label+' focus'))
        else:
            time.sleep(.2)
            test.check(label+'-cannot-steal-unrelated-keyboard-focus',focused()==before and not panel()['focused'])
        send(client,'close');test.until(lambda:client.poll() is not None,label+' original request closes')
        test.until(lambda:not panel(),label+' native modal closes')
        children.remove(client)
    send(parent,'destroy-parent');receive(parent)
    test.check('exported-parent-destruction-removes-native-parent',test.until(
        lambda: not any(w['id']==owner['id'] for w in test.command('windows')),'parent destruction'))
finally:
    for process in reversed(children):
        if process.poll() is None:process.terminate()
        try:process.wait(timeout=8)
        except subprocess.TimeoutExpired:process.kill();process.wait()
    (root/'file-parent-policy-checks.json').write_text(json.dumps(test.results,indent=2)+'\n')
