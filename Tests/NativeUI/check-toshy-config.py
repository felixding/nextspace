#!/usr/bin/env python3
"""Check local rule preservation across an upstream Toshy template refresh."""
import argparse
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'Libraries/Toshy'))
from configuration import prepare, profile_aliases


def check_rules(upstream, config):
    sys.path[:0] = [str(upstream), str(upstream / 'vendors/xwaykeyz-main/src')]
    from xwaykeyz.cli import eval_config
    from xwaykeyz.config_api import combo, get_configuration

    eval_config(str(config))
    modmaps, multipurpose, keymaps, _, _ = get_configuration()
    assert all(not rule.mappings for rule in modmaps + multipurpose)
    chords = ('LAlt-c', 'LAlt-v', 'LAlt-f', 'LAlt-t', 'LAlt-w', 'Shift-LAlt-t', 'LC-c')
    for app in ('firefox-esr', 'chromium-browser', 'org.kde.konsole', ''):
        active = [rule for rule in keymaps if rule.matches(SimpleNamespace(wm_class=app))]
        for chord in chords:
            assert all(combo(chord) not in rule for rule in active), (app, chord)
    def targets(app, chord):
        ctx = SimpleNamespace(wm_class=app)
        source = combo(chord)
        return [rule[source] for rule in keymaps if rule.matches(ctx) and source in rule]

    keys = config.with_name('command-keys')
    assert targets('mousepad', 'LAlt-t') == []
    keys.write_text('LAlt RAlt')
    assert targets('mousepad', 'LAlt-t') == [combo('C-n')]
    assert targets('mousepad', 'RAlt-t') == [combo('C-n')]
    assert targets('mousepad', 'LSuper-t') == []
    keys.write_text('LSuper RAlt')
    assert targets('mousepad', 'LSuper-t') == [combo('C-n')]
    assert targets('mousepad', 'RAlt-t') == [combo('C-n')]
    assert targets('mousepad', 'LAlt-t') == []
    assert targets('org.kde.konsole', 'LSuper-t') == []
    assert targets('', 'LSuper-t') == []
    assert targets('mousepad', 'LAlt-y') == [combo('C-z')]
    assert targets('mousepad', 'LSuper-F8') == [combo('Shift-LSuper-F8')]
    print('Pinned mapper follows live Command changes and preserves scope and physical rules')


def check(upstream, evaluate):
    terminal = profile_aliases(upstream, 'General Terminals')
    assert terminal['Command-t'] == 'Shift-Command-t'
    assert 'Command-dot' not in terminal
    relative = Path('default-toshy-config/toshy_config_barebones.py')
    original = (upstream / relative).read_bytes()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        user = root / 'shortcuts.py'
        rules = (b'compatibility_keymap("mousepad", {"Command-t": "C-n", "Alt-y": "C-z", '
                 b'"Command-F8": "Shift-Command-F8"})\n')
        user.write_bytes(rules)
        config = prepare(upstream, root, user)
        before = config.read_text()

        refreshed = root / 'refreshed'
        template = refreshed / relative
        template.parent.mkdir(parents=True)
        new_source = original + b'\n# Upstream template refresh\n'
        template.write_bytes(new_source)
        after = prepare(refreshed, root, user).read_text()

        assert before + '\n# Upstream template refresh\n' == after
        assert user.read_bytes() == rules
        assert template.read_bytes() == new_source
        assert (upstream / relative).read_bytes() == original
        assert after.count(f'include({str(user)!r})') == 1
        compile(after, str(config), 'exec')
        if evaluate:
            check_rules(upstream, config)
        try:
            prepare(refreshed, root, user)  # Rebuilding must also be idempotent.
            assert config.read_text() == after
            template.write_bytes(new_source.replace(b'SLICE_MARK_START: env_overrides', b'SLICE_MARK_START: renamed'))
            prepare(refreshed, root, user)
        except ValueError as error:
            assert 'env_overrides' in str(error)
        else:
            raise AssertionError('A renamed upstream section must fail the refresh')
    print('Toshy config refresh preserved the existing local rule file')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('upstream', type=Path)
    parser.add_argument('--evaluate', action='store_true')
    args = parser.parse_args()
    check(args.upstream.resolve(), args.evaluate)
