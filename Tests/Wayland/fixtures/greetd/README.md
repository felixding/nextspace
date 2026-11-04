# Installed login/logout readiness reference

`logout-100.png` is the English Workspace Log Out dialog at 100%, captured
from the installed native59 packages in the disposable Debian 13 Lima guest.
It is a native UI readiness reference, not an original artwork design source.

`system_greetd.py` compares the static RGB body (0,24)-(360,162). It also
requires the same Workspace client's protocol trace to show keyboard focus
on that dialog before injecting Escape or Return. The same-alpha solid-color
negative control guards against accidentally comparing only the alpha channel.
The title and button focus decorations are deliberately outside the static crop.
