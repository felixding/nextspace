/* Shared popup data transport only. NativeUI owns every widget operation.
 * Include after Protocol.h and Transport.inc. GPL-2.0-or-later. */
static struct NXSControlPopupRequest *native_popup_model_new(int selected)
{
  struct NXSControlPopupRequest *request=calloc(1,sizeof(*request)+65536);
  if(request)*request=(struct NXSControlPopupRequest){.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=11,
    .process=identity(),.kind=6,.selected=selected};
  return request;
}
static int native_popup_model_append(struct NXSControlPopupRequest *request,const char *title,int enabled,int separator)
{
  if(!request||!title||request->count>=65536||request->text_size>65536)return 0;
  size_t size=strnlen(title,65537);
  if(size>65536||8+size>65536-request->text_size)return 0;
  uint32_t flags=!!enabled|((uint32_t)!!separator<<1),length=size;
  unsigned char *body=(unsigned char *)(request+1)+request->text_size;
  memcpy(body,&flags,4);memcpy(body+4,&length,4);memcpy(body+8,title,size);
  request->text_size+=8+size;request->count++;return 1;
}
static struct NXSResponse *native_popup_title(uint64_t control,const char *title)
{
  size_t length=title?strnlen(title,65537):0;if(!control||length>65536)return NULL;
  struct NXSControlRequest *request=calloc(1,sizeof(*request)+length);if(!request)return NULL;
  *request=(struct NXSControlRequest){.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=42,.process=identity(),
    .kind=6,.control=control,.state=title!=NULL,.text_size=length};
  if(length)memcpy(request+1,title,length);
  struct NXSResponse *response=exchange_bytes(request,sizeof(*request)+length);free(request);
  return response&&response->parts[3].x==1?response:NULL;
}
