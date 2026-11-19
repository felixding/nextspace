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
#include "../../Libraries/NativeUI/Bridge/BrowserPolicy.h"
static uintptr_t base;
static int log_fd=-1,installed;
static void note(const char *message) {if(log_fd>=0)dprintf(log_fd,"%d %s\n",getpid(),message);}
#include "../../Libraries/NativeUI/Bridge/Transport.inc"
#include "../../Libraries/NativeUI/Bridge/Invalidations.inc"
#include "../../Libraries/NativeUI/Bridge/BitmapBinding.inc"
#include "../../Libraries/NativeUI/Bridge/ScrollerBinding.inc"
#include "../../Libraries/NativeUI/Bridge/AuxiliaryActivation.inc"
#include "../../Libraries/NativeUI/Bridge/Popups.inc"
#include "../../Libraries/NativeUI/Bridge/PopupBinding.inc"
#include "../../Libraries/NativeUI/Bridge/Radios.inc"
#include "../../Libraries/NativeUI/Bridge/Lists.inc"
#include "../../Libraries/NativeUI/Bridge/ListBinding.inc"
#include "../../Libraries/NativeUI/Bridge/ItemHits.inc"
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
static int eligible(void *,unsigned);

#include "images.inc"
#include "window.inc"
/* Browser chrome stays with Gecko. Process role is evaluated at use time,
 * after child startup, using the same guarded engine getter as menu dispatch. */
static int native_web_process(void) {
  return base&&(NXS_BROWSER_UI_PATCH||!((int (*)(void))(base+0x7546c5c))());
}
static int tabs_requested,tabs_trace_enabled;
static int gecko_frame_screen_origin(void *,double *,double *);
static int gecko_frame_screen_bounds(void *,struct NXSRectD *);
static int gecko_frame_device_origin(void *,double *,double *);
static int gecko_frame_device_origin(void *,double *,double *);
static int gecko_frame_pixel_rect(void *,struct NXSRectD *);
static void progress_retire_unstyled(void);
static int popups_requested,lists_requested;
/* Engine-frame metadata shared by native text and list scroll consumers. */
struct FrameViewport {
  void *frame,*node;
  uint64_t id;
  uint32_t epoch;
  int kind;
  NXSScrollGeometry geometry;
  NXSTextViewport native;
};
static int list_viewport(const void *,struct FrameViewport *,int);
static int list_viewport_scroll(const struct FrameViewport *,double,double);
static int list_viewport_wheel(const struct FrameViewport *,const NXSWheelEvent *);
static int native_list_frame(const void *);
static int native_list_owned(const void *);
static int prepare_list_image(void *);
static int draw_list_image(void *,void *,const struct RectF *);
static void native_list_forget(void *);
static void native_list_release_context(void *);
static int native_lists_exist(void);
static int native_list_post(void *,void *);
static void native_list_pointer_post(void *);
static void native_list_model_changed(void *);
static int native_list_display(void *,void *,const void *);
static int native_popup_frame(const void *);
static int native_popup_owned(const void *);
static int prepare_popup_image(void *);
static int native_popup_display(void *,void *,const void *);
static int draw_popup_image(void *,void *,const struct RectF *);
static void native_popup_forget(void *);
static void native_popup_release_context(void *);
static void native_popup_notification(const struct NXSInvalidations *);
static int native_popups_exist(void);
static void native_popup_pointer_post(const void *);
static int tabs_frame_owned(const void *);
static int tabs_draw(void *,void *,const struct RectF *);
static void tabs_forget(void *);
static void tabs_native_notification(void);
static uint64_t tabs_pointer_target(void *,void *);
static void tabs_pointer_post(uint64_t,void *,int);
static int document_scroller_owned(void *,unsigned);
static int document_scroller_draw(void *,void *,unsigned,const struct RectF *);
static void document_scroller_forget(void *);
static void document_scroller_release_context(void *);
static void document_scroller_notification(void);
static int document_scrollers_exist(void);
static int document_scroller_pointer_post(void *,void *,int *);
static int document_scroller_pointer_pre(void *,void *,int *);
#include "controls.inc"
#include "tabs.inc"
#include "popups.inc"
#include "focus-order.inc"
#define NXS_GECKO_PLACEHOLDER_NEWLINES 0x466d198ul
static const unsigned char gecko_placeholder_newlines_bytes[20]={0x5f,0x24,0x03,0xd5,0x55,0xde,0xd0,0x17,0x3f,0x23,0x03,0xd5,0xfe,0x4f,0xbf,0xa9,0xa1,0x01,0x80,0x52};
static char *text_placeholder(void *node) {
  static void *atom;static const uint16_t empty;
  if(!atom)atom=((void *(*)(const char *))(base+NXS_GECKO_POPUP_ATOMIZE))("placeholder");
  if(!atom)return NULL;
  struct GeckoString value={.data=&empty,.flags=1};
  ((int (*)(const void *,const void *,void *))(base+NXS_GECKO_POPUP_GET_ATTR))(node,atom,&value);
  ((void (*)(void *))(base+NXS_GECKO_PLACEHOLDER_NEWLINES))(&value);
  char *result=utf8_text(value.data,value.length);
  ((void (*)(void *))(base+0x3826f2c))(&value);return result;
}
#include "lists.inc"
#include "geometry.inc"
#include "scrollbars.inc"
#include "menus.inc"
#include "context-menu-model.inc"
#include "key-registry.inc"
#include "../../Libraries/NativeUI/Bridge/Menu.inc"
static int gtk_context_owns_keys(void);
#include "global-keys.inc"
static int gecko_context_prepare(int (*handler)(const struct NXSNativeMenuCommand *))
{return menu_lifecycle_requested&&ensure_widget_lifetime()&&native_menu_filter_register(handler);}
#define NXS_GTK_CONTEXT_PREPARE(handler) gecko_context_prepare(handler)
#include "../../Libraries/NativeUI/Bridge/GtkContextMenus.inc"
#undef NXS_GTK_CONTEXT_PREPARE


/* Frame/content and model access are audited against this libxul, including
 * Gecko's own FromNode tag/namespace check. NativeUI has no DOM knowledge. */
static double progress_position(void *frame) {
  if(!native_web_process())return -2;
  void *content=*(void **)((char *)frame+24);
  if(!content)return -2;
  void *info=*(void **)((char *)content+40);
  if(!info||*(uintptr_t *)((char *)info+16)!=base+0x1167eec||
     *(uint32_t *)((char *)info+32)!=3)return -2;
  return ((double (*)(const void *))(base+0x589f280))(content);
}
static void progress_retire_unstyled(void)
{
  struct Widget **cursor=&widgets;
  while(*cursor) {
    struct Widget *w=*cursor;
    if(w->kind==NXS_PROGRESS) {
      const void *style=*(void **)((char *)w->frame+32);
      const void *display=style?*(void **)((char *)style+80):NULL;
      if(!display||!original_frontend_themed(w->frame,display,NULL)||!frame_scale_supported(w->frame)) {
        forget_widget(cursor);continue;
      }
    }
    cursor=&w->next;
  }
}
static int eligible(void *frame,unsigned appearance) {
  if(channel<0)return 0;
  if(native_popup_owned(frame))return 1;
  if(texts_enabled&&native_text_frame(frame)&&widget_for_frame(frame)&&widget_for_frame(frame)->text_owned)return 1;
  if(widgets_enabled&&(appearance==4||appearance==5||(buttons_enabled&&appearance==10)||(sliders_enabled&&appearance==19))&&frame_kind(frame))return 1;
  if(appearance!=9)return 0;
  double position=progress_position(frame);
  return isfinite(position)&&position>=-1&&position<=1;
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
  if(!frame_scale_supported(frame)||!isfinite(value)||value<-1||value>1||!rect||
     !isfinite(rect->x)||!isfinite(rect->y)||!isfinite(rect->width)||!isfinite(rect->height)||
     rect->width<1||rect->height<1||rect->width>8192||rect->height>8192)goto fallback;
  struct Widget *w=widgets_enabled?widget_for_frame(frame):NULL;
  if(value<0&&!widgets_enabled)goto fallback;
  if(widgets_enabled&&!w) {
    if(!ensure_widget_lifetime()||!ensure_text_watch())goto fallback;
    w=calloc(1,sizeof(*w));if(!w)goto fallback;
    w->frame=frame;w->node=*(void **)((char *)frame+24);w->id=++next_widget;w->kind=NXS_PROGRESS;
    w->next=widgets;widgets=w;
  }
  if(w&&w->kind!=NXS_PROGRESS)goto fallback;
  if(w){w->width=rect->width;w->height=rect->height;}
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=1,
    .process=identity(),.kind=NXS_PROGRESS,.control=w?w->id:(uintptr_t)frame,
    .width=rect->width,.height=rect->height,.maximum=1,.value=value<0?0:value,.enabled=1,.indeterminate=value<0};
  if(!native_control_presentation(NXS_PROGRESS,request.control,frame_scale(frame)))goto fallback;
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
  uint32_t *pixels=NULL;int width=0,height=0;
  if(response&&response->width>0&&response->height>0&&response->width<=8192&&response->height<=8192&&
     response->stride==response->width*4&&
     sizeof(*response)+(size_t)response->stride*response->height==response->size) {
    width=response->width;height=response->height;
    pixels=malloc((size_t)response->stride*height);
    if(pixels)memcpy(pixels,response+1,(size_t)response->stride*height);
  }
  /* The existing frame/shell lifetime owns this object. Its original native
   * timer emits invalidations through the shared notifier; Gecko only repaints.
   * No animation phase, duration or interval is implemented in the adapter. */
  if(!widgets_enabled){request.operation=6;exchange_bytes(&request,sizeof(request));}
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
static void prepare_native_features(void) {
  const char *input=getenv("NEXTSPACE_FIREFOX_INPUT");
  if(input&&!strcmp(input,"1"))prepare_widget_metrics();
  const char *tabs=getenv("NEXTSPACE_FIREFOX_TABS"),*tab_trace=getenv("NEXTSPACE_FIREFOX_TABS_TRACE");
  tabs_requested=NXS_BROWSER_UI_PATCH&&frontend_requested&&tabs&&!strcmp(tabs,"1");
  tabs_trace_enabled=tabs_requested&&tab_trace&&!strcmp(tab_trace,"1");
  const char *menu_keys=getenv("NEXTSPACE_FIREFOX_MENU_KEYS");
  menu_keys_requested=menu_keys&&!strcmp(menu_keys,"1")&&application_menu_keys;
  if(menu_keys&&!strcmp(menu_keys,"1")&&!menu_keys_requested)note("native global menu keys unavailable in this helper/configuration");
 }
static void install(void) {
  if(installed||channel<0)return;
  dl_iterate_phdr(find_xul,NULL);if(!base)return;
  /* A cold startup capability reply can be lost before libxul loads. Retry
   * at this existing bootstrap boundary before committing the feature mask;
   * otherwise the parent keeps GTK pickers while content uses NativeUI. */
  if(!widgets_enabled)prepare_native_features();
  uintptr_t *table=(uintptr_t *)(base+0x9e22190+16);
  if(!guard_native_image_calls()||table[27]!=base+0x3fc3108||*(uintptr_t *)(base+0x9e21210+32)!=base+0x316fee8||
     memcmp((void *)(base+0x6a7782c),(unsigned char[]){0x00,0x0f,0x40,0xf9},4)||
     memcmp((void *)(base+0x589f280),(unsigned char[]){0x5f,0x24,0x03,0xd5,0x00,0x10,0x7e,0x1e},8)||
     !prepare_detours(detours,sizeof(detours)/sizeof(*detours))) {note("Gecko layout/instruction guard failed; unchanged");return;}
  if(multiline_enabled&&!guard_multiline_calls()){note("Gecko multiline guard failed; unchanged");return;}
  if((multiline_viewport_enabled||lists_requested)&&(!guard_viewport_calls()||!prepare_detours(viewport_detours,sizeof(viewport_detours)/sizeof(*viewport_detours)))){note("Gecko viewport guard failed; unchanged");return;}
  if(wheel_enabled&&(!guard_wheel_calls()||!prepare_detours(wheel_detours,sizeof(wheel_detours)/sizeof(*wheel_detours)))){note("Gecko wheel guard failed; unchanged");return;}
  if(widgets_enabled&&!prepare_detours(widget_detours,sizeof(widget_detours)/sizeof(*widget_detours))){note("Gecko interactive guard failed; unchanged");return;}
  if(widgets_enabled&&(!guard_checkbox_calls()||!prepare_detours(checkbox_activation_detours,sizeof(checkbox_activation_detours)/sizeof(*checkbox_activation_detours)))){note("Gecko checkbox activation guard failed; unchanged");return;}
  if(radio_groups_enabled&&(!guard_radio_calls()||!prepare_detours(radio_pointer_detours,sizeof(radio_pointer_detours)/sizeof(*radio_pointer_detours)))){note("Gecko radio group guard failed; unchanged");return;}
  if(labels_enabled&&!prepare_detours(form_label_detours,sizeof(form_label_detours)/sizeof(*form_label_detours))){note("Gecko label guard failed; unchanged");return;}
  if((buttons_enabled||popups_requested)&&(!guard_html_button_calls()||!prepare_detours(button_detours,sizeof(button_detours)/sizeof(*button_detours)))){note("Gecko button guard failed; unchanged");return;}
  if(sliders_enabled&&!prepare_detours(range_detours,sizeof(range_detours)/sizeof(*range_detours))){note("Gecko range guard failed; unchanged");return;}
  if(colors_enabled&&(!guard_color_calls()||!prepare_detours(color_detours,sizeof(color_detours)/sizeof(*color_detours)))){note("Gecko color guard failed; unchanged");return;}
  if(texts_enabled&&(!guard_text_calls()||!guard_password_visibility()||!prepare_detours(text_detours,sizeof(text_detours)/sizeof(*text_detours)))){note("Gecko text guard failed; unchanged");return;}
  if(texts_enabled&&!guard_text_commands()){note("Gecko text command guard failed; unchanged");return;}
  if(numbers_enabled&&!guard_number_calls()){note("Gecko number guard failed; unchanged");return;}
  if(dates_enabled&&(!guard_date_calls()||!prepare_detours(date_detours,sizeof(date_detours)/sizeof(*date_detours)))){note("Gecko date guard failed; unchanged");return;}
  if(placeholder_enabled&&(memcmp((void *)(base+NXS_GECKO_POPUP_GET_ATTR),gecko_popup_get_attr_bytes,20)||
     memcmp((void *)(base+NXS_GECKO_POPUP_ATOMIZE),gecko_popup_atomize_bytes,20)||
     memcmp((void *)(base+NXS_GECKO_PLACEHOLDER_NEWLINES),gecko_placeholder_newlines_bytes,20))){note("Gecko placeholder model guard failed; unchanged");return;}
  if(!prepare_background_bindings()){note("Gecko native background guard failed; unchanged");return;}
  if(!prepare_document_scrollers()){note("Gecko native document scroller guard failed; unchanged");return;}
  if(widgets_enabled&&!prepare_frontend_bindings()){note("Gecko owned-background guard failed; unchanged");return;}
  if(popups_requested&&(!guard_popup_calls()||!prepare_detours(popup_detours,sizeof(popup_detours)/sizeof(*popup_detours)))){note("Gecko select guard failed; unchanged");return;}
  if(lists_requested&&(!guard_list_calls()||!guard_list_geometry_calls()||!guard_list_hit_calls()||
     !prepare_detours(list_hit_detours,sizeof(list_hit_detours)/sizeof(*list_hit_detours))||
     (!texts_enabled&&!prepare_detours(list_detours,sizeof(list_detours)/sizeof(*list_detours))))){note("Gecko list guard failed; unchanged");return;}
  if(!prepare_geometry()){note("Gecko geometry guard failed; unchanged");return;}
  if(tabs_requested&&!prepare_tabs()){note("Gecko tab guard failed; unchanged");return;}
  if(!prepare_context_menu_model()){note("Gecko context menu model guard failed; unchanged");return;}
  if(!prepare_menu_lifecycle()){note("Gecko external menu lifecycle guard failed; unchanged");return;}
  if(widgets_enabled&&!prepare_focus_input_order()){note("Gecko focus/input ordering guard failed; unchanged");return;}
  if(!prepare_global_keys()){note("Gecko global menu key guard failed; unchanged");return;}
  if(gtk_surface_geometry){activate_detours(geometry_detours,1);activate_popup_geometry();note("experimental shared GTK surface geometry binding installed");note("original Gecko popup parent coordinate conversion enabled");}
  activate_detours(detours,sizeof(detours)/sizeof(*detours));
  activate_detours(background_detours,sizeof(background_detours)/sizeof(*background_detours));
  if(widgets_enabled){activate_detours(widget_detours,sizeof(widget_detours)/sizeof(*widget_detours));note("native Gecko checkbox/radio bindings installed");}
  if(widgets_enabled)activate_detours(checkbox_activation_detours,sizeof(checkbox_activation_detours)/sizeof(*checkbox_activation_detours));
  if(radio_groups_enabled||document_scrollbars_enabled)activate_detours(radio_pointer_detours,sizeof(radio_pointer_detours)/sizeof(*radio_pointer_detours));
  if(labels_enabled)activate_detours(form_label_detours,sizeof(form_label_detours)/sizeof(*form_label_detours));
  if(buttons_enabled||popups_requested){activate_detours(button_detours,sizeof(button_detours)/sizeof(*button_detours));note(buttons_enabled?"native Gecko input buttons installed":"native Gecko block display binding installed");}
  if(sliders_enabled){activate_detours(range_detours,sizeof(range_detours)/sizeof(*range_detours));note("native Gecko ranges installed");}
  if(colors_enabled){activate_detours(color_detours,sizeof(color_detours)/sizeof(*color_detours));note("native Gecko color binding installed");}
  if(dates_enabled){activate_detours(date_detours,sizeof(date_detours)/sizeof(*date_detours));note("native Gecko date binding installed");}
  if(texts_enabled){activate_detours(text_detours,sizeof(text_detours)/sizeof(*text_detours));note("native Gecko text bindings installed");}
  if(multiline_viewport_enabled||lists_requested){activate_detours(viewport_detours,sizeof(viewport_detours)/sizeof(*viewport_detours));note("native Gecko shared scroll viewport installed");}
  if(wheel_enabled){activate_detours(wheel_detours,sizeof(wheel_detours)/sizeof(*wheel_detours));note("native Gecko wheel binding installed");}
  if(widgets_enabled){activate_detours(frontend_detours,sizeof(frontend_detours)/sizeof(*frontend_detours));note(frontend_requested?"native Gecko frontend text binding installed":"native Gecko webpage background binding installed");}
  if(popups_requested){activate_detours(popup_detours,sizeof(popup_detours)/sizeof(*popup_detours));note("experimental native Gecko select binding installed");}
  if(lists_requested){if(!texts_enabled)activate_detours(list_detours,sizeof(list_detours)/sizeof(*list_detours));
    activate_detours(list_hit_detours,sizeof(list_hit_detours)/sizeof(*list_hit_detours));note("experimental native Gecko list binding installed");}
  if(tabs_requested){activate_detours(tabs_detours,sizeof(tabs_detours)/sizeof(*tabs_detours));note("experimental native Gecko tab container installed");}
  if(menu_lifecycle_requested){activate_detours(menu_lifecycle_detours,sizeof(menu_lifecycle_detours)/sizeof(*menu_lifecycle_detours));activate_detours(context_model_detours,sizeof(context_model_detours)/sizeof(*context_model_detours));note("native Gecko external menu lifecycle binding installed");}
  if(menu_keys_requested){
    activate_detours(registry_detours,sizeof(registry_detours)/sizeof(*registry_detours));
    activate_detours(global_key_detours,sizeof(global_key_detours)/sizeof(*global_key_detours));
    note("native Gecko original key registry and global menu binding installed");
  }
  if(widgets_enabled){activate_detours(focus_order_detours,2);note("native Gecko focus/input ordering installed");}
  installed=1;
  if(document_scrollbars_enabled)activate_detours(document_scroller_detours,sizeof(document_scroller_detours)/sizeof(*document_scroller_detours));
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
  const char *menus=getenv("NEXTSPACE_FIREFOX_MENU_LIFECYCLE");
  menu_lifecycle_requested=menus&&!strcmp(menus,"1");
  prepare_native_features();
  if(!NXS_BROWSER_UI_PATCH)note("browser-owned tabs and toolbar buttons preserved");
  note("Firefox native transport connected before sandbox");install();
}
