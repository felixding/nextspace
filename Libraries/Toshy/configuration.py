"""Assemble a session config from the intact upstream Toshy template."""
import ast
import json
import os
from pathlib import Path
import re


# Physical modifiers supported by xwaykeyz's chord API, in evdev naming.
COMMAND_MODIFIERS = {
    'LAlt': 'KEY_LEFTALT', 'RAlt': 'KEY_RIGHTALT',
    'LC': 'KEY_LEFTCTRL', 'RC': 'KEY_RIGHTCTRL',
    'LSuper': 'KEY_LEFTMETA', 'RSuper': 'KEY_RIGHTMETA',
}


def register_compatibility_keymap(keymap, combo, command_keys, app_id, mappings):
    if not app_id:
        raise ValueError('A Wayland app ID is required')

    def in_app(ctx):
        return ctx.wm_class == app_id

    fixed, dynamic = {}, {}
    for source, target in mappings.items():
        if 'Command' in source.split('-')[:-1]:
            dynamic[source] = target
        else:
            fixed[combo(source)] = combo(target)
    if fixed:
        keymap(app_id, fixed, when=in_app)
    if not dynamic:
        return

    previous_context = None
    active_keys = ()

    def matches(ctx, physical):
        nonlocal previous_context, active_keys
        if not in_app(ctx):
            return False
        # The window-context query above synchronizes the Wayland connection.
        if ctx is not previous_context:
            try:
                active_keys = command_keys.read_text().split()
            except FileNotFoundError:
                active_keys = ()
            previous_context = ctx
        return physical in active_keys

    def resolve(chord, physical):
        return combo('-'.join(physical if part == 'Command' else part for part in chord.split('-')))

    for physical in COMMAND_MODIFIERS:
        bindings = {
            resolve(source, physical): resolve(target, physical)
            for source, target in dynamic.items()
        }
        keymap(app_id, bindings, when=lambda ctx, physical=physical: matches(ctx, physical))


def render(template, overrides):
    for name, content in overrides.items():
        marker = rf'(^###[ \t]+SLICE_MARK_START: {name} [^\n]*\n).*?(^###[ \t]+SLICE_MARK_END: {name} [^\n]*$)'
        template, count = re.subn(marker, lambda match: match[1] + content + '\n' + match[2],
                                  template, flags=re.MULTILINE | re.DOTALL)
        if count != 1:
            raise ValueError(f'Expected one Toshy config section named {name}')
    return template


def profile_aliases(upstream, profile):
    """Adapt a pinned Toshy profile's same-key Command-to-Control+Shift rules."""
    template = upstream / 'default-toshy-config/toshy_config.py'
    tree = ast.parse(template.read_text(), filename=str(template))
    matches = [node.value.args[1] for node in tree.body
               if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
               and isinstance(node.value.func, ast.Name) and node.value.func.id == 'keymap'
               and len(node.value.args) >= 2 and isinstance(node.value.args[0], ast.Constant)
               and node.value.args[0].value == profile]
    if len(matches) != 1 or not isinstance(matches[0], ast.Dict):
        raise ValueError(f'Expected one declarative Toshy profile named {profile}')

    def chord(node):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'C'
                and len(node.args) == 1 and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            return node.args[0].value.lower().split('-')
        return []

    aliases = {}
    for source, target in zip(matches[0].keys, matches[0].values):
        before, after = chord(source), chord(target)
        if (len(before) == 2 and before[0] == 'rc' and len(after) == 3
                and set(after[:-1]) == {'c', 'shift'} and after[-1] == before[-1]):
            # Use the app's Command alias to keep disabled actions out of the PTY.
            aliases[f'Command-{before[-1]}'] = f'Shift-Command-{before[-1]}'
    if not aliases:
        raise ValueError(f'Toshy profile {profile} has no compatible modifier aliases')
    return aliases


def prepare(upstream, directory, local, profiles=None):
    template = upstream / 'default-toshy-config/toshy_config_barebones.py'
    local_rules = (
        # The upstream examples register later. Preserve those chords unchanged.
        'keymap("Keep diagnostic chords", {C(chord): C(chord) for chord in '
        '("Shift-Alt-RC-i", "Shift-Alt-RC-h", "Shift-Alt-RC-t")})\n'
        'from pathlib import Path\n'
        'from configuration import register_compatibility_keymap\n'
        'def compatibility_keymap(app_id, mappings):\n'
        f'    register_compatibility_keymap(keymap, C, Path({str(directory / "command-keys")!r}), '
        'app_id, mappings)\n'
        f'if os.path.isfile({str(local)!r}):\n'
        f'    include({str(local)!r})\n'
    )
    if profiles:
        for app_id, profile in json.loads(profiles.read_text()).items():
            local_rules += f'compatibility_keymap({app_id!r}, {profile_aliases(upstream, profile)!r})\n'
    overrides = {
        'env_overrides': (
            'OVERRIDE_SESSION_TYPE = "wayland"\n'
            'OVERRIDE_DESKTOP_ENV = "nextspace"\n'
            'OVERRIDE_WINDOW_MGR = "nextspace"\n'
            'wlroots_compositors = ["nextspace"]\n'
        ),
        'barebones_user_cfg': local_rules,
    }
    config = directory / 'toshy_config.py'
    config.write_text(render(template.read_text(), overrides))
    return config


def user_config():
    directory = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    return directory / 'nextspace/toshy/shortcuts.py'
