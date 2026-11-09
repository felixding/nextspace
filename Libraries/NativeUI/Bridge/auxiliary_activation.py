"""Standard activation-token handoff; no window, control or focus policy."""
import ctypes as C
import math
import os
import select


class AuxiliaryActivation:
    def __init__(self, server, ancestor):
        self.server, self.ancestor = server, ancestor
        self.tokens, self.pending = {}, {}

    def discard(self, key, reason='replaced'):
        entry = self.tokens.pop(key, None)
        if entry:
            self.server.log('native-auxiliary-source-retired',pid=key[1],reason=reason)
            os.close(entry['lifetime'])

    def publish(self, client, request, pid, payload):
        s = self.server
        accepted = False
        if (s.auxiliary_capabilities & 1 and pid and pid > 0 and request.process
                and request.kind == 0 and request.control and request.state == 1
                and 0 < len(payload) <= 4096 and b'\0' not in payload
                and math.isfinite(request.x) and request.x == int(request.x) and 0 <= request.x <= 0xffffffff
                and not any((request.width, request.height, request.y, request.minimum,
                    request.maximum, request.value, request.enabled, request.indeterminate, request.modifiers))):
            try:
                token = payload.decode('utf-8')
                lifetime = os.pidfd_open(pid, 0)
                key = client, pid
                self.discard(key)
                self.tokens[key] = dict(token=token, lifetime=lifetime, process=request.process,
                    surface=request.control, serial=int(request.x))
                accepted = True
                for pending in list(self.pending.values()):
                    self.apply(pending)
            except (OSError, UnicodeError) as error:
                accepted = False
                s.log('native-auxiliary-token-error',pid=pid,reason=str(error))
        s.log('native-auxiliary-token', process=request.process, pid=pid, accepted=int(accepted))

    def open(self, state, pid):
        s = self.server
        owned = s.owns_process(state['client'], state['key'][0], pid)
        owner = s.notifiers.get(state['key'][0])
        s.log('native-auxiliary-owner',process=state['key'][0],control=state['key'][1],
              pid=pid,owned=int(owned),notifier_pid=owner['pid'] if owner else None,
              same_client=bool(owner and owner['client'] is state['client']))
        if s.auxiliary_capabilities & 1 and owned:
            entry = dict(state=state, pid=pid)
            self.pending[state['key']] = entry
            self.apply(entry)

    def visible(self, state):
        # Ask the existing native owner; color wells own the shared color panel,
        # while popup/date controls expose their original popup state.
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
        accepted = s.native.nxs_control_auxiliary_activate(state['native'], token['token'].encode())
        s.log('native-auxiliary-activation', process=state['key'][0], control=state['key'][1],
              source_pid=key[1], target_pid=pid, accepted=int(accepted))

    def retire(self, state):
        self.pending.pop(state['key'], None)

    def disconnect(self, client):
        for key in list(self.tokens):
            if key[0] is client:
                self.discard(key,'client-disconnected')
        for key, entry in list(self.pending.items()):
            if entry['state']['client'] is client:
                del self.pending[key]

    def prune(self):
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
