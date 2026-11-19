/* Publish a standard toolkit token; contains no native window/focus policy.
 * Include after Protocol.h and Transport.inc. GPL-2.0-or-later. */
static int native_auxiliary_token_publish_query(uint64_t surface,uint32_t serial,const char *token,const char *parent,uint32_t query)
{
  size_t length=token?strlen(token):0;
  size_t parent_length=parent?strlen(parent):0;
  /* Zero serial means the original toolkit selected/consumed its own serial
   * internally (GDK launch contexts). The compositor still validates token. */
  if(!surface||(token&&!length)||length>4096||parent_length>4096||(!token&&(serial||parent_length)))return 0;
  size_t payload=length+(parent_length?1+parent_length:0);
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=64,
    .process=identity(),.control=surface,.state=token?(parent_length?2:1):0,.x=serial,.text_size=payload,.value=query};
  unsigned char *bytes=malloc(sizeof(request)+payload);if(!bytes)return 0;
  memcpy(bytes,&request,sizeof(request));if(length)memcpy(bytes+sizeof(request),token,length);
  if(parent_length){bytes[sizeof(request)+length]=0;memcpy(bytes+sizeof(request)+length+1,parent,parent_length);}
  /* This is an atomic one-way SEQPACKET message, with no reply and no shared
   * request lock. The toolkit's Wayland dispatch must never wait for a renderer
   * that may in turn need the toolkit UI thread to finish its native action. */
  ssize_t sent=channel<0?-1:send(channel,bytes,sizeof(request)+payload,MSG_DONTWAIT|MSG_NOSIGNAL);
  free(bytes);return sent==(ssize_t)(sizeof(request)+payload);
}
static int native_auxiliary_token_publish(uint64_t surface,uint32_t serial,const char *token,const char *parent)
{return native_auxiliary_token_publish_query(surface,serial,token,parent,0);}
/* A real press delivered to the source client is outside a context menu
 * hosted on another Wayland connection. Forward that lifecycle fact without
 * another event reader, coordinate hit test or synchronous input wait. */
static void native_auxiliary_source_pointer(uint64_t surface)
{
  if(!surface||channel<0)return;
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=64,
    .process=identity(),.control=surface,.state=4};
  send(channel,&request,sizeof(request),MSG_DONTWAIT|MSG_NOSIGNAL);
}
/* The toolkit event loop services this private request endpoint. Only the
 * original toolkit creates tokens; the shared host requests one at actual
 * presentation rather than retaining an eagerly minted expiring grant. */
static int native_auxiliary_source_watch(void)
{
  int pair[2];if(socketpair(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC|SOCK_NONBLOCK,0,pair))return -1;
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=64,
    .process=identity(),.state=3};
  struct iovec buffer={&request,sizeof(request)};
  char ancillary[CMSG_SPACE(sizeof(int))]={0};
  struct msghdr message={.msg_iov=&buffer,.msg_iovlen=1,.msg_control=ancillary,.msg_controllen=sizeof(ancillary)};
  struct cmsghdr *control=CMSG_FIRSTHDR(&message);
  control->cmsg_level=SOL_SOCKET;control->cmsg_type=SCM_RIGHTS;control->cmsg_len=CMSG_LEN(sizeof(int));
  memcpy(CMSG_DATA(control),pair+1,sizeof(int));
  ssize_t sent=channel<0?-1:sendmsg(channel,&message,MSG_DONTWAIT|MSG_NOSIGNAL);
  close(pair[1]);if(sent!=sizeof(request)){close(pair[0]);return -1;}return pair[0];
}
