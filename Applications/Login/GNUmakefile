#
# GNUmakefile
#

GNUSTEP_INSTALLATION_DOMAIN = SYSTEM
include $(GNUSTEP_MAKEFILES)/common.make

#GNUSTEP_BUILD_DIR = /Users/me/Projects/==BUILD==/Login.build

CC=clang

#
# Application
#
VERSION = 0.8
NEXTSPACE_BUILD_WAYLAND ?= 1
ifeq ($(NEXTSPACE_BUILD_WAYLAND),1)
ADDITIONAL_CPPFLAGS += -DNEXTSPACE_BUILD_WAYLAND=1
endif
PACKAGE_NAME = Login
APP_NAME = Login
Login_APPLICATION_ICON = loginwindow.tiff
Login_MAIN_MODEL_FILE = Login


#
# Subprojects
#
SUBPROJECTS = \
Preferences

#
# Resource files
#
Login_RESOURCE_FILES = \
	Resources/Login.gorm \
	Resources/ConsoleLog.gorm \
	Resources/loginwindow.tiff \
	Resources/Login \
	Resources/Login.user \
	Preferences/Login.preferences


#
# Header files
#
Login_HEADER_FILES = \
Controller.h \
LoginWindow.h
Login_HEADER_FILES += GreetdClient.h GreetdSession.h

#
# Class files
#
Login_OBJC_FILES = \
Controller.m \
LoginWindow.m \
UserSession.m
Login_OBJC_FILES += GreetdClient.m GreetdSession.m Controller+Native.m

#
# Other sources
#
Login_OBJC_FILES += \
Login_main.m 

TOOL_NAME = nextspace-session-hook
nextspace-session-hook_OBJC_FILES = SessionHook.m

#
# Makefiles
#
-include GNUmakefile.preamble
include $(GNUSTEP_MAKEFILES)/aggregate.make
include $(GNUSTEP_MAKEFILES)/application.make
include $(GNUSTEP_MAKEFILES)/tool.make
-include GNUmakefile.postamble
