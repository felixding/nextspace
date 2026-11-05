/* Exact-build ARM64 experiment. Never rebuild or overwrite Chromium.
 * Rendering, geometry and tracking are supplied by the separate NativeUI provider.
 * GPL-2.0-or-later. */
#define _GNU_SOURCE
#include "protocol.h"
#include <dlfcn.h>
#include <elf.h>
#include <errno.h>
#include <link.h>
#include <math.h>
#include <pthread.h>
#include <stddef.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <sys/eventfd.h>
#include <poll.h>
#include <unistd.h>
#include <fcntl.h>
#include <time.h>

struct Rect {int x,y,width,height;};
struct Flags {float color[4],width,miter;uint32_t bits;float hdr;void *objects[5];};
_Static_assert(sizeof(struct Flags)==72,"Pinned PaintFlags layout");
_Static_assert(sizeof(struct NXSControlRequest)==104,"Control request ABI");
_Static_assert(offsetof(struct NXSControlRequest,reserved)==28,"Shared control sequence offset");
_Static_assert(offsetof(struct NXSRequest,reserved)==28,"Shared scrollbar sequence offset");
static int log_fd=-1,draw_slot=-1;
static uintptr_t base;
static double native_thickness;
static __thread struct NXSRequest cached_request;
static __thread struct NXSResponse cached_response;
static void note(const char *text) {if(log_fd>=0)dprintf(log_fd,"%d %s\n",getpid(),text);}
#include "../../Libraries/NativeUI/Bridge/Transport.inc"

static struct NXSResponse *query(const void *bar,int layer,float value,int override_value) {
  if(!bar||channel<0||!shared)return NULL;
  const unsigned char *p=bar;
  int orientation=*(const int *)(p+16);
  struct Rect frame=*(const struct Rect *)(p+208);
  struct NXSRequest req={.magic=NXS_CHROMIUM_MAGIC,.operation=1,.process=identity(),.layer=layer,
    .control=(uintptr_t)bar,.horizontal=orientation==0,
    .length=orientation==0?frame.width:frame.height,
    .total=*(const int *)(p+36),.page=*(const int *)(p+32),
    .value=override_value?value:*(const float *)(p+40)};
  /* A forced, disabled scrollbar may have less content than its viewport.
   * NSScroller already handles that range; rejecting it here leaks Blink's
   * fallback artwork into an otherwise native control. */
  if((orientation!=0&&orientation!=1)||req.length<1||req.length>8192||req.total<0||req.page<1||!isfinite(req.value))return NULL;
  if(!layer&&cached_response.magic&&memcmp(&req,&cached_request,sizeof(req))==0)return &cached_response;
  struct NXSResponse *response=exchange(req);
  if(!response)return NULL;
  if(!layer) {req.reserved=0;cached_request=req;cached_response=*response;return &cached_response;}
  if(response->width<=0||response->height<=0||response->stride!=response->width*4||sizeof(*response)+(size_t)response->stride*response->height!=response->size)return NULL;
  return response;
}

static struct Rect part(const void *bar,int number) {
  struct NXSResponse *r=query(bar,0,0,0);
  if(!r)return *(const struct Rect *)((const char *)bar+208);
  struct Rect frame=*(const struct Rect *)((const char *)bar+208);
  struct NXSRectD n=r->parts[number];
  return (struct Rect){frame.x+lround(n.x),frame.y+lround(n.y),lround(n.width),lround(n.height)};
}
static struct Rect back(void*t,const void*b){return part(b,4);}
static struct Rect forward(void*t,const void*b){return part(b,5);}
static struct Rect track(void*t,const void*b){return part(b,6);}
static struct Rect thumb(void*t,const void*b){return part(b,2);}
static int minimum(void*t,const void*b) {struct NXSResponse*r=query(b,0,0,0);if(!r)return 16;return lround(r->parts[2].width<r->parts[2].height?r->parts[2].width:r->parts[2].height);}
static int position(void*t,const void*b,float value){struct NXSResponse*r=query(b,0,value,1);if(!r)return 0;return lround(*(const int *)((const char *)b+16)?r->parts[2].y-r->parts[6].y:r->parts[2].x-r->parts[6].x);}
static int track_position(void*t,const void*b){struct Rect r=track(t,b),f=*(const struct Rect *)((const char *)b+208);return *(const int *)((const char *)b+16)?r.y-f.y:r.x-f.x;}
static int track_length(void*t,const void*b){struct Rect r=track(t,b);return *(const int *)((const char *)b+16)?r.height:r.width;}
static int thickness(void*t,float scale,int width){return width==2?0:lround(native_thickness*scale);}
struct Color {float r,g,b,a;};
static struct Color transparent(void*t,const void*b){return (struct Color){0};}
static struct Rect zero_insets(void*t,const void*b){return (struct Rect){0};}
static int all_parts(void*t,const void*b,float old,float value){return -1;}
static int yes(void*t){return 1;}
static int no(void*t){return 0;}
static int has_thumb(void*t,const void*b){return *(const int *)((const char *)b+36)>*(const int *)((const char *)b+32);}

static int draw_native_bitmap(void *canvas,const uint32_t *pixels,int width,float origin_x,float origin_y,int first_x,int first_y,int last_x,int last_y) {
  typedef void (*Draw)(void *,const float *,const struct Flags *);
  Draw draw=(Draw)(*(uintptr_t **)canvas)[draw_slot];
  struct Flags flags={.miter=4,.bits=3u<<8,.hdr=-1};
  int rectangles=0;
  for(int y=first_y;y<last_y;y++) {
    int x=first_x;
    while(x<last_x) {
      uint32_t color=pixels[y*width+x];int end=x+1;
      while(end<last_x&&pixels[y*width+end]==color)end++;
      if(color>>24) {
        float alpha=(color>>24)/255.f;
        flags.color[0]=((color>>16)&255)/(255.f*alpha);flags.color[1]=((color>>8)&255)/(255.f*alpha);flags.color[2]=(color&255)/(255.f*alpha);flags.color[3]=alpha;
        float area[4]={origin_x+x,origin_y+y,origin_x+end,origin_y+y+1};draw(canvas,area,&flags);rectangles++;
      }
      x=end;
    }
  }
  return rectangles;
}

static void paint(void *theme,void *info,const void *bar,const struct Rect *rect,int layer) {
  struct NXSResponse *r=query(bar,layer,0,0);
  if(!r||draw_slot<0) {
    typedef void (*Original)(void*,void*,const void*,const struct Rect*);
    ((Original)(base+(layer==1?0xe906124:0xe906d0c)))(theme,info,bar,rect);return;
  }
  struct NXSResponse header=*r;
  uint32_t *pixels=malloc((size_t)header.stride*header.height);
  if(!pixels)return;
  memcpy(pixels,r+1,(size_t)header.stride*header.height);r=&header;
  static __thread int paint_count;
  if(paint_count++<16&&log_fd>=0)dprintf(log_fd,"%d paint layer=%d size=%dx%d color=%08x slot=%d\n",getpid(),layer,r->width,r->height,pixels[0],draw_slot);
  void *gc=*(void **)info;
  unsigned char recorder[128] __attribute__((aligned(16)))={0};
  typedef void (*Ctor)(void *,void *,const void *,int,const struct Rect *);
  typedef void (*Dtor)(void *);
  ((Ctor)(base+0xecefdf8))(recorder,gc,bar,layer==1?35:36,rect);
  /* Beginning a DrawingRecorder swaps GraphicsContext's active canvas. */
  void *canvas=*(void **)gc;
  if(!canvas){((Dtor)(base+0xecefea8))(recorder);free(pixels);return;}
  if(paint_count<=16&&log_fd>=0)dprintf(log_fd,"%d paint bounds %d,%d %dx%d knob %.0f,%.0f %.0fx%.0f\n",getpid(),rect->x,rect->y,rect->width,rect->height,r->parts[2].x,r->parts[2].y,r->parts[2].width,r->parts[2].height);
  float origin_x=rect->x,origin_y=rect->y;
  int first_x=0,first_y=0,last_x=r->width,last_y=r->height;
  if(layer==2) {
    struct NXSRectD knob=r->parts[2];
    first_x=lround(knob.x);first_y=lround(knob.y);last_x=first_x+lround(knob.width);last_y=first_y+lround(knob.height);
    origin_x-=knob.x;origin_y-=knob.y;
  }
  if(first_x<0)first_x=0;if(first_y<0)first_y=0;if(last_x>r->width)last_x=r->width;if(last_y>r->height)last_y=r->height;

  int rectangles=draw_native_bitmap(canvas,pixels,r->width,origin_x,origin_y,first_x,first_y,last_x,last_y);
  ((Dtor)(base+0xecefea8))(recorder);free(pixels);
  if(paint_count<=16&&log_fd>=0)dprintf(log_fd,"%d layer %d emitted %d rectangles\n",getpid(),layer,rectangles);
}
static void paint_track(void*t,void*i,const void*b,const struct Rect*r){paint(t,i,b,r,1);}
static void paint_thumb(void*t,void*i,const void*b,const struct Rect*r){}

static void writable(void *p,size_t size,int protect) {
  uintptr_t start=(uintptr_t)p&~(uintptr_t)(getpagesize()-1);
  size_t length=((uintptr_t)p+size-start+getpagesize()-1)&~(size_t)(getpagesize()-1);
  if(mprotect((void *)start,length,protect))abort();
}
static void set_slot(uintptr_t *table,int index,void *function){table[index]=(uintptr_t)function;}
static void configure(uintptr_t offset) {
  uintptr_t *table=(uintptr_t *)(base+offset);
  if(table[39]!=base+0xe906d0c||table[61]!=base+0xe906124){note("vtable guard failed");return;}
  writable((char *)table-1,65*8+1,PROT_READ|PROT_WRITE);
  /* This build's LLVM whole-program devirtualization reads constant bool
   * results from the byte preceding the vtable. Disable the nine-patch track
   * (bit 2); keep the solid-color thumb but make its color transparent. The
   * complete native control is painted into the track texture, including its
   * knob. Chromium 156 hard-codes Fluent mode and omits textured-thumb quads. */
  *((unsigned char *)table-1)&=~4u;
  set_slot(table,15,all_parts);set_slot(table,18,transparent);set_slot(table,48,zero_insets);
  set_slot(table,4,yes);set_slot(table,6,thickness);set_slot(table,26,position);set_slot(table,27,track_position);set_slot(table,28,track_length);
  set_slot(table,30,yes);set_slot(table,31,yes);set_slot(table,32,has_thumb);set_slot(table,33,back);set_slot(table,34,forward);set_slot(table,35,track);set_slot(table,36,thumb);set_slot(table,37,minimum);
  set_slot(table,39,paint_thumb);set_slot(table,46,no);set_slot(table,47,yes);set_slot(table,49,no);set_slot(table,61,paint_track);
  writable((char *)table-1,65*8+1,PROT_READ);note("native theme vtable installed");
}
static void form_native_work(void *controller);
#include "input.inc"
#include "forms.inc"

static int main_object(struct dl_phdr_info *info,size_t size,void *unused) {
  if(info->dlpi_name&&*info->dlpi_name)return 0;
  static const unsigned char expected[20]={0xee,0xee,0xf0,0x3b,0x83,0x09,0x69,0x58,0xe9,0xeb,0x63,0x85,0xa4,0xa9,0x2a,0xa8,0xd2,0xaa,0x40,0x4e};
  for(int i=0;i<info->dlpi_phnum;i++)if(info->dlpi_phdr[i].p_type==PT_NOTE) {
    const unsigned char *p=(void *)(info->dlpi_addr+info->dlpi_phdr[i].p_vaddr),*end=p+info->dlpi_phdr[i].p_memsz;
    while(p+12<=end) {
      const ElfW(Nhdr)*n=(void *)p;const unsigned char*name=p+12,*description=name+((n->n_namesz+3)&~3);
      if(n->n_type==NT_GNU_BUILD_ID&&n->n_descsz==20&&n->n_namesz==4&&!memcmp(name,"GNU",4)&&!memcmp(description,expected,20)){base=info->dlpi_addr;return 1;}
      p=description+((n->n_descsz+3)&~3);
    }
  }
  return 1;
}
__attribute__((constructor)) static void initialize(void) {
  const char *socket_path=getenv("NEXTSPACE_CHROMIUM_SOCKET"),*log=getenv("NEXTSPACE_CHROMIUM_LOG");
  if(!socket_path||strlen(socket_path)>=sizeof(((struct sockaddr_un *)0)->sun_path))return;
  if(log)log_fd=open(log,O_WRONLY|O_CREAT|O_APPEND|O_CLOEXEC,0600);
  dl_iterate_phdr(main_object,NULL);if(!base){note("unsupported build; unchanged");return;}
  uintptr_t *canvas=(uintptr_t *)(base+0x11c24240);
  for(int i=2;i<100;i++)if(canvas[i]==base+0xb0fe62c){draw_slot=i-2;break;}
  if(draw_slot<0){note("canvas guard failed; unchanged");return;}
  if(!bridge_connect(socket_path))return;
  struct NXSResponse *metrics=exchange((struct NXSRequest){.magic=NXS_CHROMIUM_MAGIC,.operation=7,.process=identity()});
  if(!metrics||!isfinite(metrics->parts[0].width)||metrics->parts[0].width<1||metrics->parts[0].width>256) {
    note("native metrics unavailable; unchanged");return;
  }
  native_thickness=metrics->parts[0].width;
  const char *forms=getenv("NEXTSPACE_CHROMIUM_FORMS");
  forms_available=forms&&!strcmp(forms,"1")&&metrics->parts[0].height;
  if(isfinite(metrics->parts[4].width)&&metrics->parts[4].width>=0&&metrics->parts[4].width<=3)
    forms_input_capabilities=(unsigned)metrics->parts[4].width;
  const char *input=getenv("NEXTSPACE_CHROMIUM_INPUT");
  forms_input_enabled=forms_available&&input&&!strcmp(input,"1")&&
    (forms_input_capabilities&(NXS_INPUT_FOCUS|NXS_INPUT_KEYBOARD))==(NXS_INPUT_FOCUS|NXS_INPUT_KEYBOARD);
  for(int kind=2;kind<=3;kind++) {
    double width=metrics->parts[kind-1].width,height=metrics->parts[kind-1].height;
    if(!isfinite(width)||!isfinite(height)||width<1||height<1||width>256||height>256)forms_available=0;
    else form_sizes[kind]=(struct SizeI){ceil(width),ceil(height)};
  }
  forms_input_enabled=forms_input_enabled&&forms_available;
  forms_notifications_enabled=metrics->parts[6].x==1;
  const char *progress=getenv("NEXTSPACE_CHROMIUM_PROGRESS");
  forms_progress_enabled=forms_available&&progress&&!strcmp(progress,"1");
  const char *animation=getenv("NEXTSPACE_CHROMIUM_ANIMATION");
  forms_animation_enabled=forms_progress_enabled&&animation&&!strcmp(animation,"1")&&metrics->parts[4].height==1;
  const char *sliders=getenv("NEXTSPACE_CHROMIUM_SLIDERS");
  forms_sliders_enabled=forms_input_enabled&&sliders&&!strcmp(sliders,"1")&&metrics->parts[4].height==1&&metrics->parts[5].width==1;
  const char *popups=getenv("NEXTSPACE_CHROMIUM_POPUPS");
  forms_popups_enabled=forms_input_enabled&&popups&&!strcmp(popups,"1")&&metrics->parts[4].height==1&&metrics->parts[6].width==1&&metrics->parts[6].height==1;
  const char *text=getenv("NEXTSPACE_CHROMIUM_TEXT");
  forms_text_enabled=forms_input_enabled&&text&&!strcmp(text,"1")&&metrics->parts[6].x==1&&((unsigned)metrics->parts[6].y&3)==3;
  uintptr_t *aura=(uintptr_t *)(base+0x11d4fe40),*fluent=(uintptr_t *)(base+0x11d50048);
  if(aura[39]!=base+0xe906d0c||aura[61]!=base+0xe906124||fluent[39]!=base+0xe906d0c||fluent[61]!=base+0xe906124){note("theme guard failed; unchanged");return;}
  const uintptr_t offsets[]={0xe80ebec,0xe428628,0xe590960};
  const unsigned char originals[][12]={{0x5f,0x24,0x03,0xd5,0x08,0x38,0x80,0xb9,0xa8,0x01,0x00,0x34},{0x5f,0x24,0x03,0xd5,0xc8,0x09,0x02,0xd0,0x08,0x01,0x24,0x91},{0x3f,0x23,0x03,0xd5,0xfd,0x7b,0xbe,0xa9,0xf3,0x0b,0x00,0xf9}};
  for(int i=0;i<3;i++)if(memcmp((void *)(base+offsets[i]),originals[i],12)){note("instruction guard failed; unchanged");return;}
  if(!prepare_input()){note("input guard failed; unchanged");return;}
  if(forms_available&&!prepare_forms()){note("form guard failed; unchanged");return;}
  const uint32_t patch[]={0xd503245f,0x52800020,0xd65f03c0};
  for(int i=0;i<3;i++){void *target=(void *)(base+offsets[i]);writable(target,12,PROT_READ|PROT_WRITE|PROT_EXEC);memcpy(target,patch,12);__builtin___clear_cache(target,target+12);writable(target,12,PROT_READ|PROT_EXEC);}
  configure(0x11d4fe40);configure(0x11d50048);activate_input();note("exact-build runtime adapter initialized");
  if(forms_available){activate_forms();note("experimental native forms enabled");}
  if(forms_input_enabled)note("experimental native form focus/keyboard enabled");
  if(forms_progress_enabled)note("experimental native determinate progress enabled");
  if(forms_animation_enabled)note("experimental native event invalidation enabled");
  if(forms_sliders_enabled)note("experimental native sliders enabled");
  if(forms_popups_enabled)note("experimental native select popups enabled");
  if(forms_text_enabled)note("experimental native text fields enabled");
}
