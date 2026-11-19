/* GTK's existing LinuxUi command boundary feeds the stock Chromium editor.
 * GNUstep supplies only command selection. GPL-2.0-or-later. */
#include "../../Libraries/NativeUI/Bridge/EditBindings.inc"
#include "pinned-edit-commands.h"

static int (*original_linux_edit_key)(void *,const void *,int);

static int chromium_edit_command(const char *selector)
{
  for(int i=0;i<CHROMIUM_EDIT_INVALID;i++)
    if(!strcmp(selector,chromium_edit_selectors[i]))return i;
  return CHROMIUM_EDIT_INVALID;
}

static int linux_edit_key(void *self,const void *event,int flags)
{
  unsigned key_flags=*(const unsigned *)((const char *)event+80);
  /* Keep the existing handling of AltGr, IME keys and vertical writing. */
  if(*(const int *)((const char *)event+8)!=7||
     !(views_modifiers(event)&(NXS_CONTROL|NXS_ALT|NXS_SUPER))||
     (key_flags&((1u<<6)|(1u<<16)))||(flags&(1u<<13))||
     context_menu_owns_keys()||!native_form_events_ready())
    return original_linux_edit_key(self,event,flags);

  NXSKeyEvent key=chromium_key_event(event);
  struct NXSResponse *response=key.text&&key.unmodified_text?
    native_edit_binding_request((uintptr_t)self,&key):NULL;
  chromium_key_event_free(key);
  if(response&&response->parts[3].x==NXS_EDIT_SEQUENCE) {
    /* LinuxUi returns a single command. Preserve Chromium's stock handling
     * for sequences that this boundary cannot deliver atomically. */
    native_edit_binding_request((uintptr_t)self,NULL);
  } else if(response&&response->parts[3].x==NXS_EDIT_COMMANDS&&response->size>sizeof(*response)) {
    const char *selector=(const char *)(response+1);
    size_t length=response->size-sizeof(*response);
    if(memchr(selector,0,length)==selector+length-1) {
      int command=chromium_edit_command(selector);
      if(command!=CHROMIUM_EDIT_INVALID)return command;
    }
  }
  return original_linux_edit_key(self,event,flags);
}

/* Actual GTK implementation reached through LinuxUi's virtual edit method. */
static const unsigned char linux_edit_key_bytes[20]={
  0x3f,0x23,0x03,0xd5,0xfd,0x7b,0xbd,0xa9,0xf4,0x4f,
  0x02,0xa9,0xf3,0x03,0x01,0xaa,0xf4,0x03,0x00,0xaa
};
static struct Detour linux_edit_key_detour={
  0x10e60104,linux_edit_key_bytes,linux_edit_key,(void **)&original_linux_edit_key
};
