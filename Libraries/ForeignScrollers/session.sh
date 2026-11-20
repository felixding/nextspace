# Sourced by the native user launcher when this optional package is installed.
# GPL-2.0-or-later.
if [ "${NEXTSPACE_TOOLKIT_UI:-on}" != off ]; then
  nextspace_scroller_libdir=${NEXTSPACE_SCROLLER_LIBDIR:-/usr/NextSpace/lib/nextspace-scrollbars}
  if [ -r "$nextspace_scroller_libdir/libnextspace-gtk-bootstrap.so" ]; then
    export GTK_CSD=${GTK_CSD:-0} GTK_USE_PORTAL=${GTK_USE_PORTAL:-1}
    if [ -z "${QT_QPA_PLATFORMTHEME:-}" ]; then
      for nextspace_qt_plugins in /usr/lib/*/qt6/plugins/platformthemes; do
        if [ -r "$nextspace_qt_plugins/KDEPlasmaPlatformTheme6.so" ]; then
          export QT_QPA_PLATFORMTHEME=kde
          if [ -r "$nextspace_qt_plugins/libqxdgdesktopportal.so" ]; then
            # Qt's portal decorator exports the Wayland parent and delegates
            # the application menu to the installed KDE platform theme.
            export QT_QPA_PLATFORMTHEME=xdgdesktopportal
            case ":${XDG_CURRENT_DESKTOP:-NEXTSPACE}:" in
              *:KDE:*) ;;
              *) export XDG_CURRENT_DESKTOP="${XDG_CURRENT_DESKTOP:-NEXTSPACE}:KDE" ;;
            esac
          fi
          break
        fi
      done
      unset nextspace_qt_plugins
    fi
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
