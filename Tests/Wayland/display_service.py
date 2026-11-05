"""Public Workspace display transactions shared by live Linux fixtures."""
import json
import subprocess


class DisplayService:
    def __init__(self, probe, request_path):
        self.probe = str(probe)
        self.request_path = request_path

    def query(self, *arguments):
        result = subprocess.run([self.probe, *arguments], capture_output=True,
                                text=True, check=True, timeout=20)
        return json.loads(result.stdout)

    def request(self, action, **values):
        self.request_path.write_text(json.dumps(dict(action=action, **values)))
        return self.query('--display-request', str(self.request_path))

    @staticmethod
    def settings(heads):
        keys = ('id', 'enabled', 'primary', 'width', 'height', 'refresh', 'scale', 'transform', 'x', 'y')
        return {head['id']: {key: head[key] for key in keys} for head in heads}

    def preview(self, layout, timeout=15000):
        state = self.query('--display-state')
        assert not state['pending'], 'Another display transaction is pending'
        tested = self.request('test', layout=layout, revision=state['revision'])
        assert tested['status'] == 0, tested
        assert self.settings(self.query('--display-state')['heads']) == self.settings(state['heads']), 'Test changed the layout'
        changed = self.request('apply', layout=layout, revision=state['revision'], timeout=timeout)
        assert changed['status'] == 1, changed
        assert self.settings(self.query('--display-state')['heads']) == self.settings(layout), 'Incomplete layout commit'
        return changed

    def apply(self, layout):
        changed = self.preview(layout)
        assert self.request('confirm', token=changed['token'])['status'] == 2
        return self.query('--display-state')
