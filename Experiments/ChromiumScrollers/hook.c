/* Exact-build ARM64 experiment. Never rebuild or overwrite Chromium.
 * Rendering, geometry and tracking are supplied by the separate NativeUI provider.
 * GPL-2.0-or-later. */
#define _GNU_SOURCE
#if !defined(__aarch64__) || !defined(__clang__)
#error "The pinned Chromium adapter requires Clang on AArch64 for its naked ABI wrapper"
#endif
#include "protocol.h"
#include "../../Libraries/NativeUI/Bridge/BrowserPolicy.h"
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
static int native_scroller_on_left;
static __thread struct NXSRequest cached_request;
static __thread struct NXSResponse cached_response;
static __thread uint32_t cached_scroller_epoch;
static __thread double cached_scroller_scale;
static void note(const char *text) {if(log_fd>=0)dprintf(log_fd,"%d %s\n",getpid(),text);}
#include "../../Libraries/NativeUI/Bridge/Transport.inc"
#include "../../Libraries/NativeUI/Bridge/Invalidations.inc"
#include "../../Libraries/NativeUI/Bridge/BitmapBinding.inc"
#include "../../Libraries/NativeUI/Bridge/ScrollerBinding.inc"
#include "pinned-scrollbar-scale.h"
#include "../../Libraries/NativeUI/Bridge/Popups.inc"
#include "../../Libraries/NativeUI/Bridge/PopupBinding.inc"
#include "../../Libraries/NativeUI/Bridge/AuxiliaryActivation.inc"
#include "../../Libraries/NativeUI/Bridge/Radios.inc"
#include "../../Libraries/NativeUI/Bridge/Lists.inc"
#include "../../Libraries/NativeUI/Bridge/ListBinding.inc"
#include "../../Libraries/NativeUI/Bridge/ItemHits.inc"
#include "../../Libraries/NativeUI/Bridge/Tabs.inc"
#include "../../Libraries/NativeUI/Bridge/Menu.inc"

struct ChromiumScrollerBinding {
  struct ChromiumScrollerBinding *next;
  struct NXSScrollerBinding native;
};
static struct ChromiumScrollerBinding *chromium_scrollers;
static struct NXSScrollerBinding *chromium_scroller_binding(const void *bar,int horizontal)
{
  int32_t compressed=*(const int32_t *)((const char *)bar+12);
  if(!compressed)return NULL;
  uintptr_t mask=*(const uintptr_t *)(base+0x12562900);
  void *area=(void *)(mask&((uint64_t)(int64_t)compressed<<3));
  double scale=((float (*)(const void *))(base+NXS_BLINK_SCROLLBAR_SCALE_OFFSET))(area);
  if(!isfinite(scale)||scale<.125||scale>8)return NULL;
  struct ChromiumScrollerBinding *item=chromium_scrollers;
  while(item&&item->native.control!=(uintptr_t)bar)item=item->next;
  if(!item) {
    item=calloc(1,sizeof(*item));if(!item)return NULL;
    item->native.control=(uintptr_t)bar;item->native.horizontal=horizontal;
    item->next=chromium_scrollers;chromium_scrollers=item;
  }
  return native_scroller_prepare(&item->native,scale)?&item->native:NULL;
}
static void chromium_scroller_retire(const void *bar)
{
  struct ChromiumScrollerBinding **cursor=&chromium_scrollers;
  while(*cursor) {
    struct ChromiumScrollerBinding *item=*cursor;
    if(item->native.control!=(uintptr_t)bar){cursor=&item->next;continue;}
    native_scroller_retire(&item->native);*cursor=item->next;free(item);break;
  }
  memset(&cached_request,0,sizeof(cached_request));memset(&cached_response,0,sizeof(cached_response));
}

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
  struct NXSScrollerBinding *binding=chromium_scroller_binding(bar,orientation==0);
  if(!binding)return NULL;
  if(!layer&&cached_response.magic&&cached_scroller_epoch==binding->epoch&&
     cached_scroller_scale==binding->scale&&memcmp(&req,&cached_request,sizeof(req))==0)return &cached_response;
  struct NXSResponse *response=native_scroller_model(binding,req.length,req.total,req.page,req.value,layer!=0);
  if(!response)return NULL;
  if(!layer) {req.reserved=0;cached_request=req;cached_response=*response;
    cached_scroller_epoch=binding->epoch;cached_scroller_scale=binding->scale;return &cached_response;}
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
static int scroller_on_left(void*t){return native_scroller_on_left;}
static int has_thumb(void*t,const void*b){return *(const int *)((const char *)b+36)>*(const int *)((const char *)b+32);}

static int draw_native_bitmap_scaled(void *canvas,const uint32_t *pixels,int width,float origin_x,float origin_y,int first_x,int first_y,int last_x,int last_y,double scale) {
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
        float area[4]={origin_x+x/scale,origin_y+y/scale,origin_x+end/scale,origin_y+(y+1)/scale};draw(canvas,area,&flags);rectangles++;
      }
      x=end;
    }
  }
  return rectangles;
}
static int draw_native_bitmap(void *canvas,const uint32_t *pixels,int width,float origin_x,float origin_y,int first_x,int first_y,int last_x,int last_y) {
  return draw_native_bitmap_scaled(canvas,pixels,width,origin_x,origin_y,first_x,first_y,last_x,last_y,1);
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
  set_slot(table,39,paint_thumb);set_slot(table,46,no);set_slot(table,47,scroller_on_left);set_slot(table,49,no);set_slot(table,61,paint_track);
  writable((char *)table-1,65*8+1,PROT_READ);note("native theme vtable installed");
}
static void form_native_work(void *controller);
static void dismiss_popup_before_scroll(void);
static int views_enabled,views_trace_enabled;
static int tabs_enabled,tabs_trace_enabled;
static int tabs_watch_needed(void);
static void tabs_native_work(int);
static void tabs_forget(void *);
static int menus_enabled,menus_trace_enabled;
static int menu_keys_enabled;
static int app_menu_views_key(void *,const void *);
static int context_menu_owns_keys(void);
static int app_menus_watch_needed(void);
static void app_menus_native_work(int);
static unsigned forms_pointer_capabilities;
static int forms_commands_enabled;
static int chromium_application_command(const struct NXSNativeCommand *,const char *);
static int views_watch_needed(void);
static void views_native_work(int failed);
#include "input.inc"
#include "wayland-geometry.inc"
#include "forms.inc"
#include "views-text.inc"
#include "views-tabs.inc"
#include "app-menus.inc"
#include "global-menu-keys.inc"
#include "edit-bindings.inc"
static int chromium_application_command(const struct NXSNativeCommand *command,const char *selector) {
  if(views_transaction)return views_application_command(command,selector);
  return blink_application_command(command,selector);
}

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
  if(metrics->parts[5].x==1)forms_pointer_capabilities=NXS_POINTER_CLICK_COUNT;
  forms_commands_enabled=metrics->parts[5].y==1;
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
  const char *radio_groups=getenv("NEXTSPACE_CHROMIUM_RADIO_GROUPS");
  forms_radio_groups_enabled=forms_input_enabled&&radio_groups&&!strcmp(radio_groups,"1")&&((unsigned)metrics->parts[4].y&3)==3&&(forms_pointer_capabilities&NXS_POINTER_CLICK_COUNT);
  forms_labels_enabled=forms_input_enabled&&((unsigned)metrics->parts[4].y&4);
  forms_notifications_enabled=metrics->parts[6].x==1;
  const char *progress=getenv("NEXTSPACE_CHROMIUM_PROGRESS");
  forms_progress_enabled=forms_available&&progress&&!strcmp(progress,"1");
  const char *animation=getenv("NEXTSPACE_CHROMIUM_ANIMATION");
  forms_animation_enabled=forms_progress_enabled&&animation&&!strcmp(animation,"1")&&metrics->parts[4].height==1;
  const char *sliders=getenv("NEXTSPACE_CHROMIUM_SLIDERS");
  forms_sliders_enabled=forms_input_enabled&&sliders&&!strcmp(sliders,"1")&&metrics->parts[4].height==1&&metrics->parts[5].width==1;
  const char *popups=getenv("NEXTSPACE_CHROMIUM_POPUPS");
  forms_popups_enabled=(forms_input_enabled||(!forms_available&&forms_notifications_enabled))&&popups&&!strcmp(popups,"1")&&
    metrics->parts[4].height==1&&metrics->parts[6].width==1&&metrics->parts[6].height==1;
  const char *color=getenv("NEXTSPACE_CHROMIUM_COLORS");
  forms_color_enabled=forms_input_enabled&&color&&!strcmp(color,"1")&&
    ((unsigned)metrics->parts[1].x&NXS_SPECIAL_COLOR)&&((unsigned)metrics->parts[1].y&1);
  const char *text=getenv("NEXTSPACE_CHROMIUM_TEXT");
  forms_text_enabled=forms_input_enabled&&text&&!strcmp(text,"1")&&metrics->parts[6].x==1&&((unsigned)metrics->parts[6].y&3)==3;
  const char *numbers=getenv("NEXTSPACE_CHROMIUM_NUMBERS");
  forms_numbers_enabled=forms_text_enabled&&forms_commands_enabled&&numbers&&!strcmp(numbers,"1")&&((unsigned)metrics->parts[1].x&NXS_SPECIAL_STEPPER);
  const char *dates=getenv("NEXTSPACE_CHROMIUM_DATES");
  forms_dates_enabled=forms_text_enabled&&dates&&!strcmp(dates,"1")&&((unsigned)metrics->parts[1].x&NXS_SPECIAL_DATE_NULLABLE);
  forms_times_enabled=forms_dates_enabled&&((unsigned)metrics->parts[1].x&NXS_SPECIAL_TIME_OF_DAY);
  forms_months_enabled=forms_dates_enabled&&((unsigned)metrics->parts[1].x&NXS_SPECIAL_MONTH_START);
  forms_weeks_enabled=forms_dates_enabled&&((unsigned)metrics->parts[1].x&NXS_SPECIAL_WEEK_START);
  forms_date_panel_enabled=forms_dates_enabled&&((unsigned)metrics->parts[1].x&NXS_SPECIAL_DATE_PANEL);
  wayland_auxiliary_capabilities=((unsigned)metrics->parts[1].y>>1)&1;
  forms_proleptic_enabled=forms_dates_enabled&&((unsigned)metrics->parts[1].x&NXS_SPECIAL_DATE_PROLEPTIC);
  forms_placeholder_enabled=forms_text_enabled&&((unsigned)metrics->parts[6].y&NXS_TEXT_PLACEHOLDER);
  forms_search_enabled=forms_text_enabled&&((unsigned)metrics->parts[6].y&NXS_TEXT_SEARCH);
  forms_search_actions_enabled=forms_search_enabled&&forms_commands_enabled&&((unsigned)metrics->parts[6].y&NXS_TEXT_SEARCH_ACTION);
  forms_search_clear_enabled=forms_search_actions_enabled&&((unsigned)metrics->parts[6].y&NXS_TEXT_SEARCH_CLEAR_COMMAND);
  const char *lists=getenv("NEXTSPACE_CHROMIUM_LISTS");
  forms_lists_enabled=forms_popups_enabled&&forms_text_enabled&&lists&&!strcmp(lists,"1")&&((unsigned)metrics->parts[3].x&1)&&((unsigned)metrics->parts[3].y&NXS_SCROLL_GEOMETRY)&&((unsigned)metrics->parts[2].x&1);
  const char *multiline=getenv("NEXTSPACE_CHROMIUM_MULTILINE");
  forms_multiline_enabled=forms_text_enabled&&multiline&&!strcmp(multiline,"1")&&((unsigned)metrics->parts[6].y&NXS_TEXT_MULTILINE)&&
    !memcmp((void *)(base+NXS_TEXTAREA_VALUE_OFFSET),nxs_textarea_value_bytes,20)&&
    !memcmp((void *)(base+NXS_TEXTAREA_PAINT_OFFSET),nxs_textarea_paint_bytes,8);
  const char *viewport=getenv("NEXTSPACE_CHROMIUM_MULTILINE_VIEWPORT");
  forms_multiline_viewport_enabled=forms_multiline_enabled&&viewport&&!strcmp(viewport,"1")&&
    (((unsigned)metrics->parts[6].y&(NXS_TEXT_VIEWPORT|NXS_TEXT_GEOMETRY))==(NXS_TEXT_VIEWPORT|NXS_TEXT_GEOMETRY));
  const char *wheel=getenv("NEXTSPACE_CHROMIUM_WHEEL");
  forms_wheel_enabled=(forms_multiline_viewport_enabled||forms_lists_enabled)&&wheel&&!strcmp(wheel,"1")&&((unsigned)metrics->parts[0].x&NXS_WHEEL_EVENTS);
  const char *views=getenv("NEXTSPACE_CHROMIUM_VIEWS"),*trace=getenv("NEXTSPACE_CHROMIUM_VIEWS_TRACE");
  views_enabled=NXS_BROWSER_TEXT_PATCH&&forms_text_enabled&&views&&!strcmp(views,"1")&&((unsigned)metrics->parts[6].y&NXS_TEXT_COMMAND);
  views_trace_enabled=views_enabled&&trace&&!strcmp(trace,"1");
  const char *tabs=getenv("NEXTSPACE_CHROMIUM_TABS"),*tabs_trace=getenv("NEXTSPACE_CHROMIUM_TABS_TRACE");
  tabs_enabled=NXS_BROWSER_UI_PATCH&&views_enabled&&tabs&&!strcmp(tabs,"1")&&((unsigned)metrics->parts[4].x&NXS_TAB_ITEMS);
  tabs_trace_enabled=tabs_enabled&&tabs_trace&&!strcmp(tabs_trace,"1");
  const char *menus=getenv("NEXTSPACE_CHROMIUM_MENUS"),*menu_trace=getenv("NEXTSPACE_CHROMIUM_MENUS_TRACE");
  menus_enabled=menus&&!strcmp(menus,"1")&&forms_notifications_enabled&&((unsigned)metrics->parts[5].height&1);
  menus_trace_enabled=menus_enabled&&menu_trace&&!strcmp(menu_trace,"1");
  const char *menu_keys=getenv("NEXTSPACE_CHROMIUM_MENU_KEYS");
  menu_keys_enabled=menus_enabled&&menu_keys&&!strcmp(menu_keys,"1")&&((unsigned)metrics->parts[5].height&4);
  const char *edit_keys=getenv("NEXTSPACE_CHROMIUM_EDIT_KEYS");
  int edit_keys_enabled=menu_keys_enabled&&edit_keys&&!strcmp(edit_keys,"1")&&
    (metrics->width&NXS_BOOTSTRAP_EDIT_BINDINGS);
  struct NXSRectD native_clip;
  if(!native_scroller_layout(128,128,&native_clip)){note("native scroller layout unavailable; unchanged");return;}
  native_scroller_on_left=native_clip.x>128-native_clip.x-native_clip.width;
  uintptr_t *aura=(uintptr_t *)(base+0x11d4fe40),*fluent=(uintptr_t *)(base+0x11d50048);
  if(aura[39]!=base+0xe906d0c||aura[61]!=base+0xe906124||fluent[39]!=base+0xe906d0c||fluent[61]!=base+0xe906124){note("theme guard failed; unchanged");return;}
  const uintptr_t offsets[]={0xe80ebec,0xe428628,0xe590960};
  const unsigned char originals[][12]={{0x5f,0x24,0x03,0xd5,0x08,0x38,0x80,0xb9,0xa8,0x01,0x00,0x34},{0x5f,0x24,0x03,0xd5,0xc8,0x09,0x02,0xd0,0x08,0x01,0x24,0x91},{0x3f,0x23,0x03,0xd5,0xfd,0x7b,0xbe,0xa9,0xf3,0x0b,0x00,0xf9}};
  for(int i=0;i<3;i++)if(memcmp((void *)(base+offsets[i]),originals[i],12)){note("instruction guard failed; unchanged");return;}
  if(!prepare_input()){note("input guard failed; unchanged");return;}
  if((forms_available||forms_popups_enabled)&&!prepare_detours(&form_lifetime_detour,1)){note("form lifetime guard failed; unchanged");return;}
  if(forms_popups_enabled&&!prepare_popup_lifecycle()){note("select popup lifecycle guard failed; unchanged");return;}
  if(forms_available&&!prepare_forms()){note("form guard failed; unchanged");return;}
  if(views_enabled&&(!guard_views_calls()||!prepare_detours(views_detours,sizeof(views_detours)/sizeof(*views_detours)))){note("Views guard failed; unchanged");return;}
  if((views_enabled||menu_keys_enabled)&&!prepare_detours(browser_accelerator_detour,1)){note("browser command boundary guard failed; unchanged");return;}
  if(tabs_enabled&&!prepare_tabs()){note("tab binding guard failed; unchanged");return;}
  if(menus_enabled&&(!guard_views_calls()||!prepare_app_menus())){note("application menu guard failed; unchanged");return;}
  if(menu_keys_enabled&&!prepare_global_menu_keys()){note("global menu key guard failed; unchanged");return;}
  if(edit_keys_enabled&&!prepare_detours(&linux_edit_key_detour,1)) {
    edit_keys_enabled=0;
    note("native edit key guard failed; original bindings retained");
  }
  browser_editor_keys=edit_keys_enabled&&prepare_blink_browser_editor();
  int wayland_geometry_enabled=prepare_wayland_geometry();
  const uint32_t patch[]={0xd503245f,0x52800000|((uint32_t)native_scroller_on_left<<5),0xd65f03c0};
  for(int i=0;i<3;i++){void *target=(void *)(base+offsets[i]);writable(target,12,PROT_READ|PROT_WRITE|PROT_EXEC);memcpy(target,patch,12);__builtin___clear_cache(target,target+12);writable(target,12,PROT_READ|PROT_EXEC);}
  configure(0x11d4fe40);configure(0x11d50048);activate_input();note("exact-build runtime adapter initialized");
  if(wayland_geometry_enabled){activate_detours(wayland_geometry_detours,sizeof(wayland_geometry_detours)/sizeof(*wayland_geometry_detours));note("shared native Wayland geometry enabled");activate_wayland_activation();}
  if(forms_available||forms_popups_enabled)activate_detours(&form_lifetime_detour,1);
  if(forms_popups_enabled)activate_detours(popup_lifecycle_detours,sizeof(popup_lifecycle_detours)/sizeof(*popup_lifecycle_detours));
  if(forms_available){activate_forms();note("experimental native forms enabled");}
  if(forms_input_enabled)note("experimental native form focus/keyboard enabled");
  if(forms_progress_enabled)note("experimental native determinate progress enabled");
  if(forms_animation_enabled)note("experimental native event invalidation enabled");
  if(forms_sliders_enabled)note("experimental native sliders enabled");
  if(forms_popups_enabled)note("experimental native select popups enabled");
  if(forms_text_enabled)note("experimental native text fields enabled");
  if(forms_multiline_viewport_enabled)note("experimental native multiline viewport enabled");
  if(forms_wheel_enabled)note("experimental native wheel dispatch enabled");
  if(!NXS_BROWSER_UI_PATCH)note("browser-owned tabs and toolbar buttons preserved");
  if(views_enabled){activate_detours(views_detours,sizeof(views_detours)/sizeof(*views_detours));note("experimental native address-bar fields enabled");}
  if(views_enabled||menu_keys_enabled)activate_detours(browser_accelerator_detour,1);
  if(tabs_enabled){activate_tabs();note("experimental native browser tabs enabled");}
  if(menus_enabled){activate_detours(app_menu_detours,sizeof(app_menu_detours)/sizeof(*app_menu_detours));activate_detours(context_menu_detours,sizeof(context_menu_detours)/sizeof(*context_menu_detours));note("experimental native application menu binding enabled");}
  if(menu_keys_enabled){activate_detours(browser_menu_detours,sizeof(browser_menu_detours)/sizeof(*browser_menu_detours));note("experimental native global menu keys enabled");}
  if(edit_keys_enabled){activate_detours(&linux_edit_key_detour,1);note("native LinuxUi edit bindings enabled");}
  if(browser_editor_keys) {
    activate_detours(blink_browser_editor_detours,forms_input_enabled?1:2);
    note("native Blink editor actions enabled");
  }
}
