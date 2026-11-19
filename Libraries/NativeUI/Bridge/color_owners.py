"""Owned cross-process color-picker references; contains no UI implementation."""
import math
import select
from pathlib import Path

class ColorOwners:
    def __init__(self,server):
        self.server=server
        self.pending={}
        self.pending_deferred=set()
        self.aliases={}

    def owner(self,client,process,pid):
        return self.server.owns_process(client,process,pid)

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
        if valid and request.operation in (60,61,67):
            valid=math.isfinite(request.x) and 0<request.x<=0xffffffff and request.x==int(request.x)
        if valid and request.operation==60:
            state=s.controls.get((request.process,request.control,16))
            accepted=bool(state and not state['destroy'] and state['client'] is client and
                          request.state in (0,1,2) and (request.state!=2 or s.color_panel_capabilities&2))
            if accepted:
                key=pid,int(request.x)
                if request.state:
                    self.pending[key]=state
                    if request.state==2:self.pending_deferred.add(key)
                    else:self.pending_deferred.discard(key)
                elif self.pending.get(key) is state:
                    del self.pending[key];self.pending_deferred.discard(key)
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
                    self.aliases[key]=dict(state=state,client=client,pid=pid,seen=state['actions'],applied=state['actions'],
                                           token=token,deferred=token in self.pending_deferred)
                    del self.pending[token];self.pending_deferred.discard(token);accepted=True
        elif valid and request.operation==62:
            entry=self.aliases.get((request.process,request.control))
            if entry and entry['client'] is client:
                self.release((request.process,request.control));accepted=True
        elif valid and request.operation==67:
            state=s.controls.get((request.process,request.control,16))
            accepted=bool(s.color_panel_capabilities&2 and state and not state['destroy'] and
                          state['client'] is client and state.get('color_close_token')==(pid,int(request.x)) and
                          s.native.nxs_control_color_lifecycle(state['native'],3) and
                          s.native.nxs_control_color_lifecycle(state['native'],2))
        s.log('native-color-owner',operation=request.operation,process=request.process,control=request.control,accepted=int(accepted))
        s._respond(client,request,state if accepted else None,input_result=int(accepted),pixels=bool(accepted and request.operation==61))

    def panel(self,client,request,pid,state):
        """Bind close acknowledgement to the actual successful native session."""
        s=self.server;entry=self.aliases.get((request.process,request.control))
        if request.state==2:
            # Reveal the existing native well's panel without replacing its
            # original engine callback, close ticket or borrowed reference.
            return bool(s.native.nxs_control_state(state['native']).state and
                        s.native.nxs_control_color_open(state['native'],1))
        if not request.state:
            if entry and entry['client'] is client and entry.get('deferred'):
                return bool(s.native.nxs_control_color_lifecycle(state['native'],3))
            state.pop('color_close_token',None)
            return bool(s.native.nxs_control_color_open(state['native'],0))
        ticket=entry.get('token') if entry and entry.get('deferred') else None
        direct=None
        if not entry:
            matches=[key for key,source in self.pending.items() if source is state and key[0]==pid]
            if len(matches)==1:
                direct=matches[0]
                if direct in self.pending_deferred:ticket=direct
        if s.color_panel_capabilities&2:
            if not s.native.nxs_control_color_lifecycle(state['native'],1 if ticket else 0):return False
        accepted=bool(s.native.nxs_control_color_open(state['native'],1))
        if accepted:
            state['color_close_token']=ticket
            if direct:
                del self.pending[direct];self.pending_deferred.discard(direct)
        return accepted

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

    def fanout(self,process,state=None):
        s=self.server
        for recipient in {key[0] for key,entry in self.aliases.items() if entry['state']['key'][0]==process and key[0]!=process and
                          (state is None or entry['state'] is state)}:
            s.invalidate(recipient,fanout=False)

    def release(self,key):
        entry=self.aliases.pop(key,None)
        if entry:
            if entry.get('deferred'):self.server.native.nxs_control_color_lifecycle(entry['state']['native'],3)
            else:self.server.native.nxs_control_color_open(entry['state']['native'],0)

    def retire(self,state):
        for token,source in list(self.pending.items()):
            if source is state:del self.pending[token];self.pending_deferred.discard(token)
        for key,entry in list(self.aliases.items()):
            if entry['state'] is state:
                self.release(key);self.server.invalidate(key[0])

    def disconnect(self,client):
        for key,entry in list(self.aliases.items()):
            if entry['client'] is client:self.release(key)
