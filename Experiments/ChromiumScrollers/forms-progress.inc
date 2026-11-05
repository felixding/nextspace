/* Read-only application model binding. NSProgressIndicator owns its pixels. */
#include "pinned-progress.h"
static int (*original_progress)(void *,const void *,const void *,const void *,const struct Rect *,const void *);
static struct {
  pthread_mutex_t mutex;
  pthread_cond_t condition;
  pthread_t thread,owner;
  void *controller;
  int running,started,pending,wake_fd,failed;
  double generation;
} form_watch={.mutex=PTHREAD_MUTEX_INITIALIZER,.condition=PTHREAD_COND_INITIALIZER,.wake_fd=-1};
static void wake_form_watch(void)
{
  if(form_watch.wake_fd>=0){uint64_t one=1;ssize_t result;
    do result=write(form_watch.wake_fd,&one,sizeof(one));while(result<0&&errno==EINTR);}
  pthread_cond_signal(&form_watch.condition);
}
static void close_form_notifier(void)
{
  if(form_watch.wake_fd<0)return;
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=16,.process=identity()};
  exchange_bytes(&request,sizeof(request));close(form_watch.wake_fd);form_watch.wake_fd=-1;
}
static void fail_form_watch(void)
{
  pthread_mutex_lock(&form_watch.mutex);
  if(form_watch.running){form_watch.failed=1;form_watch.pending=1;
    ((void (*)(void *))(base+0xa2e11e0))(form_watch.controller);}
  pthread_mutex_unlock(&form_watch.mutex);
  note("native invalidation transport closed");
}
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
    if(form_watch.running&&form_watch.wake_fd<0){
      /* Bound transport recovery waits, not widget animation intervals. The
       * next animation deadline comes only from the native UI run loop. */
      delay=!isfinite(delay)||delay<0?1:fmin(1,fmax(.001,delay));
      struct timespec until;clock_gettime(CLOCK_REALTIME,&until);
      until.tv_sec+=(time_t)delay;until.tv_nsec+=(long)((delay-floor(delay))*1e9);
      if(until.tv_nsec>=1000000000){until.tv_nsec-=1000000000;until.tv_sec++;}
      pthread_cond_timedwait(&form_watch.condition,&form_watch.mutex,&until);
    }
    pthread_mutex_unlock(&form_watch.mutex);
    if(form_watch.wake_fd>=0){
      /* The helper signals actual native invalidations. Do not wait for a
       * guessed widget period or hold the shared request channel while idle.
       * Observe channel shutdown without consuming another renderer's reply. */
      struct pollfd descriptors[]={{.fd=form_watch.wake_fd,.events=POLLIN},{.fd=channel,.events=POLLRDHUP}};
      int result;do result=poll(descriptors,2,-1);while(result<0&&errno==EINTR);
      if(result<0||(descriptors[0].revents&(POLLERR|POLLHUP|POLLNVAL))||
         (descriptors[1].revents&(POLLERR|POLLHUP|POLLRDHUP|POLLNVAL))){fail_form_watch();break;}
      if(descriptors[0].revents&POLLIN){uint64_t count;ssize_t bytes;
        do bytes=read(form_watch.wake_fd,&count,sizeof(count));while(bytes<0&&errno==EINTR);}
    }
  }
  return NULL;
}
static int refresh_form_watch(void) {
  if(!forms_animation_enabled&&!forms_sliders_enabled&&!forms_popups_enabled&&!forms_text_enabled)return 1;
  int needed=active_form&&active_form->kind==NXS_SLIDER;double generation=needed?active_form->generation:0;
  if(views_watch_needed())needed=1;
  for(struct NativeForm *f=native_forms;f;f=f->next)
    if((f->kind==NXS_PROGRESS&&f->indeterminate&&f->painted)||(f->kind==NXS_POPUP&&f->popup_open)||(text_kind(f->kind)&&f->painted)){needed=1;generation=fmax(generation,f->generation);}
  pthread_mutex_lock(&form_watch.mutex);
  if(form_watch.failed)needed=0;
  if(needed&&!form_watch.started){
    if(!current_controller){pthread_mutex_unlock(&form_watch.mutex);return 0;}
    form_watch.controller=current_controller;form_watch.owner=pthread_self();
    form_watch.running=1;form_watch.generation=generation;
    if(forms_notifications_enabled){
      int descriptor=eventfd(0,EFD_CLOEXEC|EFD_NONBLOCK);
      if(descriptor>=0){
        struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=15,
          .process=identity(),.value=generation};
        struct NXSResponse *response=exchange_bytes_descriptor(&request,sizeof(request),descriptor);
        if(response&&response->parts[3].x==1){form_watch.wake_fd=descriptor;note("native invalidation descriptor registered");}
        else close(descriptor);
      }
    }
    form_watch.started=!pthread_create(&form_watch.thread,NULL,watch_native_forms,NULL);
    if(!form_watch.started){form_watch.running=0;close_form_notifier();}
  }
  int join=!needed&&form_watch.started;
  if(join){form_watch.running=0;form_watch.pending=0;}
  if(join)wake_form_watch();
  else if(form_watch.wake_fd<0)pthread_cond_signal(&form_watch.condition);
  pthread_t thread=form_watch.thread;
  int usable=!needed||form_watch.started;
  pthread_mutex_unlock(&form_watch.mutex);
  if(join){pthread_join(thread,NULL);pthread_mutex_lock(&form_watch.mutex);form_watch.started=0;close_form_notifier();pthread_mutex_unlock(&form_watch.mutex);}
  return usable;
}
static void schedule_form_paint(struct NativeForm *form) {
  void *layout=decode_member((const char *)form->node+48);if(!layout)return;
  invalidate_form(form);
  void *view=((void *(*)(const void *))(base+0xe11b43c))(layout);
  if(view)((void (*)(void *))(base+0xdf93618))(view);
}
static void form_native_work(void *controller) {
  if(!forms_animation_enabled&&!forms_sliders_enabled&&!forms_popups_enabled&&!forms_text_enabled)return;
  pthread_mutex_lock(&form_watch.mutex);
  int ready=form_watch.running&&form_watch.pending&&form_watch.controller==controller&&pthread_equal(form_watch.owner,pthread_self());
  int failed=form_watch.failed;
  if(ready)form_watch.pending=0;
  pthread_mutex_unlock(&form_watch.mutex);
  if(!ready)return;
  views_native_work(failed);
  if(failed){
    if(active_form)finish_form(-10000,-10000,0);
    for(;;){struct NativeForm *popup=native_forms;
      while(popup&&!(popup->kind==NXS_POPUP&&popup->popup_open))popup=popup->next;
      if(!popup)break;
      popup->popup_open=0;popup_engine_closed(popup->popup_engine);
    }
    for(struct NativeForm *f=native_forms;f;f=f->next)
      if(text_kind(f->kind)){f->painted=0;schedule_form_paint(f);}
    refresh_form_watch();return;
  }
  if(active_form&&active_form->kind==NXS_SLIDER){
    struct NativeForm *slider=active_form;
    struct NXSResponse *response=form_request(slider,5,0,0,0);
    apply_slider_value(slider,response,2);
  }
  if(active_form&&text_kind(active_form->kind))echo_text_selection(active_form);
  struct NativeForm *popup=native_forms;
  while(popup&&!(popup->kind==NXS_POPUP&&popup->popup_open))popup=popup->next;
  if(popup)popup_after_input(popup,form_request(popup,5,0,0,0));
  for(struct NativeForm *f=native_forms;f;f=f->next){
    if(!f->painted||!((f->kind==NXS_PROGRESS&&f->indeterminate)||(f==active_form&&f->kind==NXS_SLIDER)||text_kind(f->kind)))continue;
    schedule_form_paint(f);
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
