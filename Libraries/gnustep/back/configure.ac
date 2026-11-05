#  configure.ac for GNUstep GUI Backend
#  Process this file with autoconf to produce a configure script.
#
#  Copyright (C) 1996-2015 Free Software Foundation, Inc.
#
#  Author:  Adam Fedor <fedor@gnu.org>
#
#  This file is part of the GNUstep Backend.
#
#  This library is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 3 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	 See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library; see the file COPYING.LIB.
#  If not, see <http://www.gnu.org/licenses/> or write to the 
#  Free Software Foundation, 51 Franklin Street, Fifth Floor, 
#  Boston, MA 02110-1301, USA.

builtin(include, pkg.m4)dnl

AC_INIT
AC_PREREQ(2.57)
AC_CONFIG_SRCDIR([back.make.in])
AC_CONFIG_HEADER(config.h)

# If GNUSTEP_MAKEFILES is undefined, try to use gnustep-config to determine it.
if test -z "$GNUSTEP_MAKEFILES"; then
  GNUSTEP_MAKEFILES=`gnustep-config --variable=GNUSTEP_MAKEFILES 2>&5`
fi

if test -z "$GNUSTEP_MAKEFILES"; then
  AC_MSG_ERROR([You must have the gnustep-make package installed and set up the GNUSTEP_MAKEFILES environment variable to contain the path to the makefiles directory before configuring!])
fi

#--------------------------------------------------------------------
# Use config.guess, config.sub and install-sh provided by gnustep-make
#--------------------------------------------------------------------
AC_CONFIG_AUX_DIR($GNUSTEP_MAKEFILES)

#--------------------------------------------------------------------
# Determine the host, build, and target systems
#--------------------------------------------------------------------
AC_CANONICAL_TARGET([])

#--------------------------------------------------------------------
# Find the compiler
#--------------------------------------------------------------------
MAKECC=`gnustep-config --variable=CC`
MAKECPP=`gnustep-config --variable=CPP`
MAKECXX=`gnustep-config --variable=CXX`
if test "$CC" = ""; then
  CC=$MAKECC
else
  if test "$CC" != "$MAKECC"; then
    AC_MSG_WARN([You are running configure with the compiler ($CC) set to a different value from that used by gnustep-make ($MAKECC).  To a
void conflicts/problems, reconfigure/reinstall gnustep-make to use $CC or run the gnustep-base configure again with your CC environment var
iable set to $MAKECC])
  fi
fi
if test "$CPP" = ""; then
  CPP=$MAKECPP
else
  if test "$CPP" != "$MAKECPP"; then
    AC_MSG_WARN([You are running configure with the preprocessor ($CPP) set to a different value from that used by gnustep-make ($MAKECPP).
  To avoid conflicts/problems, reconfigure/reinstall gnustep-make to use $CPP or run the gnustep-base configure again with your CPP environ
ment variable set to $MAKECPP])
  fi
fi
if test "$CXX" = ""; then
  CXX=$MAKECXX
else
  if test "$CXX" != "$MAKECXX"; then
    AC_MSG_WARN([You are running configure with the compiler ($CXX) set to a different value from that used by gnustep-make ($MAKECXX).  To
 avoid conflicts/problems, reconfigure/reinstall gnustep-make to use $CXX or run the gnustep-base configure again with your CXX environment
 variable set to $MAKECXX])
  fi
fi
AC_PROG_CC
AC_PROG_CPP

#--------------------------------------------------------------------
# The following is so that headers and custom libraries
# in the GNUstep root are used before the standard ones
#--------------------------------------------------------------------
GRAPHIC_CFLAGS="$CPPFLAGS"
GRAPHIC_LFLAGS="$LDFLAGS"

#
# It looks like we ought to source the whole GNUstep.sh here, and even
# ask it to output all variables!  That way we have access to (eg)
# GNUSTEP_SYSTEM_HEADERS below.
#
GNUSTEP_SH_EXPORT_ALL_VARIABLES=yes
. "$GNUSTEP_MAKEFILES/GNUstep.sh"
unset GNUSTEP_SH_EXPORT_ALL_VARIABLES

# For backwards compatibility, define GNUSTEP_SYSTEM_HEADERS from
# GNUSTEP_SYSTEM_ROOT if not set yet.
if test x"$GNUSTEP_SYSTEM_HEADERS" = x""; then
  GNUSTEP_SYSTEM_HEADERS="$GNUSTEP_SYSTEM_ROOT/Library/Headers"
fi

if test x"$GNUSTEP_SYSTEM_LIBRARIES" = x""; then
  GNUSTEP_SYSTEM_LIBRARIES="$GNUSTEP_SYSTEM_ROOT/Library/Libraries"
fi

if test "$GNUSTEP_IS_FLATTENED" = no; then
  clean_target_os=`$GNUSTEP_MAKEFILES/clean_os.sh $target_os`
  clean_target_cpu=`$GNUSTEP_MAKEFILES/clean_cpu.sh $target_cpu`
  obj_dir=$clean_target_cpu/$clean_target_os
  GNUSTEP_LDIR=$GNUSTEP_SYSTEM_LIBRARIES/$obj_dir
  GNUSTEP_HDIR=$GNUSTEP_SYSTEM_HEADERS/$LIBRARY_COMBO
else
  GNUSTEP_LDIR=$GNUSTEP_SYSTEM_LIBRARIES
  GNUSTEP_HDIR=$GNUSTEP_SYSTEM_HEADERS
fi
CPPFLAGS="$CPPFLAGS -I$GNUSTEP_HDIR"
LDFLAGS="$LDFLAGS -L$GNUSTEP_LDIR/$LIBRARY_COMBO -L$GNUSTEP_LDIR"

#--------------------------------------------------------------------
# Add target OS directories as necessary
#--------------------------------------------------------------------
case "$target_os" in
  freebsd* | openbsd* )   
	      CPPFLAGS="-I/usr/pkg/include $CPPFLAGS"
              LDFLAGS="-L/usr/pkg/lib $LDFLAGS";;
  netbsd*)    CPPFLAGS="-I/usr/pkg/include $CPPFLAGS"
	      LDFLAGS="-Wl,-R/usr/pkg/lib -L/usr/pkg/lib $LDFLAGS";;
esac

#--------------------------------------------------------------------
# These headers/functions needed by gpbs.m
#--------------------------------------------------------------------
AC_CHECK_HEADERS(syslog.h)
AC_CHECK_FUNCS(syslog)

#--------------------------------------------------------------------
# Find TIFF (Solaris requires this to find the correct library, even though
# it does not link directly to it)
#--------------------------------------------------------------------
AC_ARG_WITH(tiff_library,
           [  --with-tiff-library=DIR TIFF library file are in DIR], ,
           with_tiff_library=)

if test -n "$with_tiff_library"; then
  GRAPHIC_LFLAGS="$GRAPHIC_LFLAGS -L$with_tiff_library"
fi

#--------------------------------------------------------------------
# Native Wayland and Cairo dependencies
#--------------------------------------------------------------------
AC_ARG_ENABLE(server,
  [  --enable-server=wayland Build the native Wayland server],,
  enable_server=wayland)
AC_ARG_ENABLE(graphics,
  [  --enable-graphics=cairo Build the Cairo renderer],,
  enable_graphics=cairo)
AS_IF([test "$enable_server" != wayland],
  [AC_MSG_ERROR([Only the native Wayland server is supported])])
AS_IF([test "$enable_graphics" != cairo],
  [AC_MSG_ERROR([Wayland requires the Cairo renderer])])
BUILD_SERVER=wayland
BUILD_GRAPHICS=cairo

PKG_PROG_PKG_CONFIG
PKG_CHECK_MODULES([WAYLAND], [wayland-client >= 1.21 wayland-cursor xkbcommon])
PKG_CHECK_MODULES([CAIRO], [cairo cairo-ft freetype2 fontconfig libpng])
AC_PATH_PROG([WAYLAND_SCANNER], [wayland-scanner])
AS_IF([test -z "$WAYLAND_SCANNER"],
  [AC_MSG_ERROR([Wayland requires wayland-scanner])])
AC_CHECK_FUNCS([usleep])

CPPFLAGS="$GRAPHIC_CFLAGS $WAYLAND_CFLAGS $CAIRO_CFLAGS"
LDFLAGS="$GRAPHIC_LFLAGS"
LIBS="$WAYLAND_LIBS $CAIRO_LIBS $LIBS"

AH_TOP([
#define SERVER_wayland  3
#define GRAPHICS_cairo  4
])
AC_DEFINE_UNQUOTED(BUILD_SERVER,SERVER_wayland,
  [Define to the native Wayland window server])
AC_DEFINE_UNQUOTED(BUILD_GRAPHICS,GRAPHICS_cairo,
  [Define to the Cairo graphics context])
AC_SUBST(BUILD_SERVER)
AC_SUBST(BUILD_GRAPHICS)

#--------------------------------------------------------------------
# Check for -Wdeclaration-after-statement
#--------------------------------------------------------------------
AC_MSG_CHECKING(whether the compiler supports -Wdeclaration-after-statement)

saved_CFLAGS="$CFLAGS"
CFLAGS="$CFLAGS -Wdeclaration-after-statement"
AC_COMPILE_IFELSE([AC_LANG_PROGRAM()],HAS_W_DECL_AFTER_STATEMENT=yes,HAS_W_DECL_AFTER_STATEMENT=no)
CFLAGS="$saved_CFLAGS"

AC_MSG_RESULT($HAS_W_DECL_AFTER_STATEMENT)

if test x"$HAS_W_DECL_AFTER_STATEMENT" = x"yes"; then
  WARN_FLAGS="-Wall -Wdeclaration-after-statement"
else
  WARN_FLAGS=-Wall
fi

AC_SUBST(WARN_FLAGS)

#--------------------------------------------------------------------
# Set the name of the backend
#--------------------------------------------------------------------
AC_ARG_WITH(name, 
           [  --with-name=PREFIX      Set the name of the backend (def=back)])
AC_MSG_CHECKING(Backend name)
if test "x$with_name" = "x"; then
 BACKEND_NAME=back
else
 BACKEND_NAME=${with_name}
fi
AC_MSG_RESULT($BACKEND_NAME)
AC_SUBST(BACKEND_NAME)

AC_CONFIG_FILES([back.make config.make])
AC_CONFIG_COMMANDS_POST([
  WAYLAND_SCANNER="$WAYLAND_SCANNER" sh "$srcdir/wayland-regenerate.sh" || exit 1
])
AC_OUTPUT

#
# Summary
#
echo "======================================="
echo " GNUstep backend configuration summary "
echo "======================================="
echo " Graphics library : $BUILD_GRAPHICS"
echo " Server           : $BUILD_SERVER"
echo " Backend name     : $BACKEND_NAME"
