/* Application-owned editing command transport. No binding rules or text
 * storage live in the bridge. Include after Transport.inc and NativeUI.h. */
static struct NXSResponse *native_edit_binding_request(uint64_t editor,const NXSKeyEvent *event)
{
  size_t text=event&&event->text?strlen(event->text):0;
  size_t plain=event&&event->unmodified_text?strlen(event->unmodified_text):0;
  if(!editor||text+plain>128)return NULL;
  struct {
    struct NXSControlInputRequest request;
    char keys[128];
  } message={.request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=NXS_EDIT_BINDINGS_OPERATION,
    .process=identity(),.control=editor,.text_size=text,.unmodified_size=plain,.focused=!!event}};
  if(event) {
    message.request.type=event->type;
    message.request.key=event->key;
    message.request.modifiers=event->modifiers;
    message.request.repeat=event->repeat;
    if(text)memcpy(message.keys,event->text,text);
    if(plain)memcpy(message.keys+text,event->unmodified_text,plain);
  }
  return exchange_bytes(&message,sizeof(message.request)+text+plain);
}
