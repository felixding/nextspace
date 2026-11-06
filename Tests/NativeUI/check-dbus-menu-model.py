#!/usr/bin/env python3
"""Check remote menu identity churn without copying any native UI behavior."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Experiments/DBusMenus'))
from menu_model import MenuModel,flattened,replace_children
rows=[]
def check(case,value):
 rows.append(dict(case=case,passed=bool(value)));assert value,case
def node(identifier,label,children=(),**props):return (identifier,dict(label=label,**props),list(children))
def root(*children):return (0,{},list(children))
m=MenuModel();first=m.reconcile(root(node(1,'Edit',[node(2,'Undo')]),node(3,'File')));edit=first.children[0].native;undo=first.children[0].children[0].native
second=m.reconcile(root(node(30,'File'),node(10,'Edit',[node(20,'Undo',enabled=False),node(21,'Paste')])));check('whole-exporter-rebuild-retains-unique-identities',second.children[1].native==edit and second.children[1].children[0].native==undo)
check('live-properties-and-remote-identifiers-update',m.nodes[undo].remote==20 and not m.nodes[undo].properties['enabled'])
third=m.reconcile(root(node(30,'Renamed File'),node(10,'Edit',[node(20,'Undo')])));check('stable-remote-id-survives-label-change',third.children[0].native==second.children[0].native)
old=third;m.reconcile(root(node(40,'Other')));check('removed-command-token-is-retired',undo not in m.nodes)
clone=replace_children(first,edit,(node_rec:=old.children[0],));check('native-snapshot-branch-replacement-preserves-original',first.children[0].children[0].native==undo and clone.children[0].children==(node_rec,))
m=MenuModel();first=m.reconcile(root(node(1,'Same'),node(2,'Same')));old_tokens={n.native for n in first.children};second=m.reconcile(root(node(3,'Same'),node(4,'Same')));check('ambiguous-rebuilt-siblings-never-alias',not old_tokens.intersection(n.native for n in second.children))
tokens_by_remote={n.remote:n.native for n in second.children}
second=m.reconcile(root(node(4,'Same'),node(3,'Same')));check('stable-ids-disambiguate-duplicate-labels',[n.native for n in second.children]==[tokens_by_remote[4],tokens_by_remote[3]])
previous=m.root
for name,bad in [('duplicate-id',root(node(1,'A'),node(1,'B'))),('bad-child',root((1,None,[]))),('bad-shortcut',root(node(1,'A',shortcut='bad'))),('bad-root',(1,{},[]))]:
 try:m.reconcile(bad)
 except ValueError:check(name+'-atomic-rejection',m.root is previous)
 else:raise AssertionError(name)
print(json.dumps(dict(passed=len(rows),cases=rows)))
