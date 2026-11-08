"""Owned cross-process color-picker references; contains no UI implementation."""
import math
import select
from pathlib import Path

class ColorOwners:
    def __init__(self,server):
        self.server=server
        self.pending={}
        self.aliases={}

    def owner(self,client,process,pid):
        entry=self.server.notifiers.get(process)
        return bool(entry and entry['client'] is client and entry['pid']==pid and
                    not select.select([entry['lifetime']],[],[],0)[0])

    @staticmethod
    def ancestor(child,parent):
        for unused in range(32):
            if child==parent:return True
            if child<=1:return False
            try:
                fields=dict(line.split(':',1) for line in Path('/proc',str(child),'status').read_text().splitlines() if ':' in line)
                child=int(fields['PPid'])
            except (OSError,KeyError,ValueError):return False
        return False

    def message(self,client,request,pid):
        s=self.server;state=None;accepted=False
        valid=(s.color_panel_capabilities&1 and request.kind==16 and request.control and
               not request.text_size and not any((request.width,request.height,request.minimum,request.maximum,
                 request.value,request.y,request.enabled,request.indeterminate,request.modifiers)) and
               (request.operation==60 or request.state==0) and self.owner(client,request.process,pid))
        if valid and request.operation in (60,61):
            valid=math.isfinite(request.x) and 0<request.x<=0xffffffff and request.x==int(request.x)
        if valid and request.operation==60:
            state=s.controls.get((request.process,request.control,16))
            accepted=bool(state and not state['destroy'] and state['client'] is client and request.state in (0,1))
            if accepted:
                key=pid,int(request.x)
                if request.state:self.pending[key]=state
                elif self.pending.get(key) is state:del self.pending[key]
        elif valid and request.operation==61:
            key=request.process,request.control
            matches=[(token,source) for token,source in self.pending.items()
                     if token[1]==int(request.x) and not source['destroy'] and
                     self.owner(source['client'],source['key'][0],token[0]) and self.ancestor(token[0],pid)]
            # Actor IDs are scoped by their original process/channel. Refuse
            # ambiguous references rather than connect the wrong page/app.
            if len(matches)==1 and key not in self.aliases and (request.process,request.control,16) not in s.controls:
                token,state=matches[0]
                if not any(entry['state'] is state for entry in self.aliases.values()):
                    self.aliases[key]=dict(state=state,client=client,pid=pid,seen=state['actions'],applied=state['actions'])
                    del self.pending[token];accepted=True
        elif valid and request.operation==62:
            entry=self.aliases.get((request.process,request.control))
            if entry and entry['client'] is client:
                self.release((request.process,request.control));accepted=True
        s.log('native-color-owner',operation=request.operation,process=request.process,control=request.control,accepted=int(accepted))
        s._respond(client,request,state if accepted else None,input_result=int(accepted),pixels=bool(accepted and request.operation==61))

    def resolve(self,client,request,pid):
        entry=self.aliases.get((request.process,request.control)) if request.kind==16 else None
        return entry['state'] if (entry and entry['client'] is client and entry['pid']==pid and
                                 self.owner(client,request.process,pid) and not entry['state']['destroy']) else None

    def acknowledge(self,client,request,state):
        entry=self.aliases.get((request.process,request.control))
        if entry and entry['client'] is client and entry['state'] is state:entry['seen']=state['actions']

    def stale_echo(self,state,model):
        return (model==state.get('color_model') and
                any(entry['state'] is state and state['actions']>entry['applied'] for entry in self.aliases.values()))

    def model_applied(self,state):
        for entry in self.aliases.values():
            if entry['state'] is state:entry['applied']=state['actions']

    def fanout(self,process):
        s=self.server
        for recipient in {key[0] for key,entry in self.aliases.items() if entry['state']['key'][0]==process and key[0]!=process}:
            s.generations[recipient]=s.generations.get(recipient,0)+1;s.signal(recipient)

    def release(self,key):
        entry=self.aliases.pop(key,None)
        if entry:self.server.native.nxs_control_color_open(entry['state']['native'],0)

    def retire(self,state):
        for token,source in list(self.pending.items()):
            if source is state:del self.pending[token]
        for key,entry in list(self.aliases.items()):
            if entry['state'] is state:
                self.release(key);self.server.invalidate(key[0])

    def disconnect(self,client):
        for key,entry in list(self.aliases.items()):
            if entry['client'] is client:self.release(key)
