/* Included by hook.c. Version-pinned input handoff; NSScroller owns tracking. */
#include "pinned-input.h"
#include <stdatomic.h>
#include <time.h>
struct Point {int x,y;};
struct FloatPoint {float x,y;};
static __thread void *current_controller;
static __thread int suppress_blink_action;
static int scroll_offset_slot=-1,minimum_offset_slot=-1;
static int disconnect_slot=-1;
static void *nxs_original_work __attribute__((used));
static void (*original_down)(void *,const void *);
static void (*original_move)(void *,const void *);
static void (*original_up)(void *,const void *);
static void (*original_move_thumb)(void *,int,int);
static void (*original_autoscroll)(void *,int64_t);
static void (*original_destroy)(void *);
static void *original_cc_down;
static struct {
  pthread_mutex_t mutex;
  void *bar,*controller;
  pthread_t owner,reader;
  int horizontal,running,reader_started,pending;
  float value;
  int tracking;
} native_input={.mutex=PTHREAD_MUTEX_INITIALIZER};

static int native_bar(const void *bar) {
  if(!bar)return 0;
  void *theme=*(void **)((const char *)bar+24);
  if(!theme)return 0;
  uintptr_t table=*(uintptr_t *)theme;
  return table==base+0x11d4fe40+16||table==base+0x11d50048+16;
}
static unsigned event_modifiers(const void *event) {
  unsigned m=*(const unsigned *)((const char *)event+52);
  return (m&1)|((m&2)?4:0)|((m&4)?2:0)|(m&8);
}
static struct Point local_point(void *bar,const void *event) {
  typedef struct FloatPoint (*Root)(const void *);
  typedef struct Point (*Local)(const void *,const struct Point *);
  struct FloatPoint position=((Root)(base+0xac35e38))(event);
  struct Point root={(int)floorf(position.x),(int)floorf(position.y)};
  return ((Local)(base+0xe8ffa68))(bar,&root);
}
static struct NXSResponse *input_request(uintptr_t bar,int horizontal,int operation,struct Point point,unsigned modifiers) {
  struct NXSScrollerBinding binding={.control=bar,.horizontal=horizontal};
  return native_scroller_input(&binding,operation,point.x,point.y,modifiers);
}
static void apply_value(void *bar,float value) {
  if(!bar||scroll_offset_slot<0||minimum_offset_slot<0)return;
  int32_t compressed=*(const int32_t *)((const char *)bar+12);
  if(!compressed)return;
  uintptr_t mask=*(const uintptr_t *)(base+0x12562900);
  void *area=(void *)(mask&((uint64_t)(int64_t)compressed<<3));
  typedef struct FloatPoint (*Get)(const void *);
  struct FloatPoint offset=((Get)(*(uintptr_t **)area)[scroll_offset_slot])(area);
  struct FloatPoint minimum=((Get)(*(uintptr_t **)area)[minimum_offset_slot])(area);
  float old=*(const int *)((const char *)bar+16)?offset.y:offset.x;
  float target=value+(*(const int *)((const char *)bar+16)?minimum.y:minimum.x);
  if(fabsf(target-old)>.001f) {
    if(*(const int *)((const char *)bar+16))offset.y=target;else offset.x=target;
    /* Use Chromium's absolute range setter: user scroll, absolute source,
     * instant behavior. No second gesture animation or Blink repeat loop. */
    typedef int (*Set)(void *,const struct FloatPoint *,int,int,int,int);
    ((Set)(base+0xe8f5de4))(area,&offset,0,1,1,0);
    if(log_fd>=0) {
      struct FloatPoint after=((Get)(*(uintptr_t **)area)[scroll_offset_slot])(area);
      dprintf(log_fd,"%d transfer native=%.3f old=%.3f minimum=%.3f,%.3f target=%.3f after=%.3f,%.3f\n",getpid(),value,old,minimum.x,minimum.y,target,after.x,after.y);
    }
  }
  ((void (*)(void *,int))(base+0xe8fe800))(bar,-1);
}

static void *poll_native(void *unused) {
  float previous=-1;int previous_tracking=-1;
  for(;;) {
    pthread_mutex_lock(&native_input.mutex);
    int running=native_input.running,horizontal=native_input.horizontal;
    uintptr_t bar=(uintptr_t)native_input.bar;void *controller=native_input.controller;
    pthread_mutex_unlock(&native_input.mutex);
    if(!running||!bar)break;
    struct NXSResponse *r=input_request(bar,horizontal,5,(struct Point){0},0);
    if(r) {
      float value=r->parts[0].x;int tracking=r->parts[0].y;
      if(fabsf(value-previous)>.001f||tracking!=previous_tracking) {
        previous=value;previous_tracking=tracking;
        pthread_mutex_lock(&native_input.mutex);
        if(native_input.running&&native_input.bar==(void *)bar) {native_input.value=value;native_input.tracking=tracking;native_input.pending=1;}
        pthread_mutex_unlock(&native_input.mutex);
        ((void (*)(void *))(base+0xa2e11e0))(controller);
      }
    }
    struct timespec delay={.tv_nsec=8000000};nanosleep(&delay,NULL);
  }
  return NULL;
}
__attribute__((used,noinline)) static void nxs_prepare_work(void *controller) {
  current_controller=controller;
  pthread_mutex_lock(&native_input.mutex);
  int ready=native_input.pending&&native_input.bar&&pthread_equal(native_input.owner,pthread_self());
  void *bar=native_input.bar;float value=native_input.value;
  if(ready)native_input.pending=0;
  pthread_mutex_unlock(&native_input.mutex);
  if(ready)apply_value(bar,value);
  form_native_work(controller);
}
__attribute__((naked)) static void work_handoff(void) {
  __asm__ volatile("bti c\n"
    "stp x29,x30,[sp,#-32]!\n"
    "stp x0,x8,[sp,#16]\n"
    "bl nxs_prepare_work\n"
    "ldp x0,x8,[sp,#16]\n"
    "ldp x29,x30,[sp],#32\n"
    "adrp x16,nxs_original_work\n"
    "ldr x16,[x16,:lo12:nxs_original_work]\n"
    "br x16\n");
}
static void stop_native(void *bar,struct Point point,unsigned modifiers,int apply) {
  pthread_mutex_lock(&native_input.mutex);
  int matches=native_input.bar==bar;
  int horizontal=native_input.horizontal,join=native_input.reader_started;
  pthread_t reader=native_input.reader;
  if(matches) {native_input.running=0;native_input.pending=0;native_input.reader_started=0;native_input.bar=NULL;}
  pthread_mutex_unlock(&native_input.mutex);
  if(!matches)return;
  if(join)pthread_join(reader,NULL);
  struct NXSResponse *r=input_request((uintptr_t)bar,horizontal,4,point,modifiers);
  for(int i=0;r&&r->parts[0].y&&i<30;i++) {
    struct timespec pause={.tv_nsec=2000000};nanosleep(&pause,NULL);
    r=input_request((uintptr_t)bar,horizontal,5,point,modifiers);
  }
  if(apply&&r)apply_value(bar,r->parts[0].x);
}
static void mouse_down(void *bar,const void *event) {
  int use=native_bar(bar)&&current_controller&&*(const int *)((const char *)event+120)==0;
  suppress_blink_action=use;original_down(bar,event);suppress_blink_action=0;
  if(!use||*(const unsigned char *)((const char *)bar+203)||!*(const int *)((const char *)bar+52))return;
  struct Point point=local_point(bar,event);
  int horizontal=*(const int *)((const char *)bar+16)==0;
  if(!input_request((uintptr_t)bar,horizontal,2,point,event_modifiers(event)))return;
  pthread_mutex_lock(&native_input.mutex);
  native_input.bar=bar;native_input.controller=current_controller;native_input.owner=pthread_self();native_input.horizontal=horizontal;native_input.running=1;native_input.pending=0;
  pthread_mutex_unlock(&native_input.mutex);
  if(!pthread_create(&native_input.reader,NULL,poll_native,NULL))native_input.reader_started=1;
  ((void (*)(void *,int))(base+0xe8fe800))(bar,-1);
  note("native mouse tracking started");
}
static void mouse_move(void *bar,const void *event) {
  pthread_mutex_lock(&native_input.mutex);int active=native_input.bar==bar;int horizontal=native_input.horizontal;pthread_mutex_unlock(&native_input.mutex);
  if(active) {input_request((uintptr_t)bar,horizontal,3,local_point(bar,event),event_modifiers(event));return;}
  original_move(bar,event);
}
static void mouse_up(void *bar,const void *event) {
  stop_native(bar,local_point(bar,event),event_modifiers(event),1);
  original_up(bar,event);
  ((void (*)(void *,int))(base+0xe8fe800))(bar,-1);
}
static void move_thumb(void *bar,int position,int document) {
  if(!suppress_blink_action)original_move_thumb(bar,position,document);
}
static void autoscroll(void *bar,int64_t delay) {
  pthread_mutex_lock(&native_input.mutex);int active=native_input.bar==bar;pthread_mutex_unlock(&native_input.mutex);
  if(!suppress_blink_action&&!active)original_autoscroll(bar,delay);
}
static void destroy_scrollbar(void *bar) {
  stop_native(bar,(struct Point){0},0,0);
  chromium_scroller_retire(bar);
  original_destroy(bar);
}
static void disconnect_scrollbar(void *bar) {
  stop_native(bar,(struct Point){0},0,0);
  chromium_scroller_retire(bar);
  ((void (*)(void *))(base+0xb249734))(bar);
}

#include "../../Libraries/NativeUI/Bridge/AArch64Detours.inc"
struct PointerResult {int type,units;float dx,dy;uint64_t target;};
_Static_assert(sizeof(struct PointerResult)==24,"Pinned compositor pointer result");
static struct PointerResult main_thread_pointer(void *controller,struct FloatPoint position,int jump) {
  /* Chromium's own unhandled result routes this event to Blink's main thread.
   * Prevent cc from starting a second scrollbar animation before NSScroller
   * receives the same press. Wheel and content scrolling keep their handlers. */
  return (struct PointerResult){0};
}
static struct Detour input_detours[]={
 {NXS_CC_DOWN_OFFSET,nxs_cc_down_bytes,main_thread_pointer,&original_cc_down},
 {NXS_DOWN_OFFSET,nxs_down_bytes,mouse_down,(void **)&original_down},
 {NXS_MOVE_OFFSET,nxs_move_bytes,mouse_move,(void **)&original_move},
 {NXS_UP_OFFSET,nxs_up_bytes,mouse_up,(void **)&original_up},
 {NXS_MOVE_THUMB_OFFSET,nxs_move_thumb_bytes,move_thumb,(void **)&original_move_thumb},
 {NXS_AUTOSCROLL_OFFSET,nxs_autoscroll_bytes,autoscroll,(void **)&original_autoscroll},
 {NXS_WORK_OFFSET,nxs_work_bytes,work_handoff,&nxs_original_work},
 {NXS_DESTROY_OFFSET,nxs_destroy_bytes,destroy_scrollbar,(void **)&original_destroy}
};
static int prepare_input(void) {
  if(memcmp((void *)(base+NXS_BLINK_SCROLLBAR_SCALE_OFFSET),nxs_blink_scrollbar_scale_bytes,20))return 0;
  uintptr_t *table=(uintptr_t *)(base+0x11d4b228);
  for(int i=2;i<120;i++)if(table[i]==base+0xc7a3550){if(scroll_offset_slot>=0)return 0;scroll_offset_slot=i-2;}
  for(int i=2;i<120;i++)if(table[i]==base+0xdfe7078){if(minimum_offset_slot>=0)return 0;minimum_offset_slot=i-2;}
  if(scroll_offset_slot<0||minimum_offset_slot<0)return 0;
  uintptr_t *scrollbar_table=(uintptr_t *)(base+0x11d4f840);
  for(int i=2;i<24;i++)if(scrollbar_table[i]==base+0xb249734){if(disconnect_slot>=0)return 0;disconnect_slot=i;}
  if(disconnect_slot<0)return 0;
  return prepare_detours(input_detours,sizeof(input_detours)/sizeof(*input_detours));
}
static void activate_input(void) {
  uintptr_t *scrollbar_table=(uintptr_t *)(base+0x11d4f840);
  writable(scrollbar_table,24*8,PROT_READ|PROT_WRITE);
  scrollbar_table[disconnect_slot]=(uintptr_t)disconnect_scrollbar;
  writable(scrollbar_table,24*8,PROT_READ);
  activate_detours(input_detours,sizeof(input_detours)/sizeof(*input_detours));
}
