# Chromium native scrollbar integration boundary

Audited 2026-11-05 against Debian's ARM64 Chromium
`156.0.8078.79-1~deb13u1`, downloaded and extracted without installing it, and
upstream tag `156.0.8078.79`, commit
`a21ce95c24ce3964416f09ae1862f53f319eb4d0`.

The GTK/Qt adapters cannot host `NSScroller` in Chromium's web content:

- [Blink's theme factory](https://chromium.googlesource.com/chromium/src/+/a21ce95c24ce3964416f09ae1862f53f319eb4d0/third_party/blink/renderer/platform/theme/web_theme_engine_helper.cc)
  constructs its built-in theme engine. Its replacement method is an internal
  testing API, not a GTK/Qt module loader.
- [The web native-theme selection](https://chromium.googlesource.com/chromium/src/+/a21ce95c24ce3964416f09ae1862f53f319eb4d0/ui/native_theme/native_theme.cc)
  constructs Aura or Fluent theme objects. Selecting a GTK desktop theme does
  not substitute a `GtkScrollbar` widget for this control.
- [Blink's scrollbar](https://chromium.googlesource.com/chromium/src/+/a21ce95c24ce3964416f09ae1862f53f319eb4d0/third_party/blink/renderer/core/scroll/scrollbar.cc)
  owns thumb movement, pressed-part repeat, mouse dispatch and the request for
  scrollbar-side placement. Replacing drawing alone would leave that behavior
  in Blink rather than reuse native `NSScroller` tracking.
- The packaged executable's dynamic symbol table contains no `NativeTheme`,
  `Scrollbar`, `ThemeEngine`, `gtk_scrollbar` or `gtk_scrolled_window` entries.
  In particular, its testing replacement method is not exposed for a preload
  adapter to call. This is a finding about this stock build, not every possible
  custom/component build.
- [Extension native messaging](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging)
  exchanges JSON with a separate process. That interface does not itself embed
  an AppKit control or replace Blink's layout and input handling. A content
  script that draws a similar-looking control would not satisfy native reuse.

Full support therefore needs an additional browser-engine integration covering
placement, painting and input, reusing the existing native bridge across the
renderer boundary. No supported way to install that integration into the
inspected unchanged browser binary was found. A source integration would need
a Chromium rebuild, conflicting with the current no-application-recompile
constraint. It is not implemented or counted as supported by this branch.

Local audit evidence is under `.build/foreign-scrollbars/chromium-boundary/`:
`audit.json`, the executable's dynamic symbols/section, download log, binary
hashes, and source receipts with individual file hashes. The downloaded package
SHA-256 is `9d653adaa334c661144330bd1374bf6564ad510841d0c74f06be40f164218841`.
