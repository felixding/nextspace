"""Remove a browser text-only effect from the complete native address field."""
from pathlib import Path

START='/* NEXTSPACE native address field clipping */'
END='/* End NEXTSPACE native address field clipping */'
RULE=START+'\n*|*#urlbar-input { mask-image: none !important; }\n'+END

def prepare_native_fields(profile):
    profile=Path(profile)
    chrome=profile/'chrome'
    chrome.mkdir(parents=True,exist_ok=True)
    path=chrome/'userChrome.css'
    content=path.read_text() if path.exists() else ''
    if START in content:
        before,owned=content.split(START,1)
        unused,after=owned.split(END,1)
        content=before+RULE+after
    else:content+=('\n' if content and not content.endswith('\n') else '')+RULE+'\n'
    path.write_text(content)
    prefs=profile/'user.js'
    line='user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);'
    content=prefs.read_text() if prefs.exists() else ''
    if line not in content:content+='\n'+line+'\n'
    native_context='user_pref("widget.gtk.native-context-menus", true);'
    if native_context not in content:content+='\n'+native_context+'\n'
    prefs.write_text(content)
