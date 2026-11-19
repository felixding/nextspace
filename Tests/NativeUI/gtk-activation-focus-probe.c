/* Exercise the production GTK handoff with a queued native focus-in. */
#define _GNU_SOURCE
#include <assert.h>
#include <stdio.h>
#include <unistd.h>
#include <poll.h>
#include <dlfcn.h>
#include <string.h>
#ifndef NXS_GTK_ACTIVATION_SOURCE
#define NXS_GTK_ACTIVATION_SOURCE "../../Libraries/NativeUI/Bridge/Gtk3Geometry.c"
#endif
#include NXS_GTK_ACTIVATION_SOURCE
static char *grant;
static int input_seen;
static void received(uintptr_t surface,const char *token,void *context)
{if(token){free(grant);grant=strdup(token);}else input_seen=1;}
int main(void)
{
  void *gtk=dlopen("libgtk-3.so.0",RTLD_NOW|RTLD_GLOBAL);assert(gtk);
  int (*init)(void*,void*)=dlsym(gtk,"gtk_init_check");
  void *(*create)(int)=dlsym(gtk,"gtk_window_new");
  void (*title)(void*,const char*)=dlsym(gtk,"gtk_window_set_title");
  void (*size)(void*,int,int)=dlsym(gtk,"gtk_window_set_default_size");
  void (*events)(void*,int)=dlsym(gtk,"gtk_widget_add_events");
  void (*show)(void*)=dlsym(gtk,"gtk_widget_show_all");
  void *(*getwindow)(void*)=dlsym(gtk,"gtk_widget_get_window");
  unsigned (*state)(void*)=dlsym(RTLD_DEFAULT,"gdk_window_get_state");
  assert(init(NULL,NULL));void *widget=create(0);title(widget,"GTK token source");size(widget,300,220);
  events(widget,(1<<8)|(1<<9));show(widget);void *window=getwindow(widget);assert(window);
  assert(nxs_gtk3_activation_observe_requests(received,NULL));
  puts("{\"phase\":\"ready\"}");fflush(stdout);
  char line[64];int reported_input=0;
  for(;;){
    while(g_main_context_iteration(NULL,FALSE));
    if(input_seen&&!reported_input){puts("{\"phase\":\"input\"}");fflush(stdout);reported_input=1;}
    struct pollfd fd={0,POLLIN,0};if(poll(&fd,1,10)<=0)continue;
    assert(fgets(line,sizeof(line),stdin));
    if(!strcmp(line,"pause\n")){
      assert(input_seen&&activation_pending_window==window);
      assert(!(state(window)&(1<<7))); /* The original GDK window processed focus-out. */
      puts("{\"phase\":\"paused-after-focus-out\"}");fflush(stdout);
      assert(fgets(line,sizeof(line),stdin)&&!strcmp(line,"token\n"));
      assert(nxs_gtk3_activation_request());
      /* Select the already scheduled production idle before GDK consumes its
       * queued focus-in. This fixes the event ordering, not the control code. */
      if(activation_idle){g_source_remove(activation_idle);activation_idle=0;}
      activation_notify(NULL);assert(grant);
      printf("{\"phase\":\"token\",\"token\":\"%s\"}\n",grant);fflush(stdout);
      assert(fgets(line,sizeof(line),stdin)&&!strcmp(line,"finish\n"));break;
    }
  }
  return 0;
}
