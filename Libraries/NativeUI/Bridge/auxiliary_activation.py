"""Standard activation-token handoff; no window, control or focus policy."""
import ctypes as C
import math
import os
import select
import socket
import struct
import stat
import time


class AuxiliaryActivation:
    def __init__(self, server, ancestor):
        self.server, self.ancestor = server, ancestor
        self.tokens, self.pending, self.providers = {}, {}, {}
        self.sequence = 0

    def remove_provider(self, key):
        entry = self.providers.pop(key, None)
        if entry:
            self.server.native.nxs_native_ui_source_destroy(entry['source'])
            entry['socket'].close()
            os.close(entry['lifetime'])

    def register(self, client, request, pid, descriptors):
        if (request.state != 3 or request.kind or request.control or request.text_size
                or not self.server.auxiliary_capabilities & 1 or not pid or pid <= 0
                or not request.process or len(descriptors) != 1 or any((request.x, request.y,
                    request.width, request.height, request.minimum, request.maximum, request.value,
                    request.enabled, request.indeterminate, request.modifiers))):
            return
        peer = lifetime = source = None
        try:
            if not stat.S_ISSOCK(os.fstat(descriptors[0]).st_mode):return
            peer = socket.socket(fileno=os.dup(descriptors[0]))
            if peer.family != socket.AF_UNIX or peer.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_SEQPACKET:
                return
            peer.setblocking(False)
            lifetime = os.pidfd_open(pid, 0)
            source = self.server.native.nxs_native_ui_source_create(lifetime)
            if not source:
                return
            key = client, pid
            self.remove_provider(key)
            self.providers[key] = dict(socket=peer, lifetime=lifetime, source=source,
                                      process=request.process, input=False, requested=0)
            peer = lifetime = source = None
            self.server.log('native-auxiliary-provider', pid=pid)
        except OSError as error:
            self.server.log('native-auxiliary-provider-error', pid=pid, reason=str(error))
        finally:
            if source:self.server.native.nxs_native_ui_source_destroy(source)
            if lifetime is not None:os.close(lifetime)
            if peer is not None:peer.close()

    def request(self, pending):
        matches = [(key, entry) for key, entry in self.providers.items()
                   if entry['input'] and self.ancestor(pending['pid'], key[1])]
        if len(matches) != 1:
            return False
        key, entry = matches[0]
        if not entry['requested']:
            self.sequence = self.sequence % 0xffffffff + 1
            try:
                entry['socket'].send(struct.pack('<Q', self.sequence))
            except (BlockingIOError, OSError):
                self.remove_provider(key)
                return False
            entry['requested'] = self.sequence
            self.server.log('native-auxiliary-token-request', pid=key[1], request=self.sequence)
        return True

    def discard(self, key, reason='replaced'):
        entry = self.tokens.pop(key, None)
        if entry:
            self.server.log('native-auxiliary-source-retired',pid=key[1],reason=reason)
            os.close(entry['lifetime'])

    def publish(self, client, request, pid, payload):
        s = self.server
        accepted = False
        if (request.state == 4 and not payload and request.kind == 0 and request.control
                and pid and s.owns_process(client,request.process,pid)
                and not any((request.x,request.y,request.width,request.height,request.minimum,request.maximum,
                    request.value,request.enabled,request.indeterminate,request.modifiers))):
            state=s.menus.context_active
            if (state and not state['destroy'] and self.ancestor(state['context_pid'],pid)
                    and state['client'] is client and (not s.input_owner or s.input_owner(pid))):
                s.native.nxs_menu_cancel(state['native'])
                s.log('native-context-menu-source-pointer-dismiss',process=request.process,pid=pid,control=state['key'][1])
            return
        if (request.state == 0 and not payload and s.auxiliary_capabilities & 1
                and pid and pid > 0 and request.process and request.kind == 0 and request.control
                and not any((request.x, request.width, request.height, request.y, request.minimum,
                    request.maximum, request.value, request.enabled, request.indeterminate, request.modifiers))):
            self.discard((client, pid), 'new-input')
            provider = self.providers.get((client, pid))
            if provider:provider.update(input=True, requested=0)
            for key, entry in list(self.pending.items()):
                if self.ancestor(entry['pid'], pid):
                    del self.pending[key]
            s.log('native-auxiliary-input-reset', process=request.process, pid=pid)
            return
        if (s.auxiliary_capabilities & 1 and pid and pid > 0 and request.process
                and request.kind == 0 and request.control and request.state in (1, 2)
                and 0 < len(payload) <= 8193
                and math.isfinite(request.x) and request.x == int(request.x) and 0 <= request.x <= 0xffffffff
                and not any((request.width, request.height, request.y, request.minimum,
                    request.maximum, request.enabled, request.indeterminate, request.modifiers))):
            try:
                provider = self.providers.get((client, pid))
                if provider and provider['input']:
                    if not request.value or request.value != provider['requested']:
                        raise ValueError('Superseded activation token request')
                elif request.value:
                    raise ValueError('Unrequested activation token')
                parts = payload.split(b'\0')
                if len(parts) != request.state or any(not p or len(p) > 4096 for p in parts):
                    raise ValueError('Invalid activation/parent payload')
                token = parts[0].decode('utf-8')
                parent = parts[1].decode('utf-8') if request.state == 2 else None
                lifetime = os.pidfd_open(pid, 0)
                if provider:provider['requested'] = 0
                key = client, pid
                self.discard(key)
                self.tokens[key] = dict(token=token, lifetime=lifetime, process=request.process,
                    surface=request.control, serial=int(request.x), parent=parent, received=time.monotonic())
                accepted = True
                for pending in list(self.pending.values()):
                    self.apply(pending)
            except (OSError, ValueError) as error:
                accepted = False
                s.log('native-auxiliary-token-error',pid=pid,reason=str(error))
        s.log('native-auxiliary-token', process=request.process, pid=pid, accepted=int(accepted))

    def open(self, state, pid, *, activate=True):
        s = self.server
        owned = s.owns_process(state['client'], state['key'][0], pid)
        owner = s.notifiers.get(state['key'][0])
        s.log('native-auxiliary-owner',process=state['key'][0],control=state['key'][1],
              pid=pid,owned=int(owned),notifier_pid=owner['pid'] if owner else None,
              same_client=bool(owner and owner['client'] is state['client']))
        if s.auxiliary_capabilities & 1 and owned:
            entry = dict(state=state, pid=pid, opened=time.monotonic(), activate=activate)
            self.pending[state['key']] = entry
            if not self.request(entry):self.apply(entry)

    def visible(self, state):
        # Ask the existing native owner; color wells own the shared color panel,
        # while popup/date controls expose their original popup state.
        if state['key'][2] == 0:
            return bool(self.server.native.nxs_menu_state(state['native'],-1).visible)
        if state['key'][2] == 16:
            return bool(self.server.native.nxs_control_state(state['native']).state)
        return bool(self.server.native.nxs_control_popup_state(state['native']).visible)

    def apply(self, pending):
        s = self.server
        state, pid = pending['state'], pending['pid']
        if (state['destroy'] or not s.owns_process(state['client'], state['key'][0], pid)
                or not self.visible(state)):
            s.log('native-auxiliary-retired-before-token',process=state['key'][0],control=state['key'][1])
            self.pending.pop(state['key'], None)
            return
        matches = []
        for key, token in list(self.tokens.items()):
            if select.select([token['lifetime']], [], [], 0)[0]:
                self.discard(key,'source-exited')
            elif self.ancestor(pid, key[1]):
                matches.append((key, token))
        if len(matches) != 1:
            s.log('native-auxiliary-source-match',process=state['key'][0],control=state['key'][1],
                  pid=pid,matches=len(matches),sources=[key[1] for key in self.tokens])
            return
        key, token = matches[0]
        self.discard(key,'consumed')
        self.pending.pop(state['key'], None)
        parent_accepted = None
        parent_call=getattr(s.native,'nxs_menu_auxiliary_parent' if state['key'][2]==0 else 'nxs_control_auxiliary_parent',None)
        activate_call=s.native.nxs_menu_auxiliary_activate if state['key'][2]==0 else s.native.nxs_control_auxiliary_activate
        if s.auxiliary_capabilities & 2 and parent_call:
            parent_accepted = parent_call(state['native'],
                token['parent'].encode() if token['parent'] else None)
        accepted = activate_call(state['native'], token['token'].encode()) if pending['activate'] else parent_accepted
        s.log('native-auxiliary-activation', process=state['key'][0], control=state['key'][1],
              source_pid=key[1], target_pid=pid, serial=token['serial'],
              has_parent=bool(token['parent']),
              token_age=time.monotonic()-token['received'], open_age=time.monotonic()-pending['opened'],
              accepted=int(bool(accepted)), parent_accepted=parent_accepted,
              activation_requested=pending['activate'])

    def retire(self, state):
        self.pending.pop(state['key'], None)

    def disconnect(self, client):
        for key in list(self.providers):
            if key[0] is client:self.remove_provider(key)
        for key in list(self.tokens):
            if key[0] is client:
                self.discard(key,'client-disconnected')
        for key, entry in list(self.pending.items()):
            if entry['state']['client'] is client:
                del self.pending[key]

    def prune(self):
        for key, entry in list(self.providers.items()):
            if select.select([entry['lifetime']], [], [], 0)[0]:self.remove_provider(key)
        for key, token in list(self.tokens.items()):
            if select.select([token['lifetime']], [], [], 0)[0]:
                self.discard(key, 'source-exited')
        for key, pending in list(self.pending.items()):
            state = pending['state']
            if (state['destroy'] or not self.server.owns_process(state['client'], key[0], pending['pid'])
                    or not self.visible(state)):
                del self.pending[key]

    def close(self):
        for key in list(self.tokens):
            self.discard(key,'cleanup')
        self.pending.clear()
        for key in list(self.providers):self.remove_provider(key)
