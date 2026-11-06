#!/usr/bin/env python3
"""Check definite menu-ID rejection recovery and uncertain delivery boundaries."""
import json,sys
from pathlib import Path
from gi.repository import Gio
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Experiments/DBusMenus'))
from menu_model import MenuModel
from menu_events import application_event

ERROR='org.gtk.GDBus.UnmappedGError.Quark._LIBDBUSMENU_2dGLIB.Code0'
rows=[]
def check(case,value):
 rows.append(dict(case=case,passed=bool(value)));assert value,case
def missing(identifier):
 return Gio.DBusError.new_for_dbus_error(ERROR,f'The ID supplied {identifier} does not refer to a menu item we have')
def layout(identifier,**props):return (0,{},[(identifier,dict(label='Application command',**props),[])])
def fixture():
 model=MenuModel();token=model.reconcile(layout(10)).children[0].native
 return model,token
for operation in ['opened','clicked','closed']:
 model,token=fixture();sent=[];accepted=[];rejected=[]
 def send(remote,name):
  sent.append((remote,name))
  if remote==10:raise missing(remote)
  accepted.append((remote,name))
 remote=application_event(model,token,operation,send,lambda:model.reconcile(layout(20)),lambda *args:rejected.append(args))
 check(operation+'-definite-rejection-resolves-current-id-once',remote==20 and sent==[(10,operation),(20,operation)] and accepted==[(20,operation)] and len(rejected)==1)
for case,error in [
 ('timeout',Gio.DBusError.new_for_dbus_error('org.freedesktop.DBus.Error.Timeout','Reply expired')),
 ('disconnect',Gio.DBusError.new_for_dbus_error('org.freedesktop.DBus.Error.Disconnected','Connection closed')),
 ('different-id',missing(99)),
 ('different-error',Gio.DBusError.new_for_dbus_error('org.nextspace.Test.Uncertain','The ID supplied 10 does not refer to a menu item we have')),
 ('different-message',Gio.DBusError.new_for_dbus_error(ERROR,'Application callback failed'))]:
 model,token=fixture();sent=[];refreshes=[]
 def send(remote,name):
  sent.append((remote,name));raise error
 try:application_event(model,token,'clicked',send,lambda:refreshes.append(True),lambda *args:None)
 except type(error):pass
 else:raise AssertionError(case+' did not propagate')
 check(case+'-never-repeats-an-uncertain-action',sent==[(10,'clicked')] and not refreshes)
model,token=fixture();sent=[];refreshes=[]
def reject_forever(remote,name):
 sent.append(remote);raise missing(remote)
try:application_event(model,token,'clicked',reject_forever,lambda:refreshes.append(True),lambda *args:None)
except Exception:pass
else:raise AssertionError('Expected bounded rejection failure')
check('definite-rejection-has-bounded-recovery',len(sent)==3 and len(refreshes)==2)
for case,new_layout in [('retired',(0,{},[])),('disabled',layout(20,enabled=False)),('hidden',layout(20,visible=False))]:
 model,token=fixture();sent=[]
 def send(remote,name):
  sent.append(remote);raise missing(remote)
 result=application_event(model,token,'clicked',send,lambda:model.reconcile(new_layout),lambda *args:None)
 check('refreshed-'+case+'-command-is-not-executed',result is None and sent==[10])
print(json.dumps(dict(passed=len(rows),cases=rows)))
