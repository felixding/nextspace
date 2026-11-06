"""Select existing system-decoration paths in an owned, stopped browser profile.

Call before launching the browser. Rendering, metrics and window actions remain
in the compositor; this module only configures browser-owned preferences.
"""
import json
from pathlib import Path


def prepare_native_frame(family, profile, environment):
    profile = Path(profile)
    if family == 'firefox':
        profile.mkdir(parents=True, exist_ok=True)
        with (profile / 'user.js').open('a') as stream:
            stream.write('\nuser_pref("browser.tabs.inTitlebar", 0);\n')
        environment.update(MOZ_GTK_TITLEBAR_DECORATION='system', GTK_CSD='0')
    elif family == 'chromium':
        path = profile / 'Default/Preferences'
        preferences = json.loads(path.read_text()) if path.exists() else {}
        preferences.setdefault('browser', {})['custom_chrome_frame'] = False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(preferences) + '\n')
    else:
        raise ValueError('Unsupported browser family: ' + family)
