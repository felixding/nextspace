/* Shared placeholder model transport. Native cells own display and behavior.
 * Include after Transport.inc. GPL-2.0-or-later. */
static int native_text_placeholder(unsigned kind,uint64_t control,const char *value)
{
  size_t length=value?strlen(value):0;
  if(length>65536)return 0;
  size_t size=sizeof(struct NXSControlRequest)+length;
  struct NXSControlRequest *request=calloc(1,size);if(!request)return 0;
  *request=(struct NXSControlRequest){.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=54,
    .process=identity(),.kind=kind,.control=control,.text_size=length,.state=value!=NULL};
  if(length)memcpy(request+1,value,length);
  struct NXSResponse *response=exchange_bytes(request,size);free(request);
  return response&&response->parts[3].x==1;
}
