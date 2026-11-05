# Original Window Maker references

These seven files are unchanged copies from `82bd01c4`, preserved for title
font/truncation references and the original application-level semantics.
`sources.json` records their original paths and byte hashes. Copyright and
license notices remain in each source file.

`generate_title_reference.py` extracts the original title functions from
`misc.c` and `core/wfont.c`; its optional Xft/Xvfb reference renderer uses the
four retained headers. `GNUstep.h` records the original application hints.
These files are reference inputs and are not compiled or installed as part of
the native Wayland desktop. The embedded window manager has been removed.
