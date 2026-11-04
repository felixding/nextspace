#
#  GNUmakefile
#

GNUSTEP_INSTALLATION_DOMAIN = SYSTEM

include $(GNUSTEP_MAKEFILES)/common.make

NEXTSPACE_BUILD_WAYLAND ?= 1
PACKAGE_NAME = Workspace
VERSION = 0.8
REVISION := "$(shell git log -n 1 --date=short --format=format:"%h, %ad" 2>/dev/null || echo unknown)"
APP_NAME = Workspace
OS_NAME=`./os-release`
$(APP_NAME)_APPLICATION_ICON = app-$(OS_NAME)-48.tiff
$(APP_NAME)_MAIN_MODEL_FILE = WorkspaceManager

SUBPROJECTS = \
	Viewers/BrowserViewer \
	Viewers/IconViewer \
	Inspectors \
	Tools/FileMover \
	Tools/Sizer \
	Preferences/Advanced \
	Preferences/Browser \
	Preferences/Dock \
	Preferences/FileCopyOptions \
	Preferences/IconView \
	Preferences/Shelf \
	Preferences/Desktops

$(APP_NAME)_OBJC_FILES = \
	$(filter-out DisplayProfile.m ScreenCastChooser.m WSShellConnection.m WaylandWindowManager.m,$(wildcard *.m)) \
	$(wildcard Viewers/*.m) \
	$(wildcard Operations/*.m) \
	$(wildcard Processes/*.m)

# The supported desktop is native Wayland. Historical X11 sources are excluded.
ifeq ($(NEXTSPACE_BUILD_WAYLAND),1)
$(APP_NAME)_OBJC_FILES := $(filter-out X11Session.m X11WindowManager.m Workspace+WM.m WMNotificationCenter.m RecyclerIcon.m Processes/ProcessManager+X11.m,$($(APP_NAME)_OBJC_FILES))
$(APP_NAME)_OBJC_FILES += WSShellConnection.m WaylandWindowManager.m
ADDITIONAL_CPPFLAGS += -DNEXTSPACE_BUILD_WAYLAND=1
NEXTSPACE_FRAMEWORKS_DIR ?= ../../Frameworks
ADDITIONAL_INCLUDE_DIRS += -I$(NEXTSPACE_FRAMEWORKS_DIR)
NEXTSPACE_SHELL_CLIENT = Workspace
NEXTSPACE_PROTOCOLS_DIR ?= ../../Protocols
include $(NEXTSPACE_PROTOCOLS_DIR)/shell-client.make
TOOL_NAME = nextspace-display-profile nextspace-screencast-chooser
nextspace-display-profile_OBJC_FILES = DisplayProfile.m WSShellConnection.m
nextspace-display-profile_C_FILES = $(NEXTSPACE_SHELL_CODE)
nextspace-display-profile_TOOL_LIBS = -lSystemKit -lgnustep-gui `pkg-config --libs wayland-client xkbcommon`
nextspace-screencast-chooser_OBJC_FILES = ScreenCastChooser.m
nextspace-screencast-chooser_TOOL_LIBS = -lgnustep-gui
endif

$(APP_NAME)_RESOURCE_FILES = \
	$(wildcard Resources/*) \
	Inspectors/Inspectors.bundle \
	$(wildcard Processes/English.lproj)

# Window manager
WM_DIR = WM
ifneq ($(NEXTSPACE_BUILD_WAYLAND),1)
include GNUmakefile.WM
endif

$(APP_NAME)_LOCALIZED_RESOURCE_FILES = $(notdir $(wildcard English.lproj/*))

$(APP_NAME)_LANGUAGES = $(basename $(wildcard *.lproj))

$(APP_NAME)_HEADER_FILES = Inspectors/Workspace.h
$(APP_NAME)_HEADER_FILES_INSTALL_DIR = $(GNUSTEP_SYSTEM_HEADERS)/Applications

-include GNUmakefile.preamble
include $(GNUSTEP_MAKEFILES)/aggregate.make
include $(GNUSTEP_MAKEFILES)/application.make
ifeq ($(NEXTSPACE_BUILD_WAYLAND),1)
include $(GNUSTEP_MAKEFILES)/tool.make
endif
include $(GNUSTEP_MAKEFILES)/Instance/Shared/headers.make
-include GNUmakefile.postamble
