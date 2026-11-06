/* Optional exact-build Gecko adapter. NativeUI supplies the actual controls.
 * Firefox/libxul stay unchanged. GPL-2.0-or-later. */
#define _GNU_SOURCE
#if !defined(__aarch64__) || !defined(__clang__)
#error "The pinned Firefox adapter requires Clang on AArch64 for its naked ABI wrappers"
#endif
#include "../../Libraries/NativeUI/Bridge/Protocol.h"
#include <dlfcn.h>
#include <elf.h>
#include <fcntl.h>
#include <link.h>
#include <math.h>
#include <stddef.h>
#include <stdio.h>
#include <stdint.h>
#include <unistd.h>
#include <sys/eventfd.h>
#include <time.h>
#include "../../Libraries/NativeUI/NativeUI.h"
static uintptr_t base;
static int log_fd=-1,installed;
static void note(const char *message) {if(log_fd>=0)dprintf(log_fd,"%d %s\n",getpid(),message);}
#include "../../Libraries/NativeUI/Bridge/Transport.inc"
static void writable(void *p,size_t size,int protect) {
  uintptr_t start=(uintptr_t)p&~(uintptr_t)(getpagesize()-1);
  size_t length=((uintptr_t)p+size-start+getpagesize()-1)&~(size_t)(getpagesize()-1);
  if(mprotect((void *)start,length,protect))abort();
}
#include "../../Libraries/NativeUI/Bridge/AArch64Detours.inc"
struct RectF {float x,y,width,height;};
struct ColorPattern {uintptr_t vptr;float red,green,blue,alpha;};
struct DrawOptions {float alpha;int8_t composition,antialias;uint8_t padding[2];};
_Static_assert(sizeof(struct NXSControlRequest)==104,"Shared control envelope");
_Static_assert(sizeof(struct ColorPattern)==24,"Pinned Gecko ColorPattern");
_Static_assert(sizeof(struct DrawOptions)==8,"Pinned Gecko DrawOptions");
typedef void (*ProgressPaint)(void *,void *,void *,const struct RectF *,const void *,const void *,const void *,int);
typedef int (*WebRenderPaint)(void *,void *,void *,void *,void *,void *,unsigned,const void *);
static ProgressPaint original_progress;
static WebRenderPaint original_webrender;

static void draw_bitmap(void *target,const struct RectF *rect,const uint32_t *pixels,int width,int height) {
  typedef void (*FillRect)(void *,const struct RectF *,const struct ColorPattern *,const struct DrawOptions *);
  FillRect fill=(FillRect)(*(uintptr_t **)target)[27];
  struct ColorPattern pattern={.vptr=base+0x9e21210+16};
  struct DrawOptions options={.alpha=1,.composition=1,.antialias=0};
  for(int y=0;y<height;y++)for(int x=0;x<width;) {
    uint32_t color=pixels[y*width+x];int end=x+1;
    while(end<width&&pixels[y*width+end]==color)end++;
    if(color>>24) {
      float alpha=(color>>24)/255.f;
      pattern.red=((color>>16)&255)/(255.f*alpha);
      pattern.green=((color>>8)&255)/(255.f*alpha);
      pattern.blue=(color&255)/(255.f*alpha);pattern.alpha=alpha;
      struct RectF run={rect->x+x,rect->y+y,end-x,1};fill(target,&run,&pattern,&options);
    }
    x=end;
  }
}
#include "controls.inc"
#include "menus.inc"
#include "../../Libraries/NativeUI/Bridge/Menu.inc"
#include "global-keys.inc"

/* Frame/content and model access are audited against this libxul, including
 * Gecko's own FromNode tag/namespace check. NativeUI has no DOM knowledge. */
static double progress_position(void *frame) {
  void *content=*(void **)((char *)frame+24);
  if(!content)return -2;
  void *info=*(void **)((char *)content+40);
  if(!info||*(uintptr_t *)((char *)info+16)!=base+0x1167eec||
     *(uint32_t *)((char *)info+32)!=3)return -2;
  return ((double (*)(const void *))(base+0x589f280))(content);
}
static int eligible(void *frame,unsigned appearance) {
  if(channel<0)return 0;
  if(texts_enabled&&native_text_frame(frame)&&widget_for_frame(frame)&&widget_for_frame(frame)->text_owned)return 1;
  if(widgets_enabled&&(appearance==4||appearance==5||(buttons_enabled&&appearance==10)||(sliders_enabled&&appearance==19))&&frame_kind(frame))return 1;
  if(appearance!=9)return 0;
  double position=progress_position(frame);
  return isfinite(position)&&position>=0&&position<=1;
}
static int webrender(void *self,void *builder,void *resources,void *stacking,
    void *manager,void *frame,unsigned appearance,const void *rect) {
  /* Gecko's existing fallback paints this display item into its DrawTarget.
   * Other controls retain their existing rendering and model paths. */
  if(eligible(frame,appearance))return 0;
  return original_webrender(self,builder,resources,stacking,manager,frame,appearance,rect);
}
static void progress(void *self,void *frame,void *target,const struct RectF *rect,
    const void *state,const void *colors,const void *dpi,int meter) {
  double value=meter?-2:progress_position(frame);
  /* The current bitmap transport draws generic controls at scale 1. Preserve
   * Gecko's path until that transport can request the provider's scaled draw. */
  float scale=dpi?*(const float *)dpi:0;
  if(!isfinite(scale)||fabsf(scale-1)>0.000001f||!isfinite(value)||value<0||value>1||!rect||
     !isfinite(rect->x)||!isfinite(rect->y)||!isfinite(rect->width)||!isfinite(rect->height)||
     rect->width<1||rect->height<1||rect->width>8192||rect->height>8192)goto fallback;
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=1,
    .process=identity(),.kind=5,.control=(uintptr_t)frame,
    .width=rect->width,.height=rect->height,.maximum=1,.value=value,.enabled=1};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
  uint32_t *pixels=NULL;int width=0,height=0;
  if(response&&response->width>0&&response->height>0&&response->width<=8192&&response->height<=8192&&
     response->stride==response->width*4&&
     sizeof(*response)+(size_t)response->stride*response->height==response->size) {
    width=response->width;height=response->height;
    pixels=malloc((size_t)response->stride*height);
    if(pixels)memcpy(pixels,response+1,(size_t)response->stride*height);
  }
  /* Determinate indicators are read-only. Release this actual native object
   * after each snapshot; no frame-pointer cache can outlive a Gecko frame. */
  request.operation=6;exchange_bytes(&request,sizeof(request));
  if(!pixels)goto fallback;
  draw_bitmap(target,rect,pixels,width,height);free(pixels);
  if(log_fd>=0)dprintf(log_fd,"%d native-progress frame=%p value=%.17g rect=%.0f,%.0f %dx%d\n",getpid(),frame,value,rect->x,rect->y,width,height);
  return;
fallback:
  original_progress(self,frame,target,rect,state,colors,dpi,meter);
}
static const unsigned char progress_bytes[]={0x3f,0x23,0x03,0xd5,0xff,0x43,0x04,0xd1,0xe9,0x23,0x0a,0x6d,0xfd,0x7b,0x0b,0xa9,0xfc,0x6f,0x0c,0xa9};
static const unsigned char wr_bytes[]={0x3f,0x23,0x03,0xd5,0xff,0x03,0x01,0xd1,0xfe,0x1b,0x00,0xf9,0x08,0xc4,0x01,0xf0,0x08,0x89,0x44,0xf9};
static struct Detour detours[]={
  {0x6a77614,progress_bytes,progress,(void **)&original_progress},
  {0x6a60354,wr_bytes,webrender,(void **)&original_webrender}
};
static int find_xul(struct dl_phdr_info *info,size_t size,void *unused) {
  if(!info->dlpi_name||!strstr(info->dlpi_name,"/libxul.so"))return 0;
  static const unsigned char expected[]={0xac,0xe6,0x00,0x69,0x74,0x90,0xec,0x16,0x9e,0x3e,0x37,0x1f,0xb4,0x56,0xdc,0xb5,0x42,0xe3,0xab,0xef};
  for(int i=0;i<info->dlpi_phnum;i++)if(info->dlpi_phdr[i].p_type==PT_NOTE) {
    const unsigned char *p=(void *)(info->dlpi_addr+info->dlpi_phdr[i].p_vaddr),*end=p+info->dlpi_phdr[i].p_memsz;
    while(p+12<=end) {
      const ElfW(Nhdr)*n=(void *)p;const unsigned char *name=p+12,*description=name+((n->n_namesz+3)&~3);
      if(description>end||n->n_descsz>(size_t)(end-description))break;
      if(n->n_type==NT_GNU_BUILD_ID&&n->n_descsz==20&&n->n_namesz==4&&!memcmp(name,"GNU",4)&&!memcmp(description,expected,20))base=info->dlpi_addr;
      p=description+((n->n_descsz+3)&~3);
    }
  }
  return 1;
}
static void install(void) {
  if(installed||channel<0)return;
  dl_iterate_phdr(find_xul,NULL);if(!base)return;
  uintptr_t *table=(uintptr_t *)(base+0x9e22190+16);
  if(table[27]!=base+0x3fc3108||*(uintptr_t *)(base+0x9e21210+32)!=base+0x316fee8||
     memcmp((void *)(base+0x6a7782c),(unsigned char[]){0x00,0x0f,0x40,0xf9},4)||
     memcmp((void *)(base+0x589f280),(unsigned char[]){0x5f,0x24,0x03,0xd5,0x00,0x10,0x7e,0x1e},8)||
     !prepare_detours(detours,sizeof(detours)/sizeof(*detours))) {note("Gecko layout/instruction guard failed; unchanged");return;}
  if(multiline_enabled&&!guard_multiline_calls()){note("Gecko multiline guard failed; unchanged");return;}
  if(multiline_viewport_enabled&&(!guard_viewport_calls()||!prepare_detours(viewport_detours,sizeof(viewport_detours)/sizeof(*viewport_detours)))){note("Gecko viewport guard failed; unchanged");return;}
  if(wheel_enabled&&(!guard_wheel_calls()||!prepare_detours(wheel_detours,sizeof(wheel_detours)/sizeof(*wheel_detours)))){note("Gecko wheel guard failed; unchanged");return;}
  if(widgets_enabled&&!prepare_detours(widget_detours,sizeof(widget_detours)/sizeof(*widget_detours))){note("Gecko interactive guard failed; unchanged");return;}
  if(buttons_enabled&&!prepare_detours(button_detours,sizeof(button_detours)/sizeof(*button_detours))){note("Gecko button guard failed; unchanged");return;}
  if(sliders_enabled&&!prepare_detours(range_detours,sizeof(range_detours)/sizeof(*range_detours))){note("Gecko range guard failed; unchanged");return;}
  if(texts_enabled&&(!guard_text_calls()||!prepare_detours(text_detours,sizeof(text_detours)/sizeof(*text_detours)))){note("Gecko text guard failed; unchanged");return;}
  if(texts_enabled&&!guard_text_commands()){note("Gecko text command guard failed; unchanged");return;}
  if(frontend_requested&&!prepare_frontend_bindings()){note("Gecko frontend guard failed; unchanged");return;}
  if(!prepare_menu_lifecycle()){note("Gecko external menu lifecycle guard failed; unchanged");return;}
  if(!prepare_global_keys()){note("Gecko global menu key guard failed; unchanged");return;}
  activate_detours(detours,sizeof(detours)/sizeof(*detours));
  if(widgets_enabled){activate_detours(widget_detours,sizeof(widget_detours)/sizeof(*widget_detours));note("native Gecko checkbox/radio bindings installed");}
  if(buttons_enabled){activate_detours(button_detours,sizeof(button_detours)/sizeof(*button_detours));note("native Gecko input buttons installed");}
  if(sliders_enabled){activate_detours(range_detours,sizeof(range_detours)/sizeof(*range_detours));note("native Gecko ranges installed");}
  if(texts_enabled){activate_detours(text_detours,sizeof(text_detours)/sizeof(*text_detours));note("native Gecko text bindings installed");}
  if(multiline_viewport_enabled){activate_detours(viewport_detours,sizeof(viewport_detours)/sizeof(*viewport_detours));note("native Gecko multiline viewport installed");}
  if(wheel_enabled){activate_detours(wheel_detours,sizeof(wheel_detours)/sizeof(*wheel_detours));note("native Gecko wheel binding installed");}
  if(frontend_requested){activate_detours(frontend_detours,sizeof(frontend_detours)/sizeof(*frontend_detours));note("native Gecko frontend text binding installed");}
  if(menu_lifecycle_requested){activate_detours(menu_lifecycle_detours,sizeof(menu_lifecycle_detours)/sizeof(*menu_lifecycle_detours));note("native Gecko external menu lifecycle binding installed");}
  if(menu_keys_requested){activate_detours(global_key_detours,sizeof(global_key_detours)/sizeof(*global_key_detours));note("native Gecko global menu key binding installed");}
  installed=1;
  note("exact-build Gecko native progress adapter installed");
}
void *dlopen(const char *path,int flags) {
  static void *(*next)(const char *,int);
  if(!next)next=dlsym(RTLD_NEXT,"dlopen");
  void *result=next(path,flags);
  if(result&&path&&strstr(path,"libxul.so"))install();
  return result;
}
__attribute__((constructor)) static void initialize(void) {
  const char *endpoint=getenv("NEXTSPACE_FIREFOX_SOCKET"),*log=getenv("NEXTSPACE_FIREFOX_LOG");
  if(!endpoint)return;
  if(log)log_fd=open(log,O_WRONLY|O_CREAT|O_APPEND|O_CLOEXEC,0600);
  if(!bridge_connect(endpoint))return;
  const char *input=getenv("NEXTSPACE_FIREFOX_INPUT");
  const char *menus=getenv("NEXTSPACE_FIREFOX_MENU_LIFECYCLE");
  menu_lifecycle_requested=menus&&!strcmp(menus,"1");
  if(input&&!strcmp(input,"1"))prepare_widget_metrics();
  const char *menu_keys=getenv("NEXTSPACE_FIREFOX_MENU_KEYS");
  menu_keys_requested=menu_keys&&!strcmp(menu_keys,"1")&&frontend_requested&&application_menu_keys;
  if(menu_keys&&!strcmp(menu_keys,"1")&&!menu_keys_requested)note("native global menu keys unavailable in this helper/configuration");
  note("Firefox native transport connected before sandbox");install();
}
