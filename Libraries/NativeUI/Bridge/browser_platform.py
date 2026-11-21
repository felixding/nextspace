"""Configure the platform bridge for a stopped, caller-owned browser profile."""

from pathlib import Path

from browser_frames import prepare_native_frame
from firefox_webui import prepare_native_webui


FEATURES = {
    'chromium': ('POPUPS', 'MENUS', 'MENU_KEYS', 'EDIT_KEYS'),
    'firefox': ('INPUT', 'PAINT_ONLY', 'BUTTONS', 'POPUPS', 'COLORS',
                'SCROLLERS', 'MENU_LIFECYCLE', 'MENU_KEYS', 'EDIT_KEYS'),
}


def prepare_browser_platform(family, executable, profile, lifetime, environment):
    features = FEATURES[family]
    prepare_native_frame(family, profile, environment)
    for feature in features:
        if feature in ('MENU_KEYS', 'EDIT_KEYS') and environment.get('NEXTSPACE_SHORTCUTS', 'native') != 'native':
            environment.pop(f'NEXTSPACE_{family.upper()}_{feature}', None)
        else:
            environment[f'NEXTSPACE_{family.upper()}_{feature}'] = '1'

    if family == 'firefox':
        environment['MOZ_ENABLE_WAYLAND'] = '1'
        with (Path(profile) / 'user.js').open('a') as preferences:
            preferences.write(
                '\nuser_pref("widget.gtk.global-menu.enabled", true);\n'
                'user_pref("widget.gtk.global-menu.wayland.enabled", true);\n'
                'user_pref("widget.gtk.native-context-menus", true);\n'
                'user_pref("widget.use-xdg-desktop-portal.file-picker", 1);\n'
            )
        return prepare_native_webui(executable, profile, lifetime, environment,
                                    replace_controls=False)
    return executable
