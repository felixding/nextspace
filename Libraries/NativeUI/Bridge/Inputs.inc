/* Shared native focus/key packet serializer; event metadata only.
 * Include after Transport.inc. GPL-2.0-or-later. */
#ifndef NXS_NATIVE_UI_INPUT_SERIALIZER
#define NXS_NATIVE_UI_INPUT_SERIALIZER
#include "../NativeUI.h"
static struct NXSResponse *native_control_input(unsigned kind,uint64_t control,int focused,const NXSKeyEvent *event)
{
  if(!control||(event&&event->size<sizeof(*event)))return NULL;
  size_t text=event&&event->text?strnlen(event->text,65537):0;
  size_t unmodified=event&&event->unmodified_text?strnlen(event->unmodified_text,65537):0;
  if(text+unmodified>65536)return NULL;
  size_t size=sizeof(struct NXSControlInputRequest)+text+unmodified;
  struct NXSControlInputRequest *request=calloc(1,size);if(!request)return NULL;
  *request=(struct NXSControlInputRequest){.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=event?8:7,
    .process=identity(),.kind=kind,.control=control,.focused=!!focused};
  if(event) {
    request->type=event->type;request->modifiers=event->modifiers;request->key=event->key;
    request->repeat=event->repeat;request->text_size=text;request->unmodified_size=unmodified;
    if(text)memcpy(request+1,event->text,text);
    if(unmodified)memcpy((char *)(request+1)+text,event->unmodified_text,unmodified);
  }
  struct NXSResponse *response=exchange_bytes(request,size);free(request);return response;
}
#endif
