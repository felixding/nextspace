#
#  Main makefile for GNUstep Backend wayland
#
#  Copyright (C) 2020 Free Software Foundation, Inc.
#
#  Author: Adam Fedor <fedor@gnu.org>
#  Author: Sergio L. Pascual <slp@sinrega.org>
#  Author: Ladislav Michl <ladis@linux-mips.org>
#
#  This file is part of the GNUstep Backend.
#
#  This library is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
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

PACKAGE_NAME = gnustep-back
GNUSTEP_LOCAL_ADDITIONAL_MAKEFILES=../../back.make

include $(GNUSTEP_MAKEFILES)/common.make

include ../../config.make

# The library to be compiled, as a library or as a bundle
SUBPROJECT_NAME=wayland

wayland_LOCALIZED_RESOURCE_FILES = \

# The C source files to be compiled
wayland_C_FILES = \
generated/xdg-shell-protocol.c \
generated/xdg-decoration-unstable-v1-protocol.c \
generated/wlr-layer-shell-protocol.c \
generated/fractional-scale-v1-protocol.c \
generated/viewporter-protocol.c \
generated/xdg-output-unstable-v1-protocol.c \
generated/xdg-activation-v1-protocol.c \
generated/primary-selection-unstable-v1-protocol.c \
generated/text-input-unstable-v3-protocol.c \
generated/nextspace-application-v1-protocol.c \

# The Objective-C source files to be compiled
wayland_OBJC_FILES = \
WaylandServer.m  \
WaylandServer+Output.m  \
WaylandServer+Scale.m \
WaylandServer+Application.m \
WaylandServer+Decoration.m \
WaylandPasteboard.m \
WaylandServer+Cursor.m  \
WaylandCursor.m \
WaylandServer+Keyboard.m  \
WaylandServer+Seat.m  \
WaylandServer+Xdgshell.m  \
WaylandServer+Layershell.m  \
WaylandDragView.m  \
WaylandDragIcon.m \
WaylandInputServer.m  \

-include GNUmakefile.preamble

include $(GNUSTEP_MAKEFILES)/subproject.make

-include GNUmakefile.postamble
