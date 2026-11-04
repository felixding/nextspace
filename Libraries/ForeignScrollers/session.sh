# Sourced by the native user launcher when this optional package is installed.
# GPL-2.0-or-later.
if [ "${NEXTSPACE_SCROLLBARS:-native}" != off ]; then
  nextspace_scroller_libdir=${NEXTSPACE_SCROLLER_LIBDIR:-/usr/NextSpace/lib/nextspace-scrollbars}
  if [ -r "$nextspace_scroller_libdir/libnextspace-gtk-bootstrap.so" ]; then
    case ":${LD_PRELOAD:-}:" in
      *":$nextspace_scroller_libdir/libnextspace-gtk-bootstrap.so:"*) ;;
      *) export LD_PRELOAD="${LD_PRELOAD:+$LD_PRELOAD:}$nextspace_scroller_libdir/libnextspace-gtk-bootstrap.so" ;;
    esac
    case ":${QT_PLUGIN_PATH:-}:" in
      *":$nextspace_scroller_libdir/qt6:"*) ;;
      *) export QT_PLUGIN_PATH="$nextspace_scroller_libdir/qt6${QT_PLUGIN_PATH:+:$QT_PLUGIN_PATH}" ;;
    esac
    case ",${QT_QPA_GENERIC_PLUGINS:-}," in
      *,nextspace-scrollbars,*) ;;
      *) export QT_QPA_GENERIC_PLUGINS="${QT_QPA_GENERIC_PLUGINS:+$QT_QPA_GENERIC_PLUGINS,}nextspace-scrollbars" ;;
    esac
    case ":${GTK_MODULES:-}:" in
      *":$nextspace_scroller_libdir/libnextspace-gtk3-scrollbars.so:"*) ;;
      *) export GTK_MODULES="${GTK_MODULES:+$GTK_MODULES:}$nextspace_scroller_libdir/libnextspace-gtk3-scrollbars.so" ;;
    esac
  fi
  unset nextspace_scroller_libdir
fi
