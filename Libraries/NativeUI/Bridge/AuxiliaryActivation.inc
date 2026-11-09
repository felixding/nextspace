/* Publish a standard toolkit token; contains no native window/focus policy.
 * Include after Protocol.h and Transport.inc. GPL-2.0-or-later. */
static int native_auxiliary_token_publish(uint64_t surface,uint32_t serial,const char *token)
{
  size_t length=token?strlen(token):0;
  /* Zero serial means the original toolkit selected/consumed its own serial
   * internally (GDK launch contexts). The compositor still validates token. */
  if(!surface||!length||length>4096)return 0;
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=64,
    .process=identity(),.control=surface,.state=1,.x=serial,.text_size=length};
  unsigned char *bytes=malloc(sizeof(request)+length);if(!bytes)return 0;
  memcpy(bytes,&request,sizeof(request));memcpy(bytes+sizeof(request),token,length);
  /* This is an atomic one-way SEQPACKET message, with no reply and no shared
   * request lock. The toolkit's Wayland dispatch must never wait for a renderer
   * that may in turn need the toolkit UI thread to finish its native action. */
  ssize_t sent=channel<0?-1:send(channel,bytes,sizeof(request)+length,MSG_DONTWAIT|MSG_NOSIGNAL);
  free(bytes);return sent==(ssize_t)(sizeof(request)+length);
}
