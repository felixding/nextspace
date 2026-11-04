# Include before application.make/tool.make and set NEXTSPACE_SHELL_CLIENT to
# the GNUmake instance name. Keep generated code private to each build tree.
.DEFAULT_GOAL := all
NEXTSPACE_PROTOCOLS_DIR ?= ../../Protocols
NEXTSPACE_SHELL_GENERATED = .wayland-generated
NEXTSPACE_SHELL_HEADER = $(NEXTSPACE_SHELL_GENERATED)/nextspace-shell-v1-client-protocol.h
NEXTSPACE_SHELL_CODE = $(NEXTSPACE_SHELL_GENERATED)/nextspace-shell-v1-protocol.c
$(NEXTSPACE_SHELL_CLIENT)_C_FILES += $(NEXTSPACE_SHELL_CODE)
ADDITIONAL_INCLUDE_DIRS += -I$(NEXTSPACE_SHELL_GENERATED) `pkg-config --cflags wayland-client xkbcommon`
ADDITIONAL_GUI_LIBS += `pkg-config --libs wayland-client xkbcommon`
$(NEXTSPACE_SHELL_CLIENT)_TOOL_LIBS += `pkg-config --libs wayland-client xkbcommon`

$(NEXTSPACE_SHELL_HEADER): $(NEXTSPACE_PROTOCOLS_DIR)/nextspace-shell-v1.xml
	@mkdir -p $(NEXTSPACE_SHELL_GENERATED)
	wayland-scanner client-header $< $@

$(NEXTSPACE_SHELL_CODE): $(NEXTSPACE_PROTOCOLS_DIR)/nextspace-shell-v1.xml
	@mkdir -p $(NEXTSPACE_SHELL_GENERATED)
	wayland-scanner private-code $< $@

# Depend on the header on the first build, before compiler-generated .d files.
# GNUstep defines these object paths only in its instance invocation.
ifneq ($(GNUSTEP_INSTANCE),)
$(GNUSTEP_OBJ_INSTANCE_DIR)/WSShellConnection.m$(OEXT): $(NEXTSPACE_SHELL_HEADER)
endif
