/* Read-only application model binding. NSProgressIndicator owns its pixels. */
#include "pinned-progress.h"
static int (*original_progress)(void *,const void *,const void *,const void *,const struct Rect *,const void *);
static struct {
  pthread_mutex_t mutex;
  pthread_cond_t condition;
  pthread_t thread,owner;
  void *controller;
  int running,started,pending;
  double generation;
} form_watch={.mutex=PTHREAD_MUTEX_INITIALIZER,.condition=PTHREAD_COND_INITIALIZER};
static void *watch_native_forms(void *unused) {
  for(;;){
    pthread_mutex_lock(&form_watch.mutex);int running=form_watch.running;pthread_mutex_unlock(&form_watch.mutex);
    if(!running)break;
    struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=9,.process=identity()};
    struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
    double generation=response?response->parts[4].x:0,delay=response?response->parts[4].y:-1;
    pthread_mutex_lock(&form_watch.mutex);
    if(form_watch.running&&response&&generation>form_watch.generation){
      form_watch.generation=generation;form_watch.pending=1;
      /* ScheduleWork is thread-safe. Actual DOM/layout access stays on the
       * owning renderer thread when its existing work loop wakes. */
      ((void (*)(void *))(base+0xa2e11e0))(form_watch.controller);
    }
    if(form_watch.running){
      /* Bound transport recovery waits, not widget animation intervals. The
       * next animation deadline comes only from the native UI run loop. */
      delay=!isfinite(delay)||delay<0?1:fmin(1,fmax(.001,delay));
      struct timespec until;clock_gettime(CLOCK_REALTIME,&until);
      until.tv_sec+=(time_t)delay;until.tv_nsec+=(long)((delay-floor(delay))*1e9);
      if(until.tv_nsec>=1000000000){until.tv_nsec-=1000000000;until.tv_sec++;}
      pthread_cond_timedwait(&form_watch.condition,&form_watch.mutex,&until);
    }
    pthread_mutex_unlock(&form_watch.mutex);
  }
  return NULL;
}
static int refresh_form_watch(void) {
  if(!forms_animation_enabled&&!forms_sliders_enabled&&!forms_popups_enabled)return 1;
  int needed=active_form&&active_form->kind==NXS_SLIDER;double generation=needed?active_form->generation:0;
  for(struct NativeForm *f=native_forms;f;f=f->next)
    if((f->kind==NXS_PROGRESS&&f->indeterminate&&f->painted)||(f->kind==NXS_POPUP&&f->popup_open)){needed=1;generation=fmax(generation,f->generation);}
  pthread_mutex_lock(&form_watch.mutex);
  if(needed&&!form_watch.started){
    if(!current_controller){pthread_mutex_unlock(&form_watch.mutex);return 0;}
    form_watch.controller=current_controller;form_watch.owner=pthread_self();
    form_watch.running=1;form_watch.generation=generation;
    form_watch.started=!pthread_create(&form_watch.thread,NULL,watch_native_forms,NULL);
    if(!form_watch.started)form_watch.running=0;
  }
  int join=!needed&&form_watch.started;
  if(join){form_watch.running=0;form_watch.pending=0;}
  pthread_cond_signal(&form_watch.condition);
  pthread_t thread=form_watch.thread;
  int usable=!needed||form_watch.started;
  pthread_mutex_unlock(&form_watch.mutex);
  if(join){pthread_join(thread,NULL);pthread_mutex_lock(&form_watch.mutex);form_watch.started=0;pthread_mutex_unlock(&form_watch.mutex);}
  return usable;
}
static void form_native_work(void *controller) {
  if(!forms_animation_enabled&&!forms_sliders_enabled&&!forms_popups_enabled)return;
  pthread_mutex_lock(&form_watch.mutex);
  int ready=form_watch.running&&form_watch.pending&&form_watch.controller==controller&&pthread_equal(form_watch.owner,pthread_self());
  if(ready)form_watch.pending=0;
  pthread_mutex_unlock(&form_watch.mutex);
  if(!ready)return;
  if(active_form&&active_form->kind==NXS_SLIDER){
    struct NativeForm *slider=active_form;
    struct NXSResponse *response=form_request(slider,5,0,0,0);
    apply_slider_value(slider,response,2);
  }
  struct NativeForm *popup=native_forms;
  while(popup&&!(popup->kind==NXS_POPUP&&popup->popup_open))popup=popup->next;
  if(popup)popup_after_input(popup,form_request(popup,5,0,0,0));
  for(struct NativeForm *f=native_forms;f;f=f->next){
    if(!f->painted||!((f->kind==NXS_PROGRESS&&f->indeterminate)||(f==active_form&&f->kind==NXS_SLIDER)))continue;
    void *layout=decode_member((const char *)f->node+48);if(!layout)continue;
    invalidate_form(f);
    void *view=((void *(*)(const void *))(base+0xe11b43c))(layout);
    if(view)((void (*)(void *))(base+0xdf93618))(view);
  }
  static __thread unsigned logged;
  if(logged++<32)note("native invalidation applied on renderer thread");
}
static int paint_progress(void *self,const void *element,const void *layout,
    const void *info,const struct Rect *rect,const void *style) {
  if(*(const uintptr_t *)element!=base+0x11d4a168+16)
    return original_progress(self,element,layout,info,rect,style);
  /* Chromium validates the model; NativeUI owns animation and invalidation. */
  double position=((double (*)(const void *))(base+0xe7bb2e8))(element);
  if(isfinite(position)&&((position>=0&&position<=1)||
     (position==-1&&forms_animation_enabled&&current_controller))) {
    if(!paint_form(NXS_PROGRESS,self,element,NULL,style,info,rect)&&refresh_form_watch())return 0;
  } else {
    struct NativeForm *form=find_form(element);if(form){form->painted=0;form->indeterminate=0;}
    refresh_form_watch();
  }
  return original_progress(self,element,layout,info,rect,style);
}
static struct Detour progress_detour={NXS_PROGRESS_OFFSET,nxs_progress_bytes,
  paint_progress,(void **)&original_progress};
