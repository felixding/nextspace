/* Exercise native timers/invalidation without reproducing their animation.
 * GPL-2.0-or-later. */
#include "NativeUI.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static double now(void)
{struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9;}
static uint64_t draw(NXSControl *control,const char *directory,int frame)
{
  NXSBitmap bitmap=nxs_control_draw(control,1);
  assert(bitmap.pixels&&bitmap.width==128&&bitmap.height==24&&bitmap.stride==512);
  uint64_t hash=14695981039346656037ull;
  for(int i=0;i<bitmap.stride*bitmap.height;i++){hash^=bitmap.pixels[i];hash*=1099511628211ull;}
  if(directory){
    char path[4096];snprintf(path,sizeof(path),"%s/animation-%02d.argb",directory,frame);
    FILE *file=fopen(path,"wb");assert(file);
    assert(fwrite(bitmap.pixels,bitmap.stride,bitmap.height,file)==(size_t)bitmap.height);fclose(file);
  }
  assert(!nxs_control_needs_display(control));return hash;
}
static unsigned actions;
static void changed(void *unused,int event,const NXSControlState *state){actions++;}
int main(int argc,char **argv)
{
  if(argc>1&&!strcmp(argv[1],"--expect-no-events")){
    assert(!nxs_native_ui_event_capabilities());
    assert(nxs_native_ui_dispatch_events(0)==-1);
    assert(!nxs_control_needs_display(NULL));
    puts("{\"older_provider_without_events\":true}");return 0;
  }
  assert(nxs_native_ui_event_capabilities()==NXS_EVENTS);
  const char *directory=argc>1?argv[1]:NULL;
  NXSControl *control=nxs_control_create(NXS_PROGRESS,changed,NULL,NULL);assert(control);
  NXSControlConfig config={.size=sizeof(config),.width=128,.height=24,.minimum=0,.maximum=100,
    .value=0,.enabled=1,.indeterminate=1};
  assert(nxs_control_sync(control,&config));
  draw(control,directory,0);
  if(getenv("NXS_NATIVE_UI_ANIMATION_HOLD")){
    puts("{\"event\":\"host-live\"}");fflush(stdout);assert(getchar()!=EOF);
  }
  uint64_t hashes[12];double waits[12],times[12],start=now();unsigned frames=0,unique=0;
  while(frames<12&&now()-start<5){
    double next=nxs_native_ui_dispatch_events(.2);
    if(!nxs_control_needs_display(control))continue;
    times[frames]=now()-start;waits[frames]=next;
    hashes[frames]=draw(control,directory,frames+1);
    unsigned i;for(i=0;i<frames;i++)if(hashes[i]==hashes[frames])break;
    if(i==frames)unique++;
    frames++;
  }
  if(frames!=12||unique<2||actions){
    fprintf(stderr,"frames=%u unique=%u actions=%u times:",frames,unique,actions);
    for(unsigned i=0;i<frames;i++)fprintf(stderr," %.6f/%.6f",times[i],waits[i]);
    fputc('\n',stderr);
  }
  assert(frames==12&&unique>=2&&!actions);
  if(getenv("NXS_NATIVE_UI_ANIMATION_HOLD")){
    puts("{\"event\":\"animation-live\"}");fflush(stdout);assert(getchar()!=EOF);
  }
  /* Native mode change stops its timer. Servicing events must leave the
   * determinate bitmap stable; the bridge has no frame counter to reset. */
  config.indeterminate=0;config.value=50;assert(nxs_control_sync(control,&config));
  uint64_t stable=draw(control,NULL,0);double stopped=now();unsigned static_events=0;
  while(now()-stopped<.35){
    nxs_native_ui_dispatch_events(.05);
    if(nxs_control_needs_display(control)){static_events++;assert(draw(control,NULL,0)==stable);}
  }
  assert(!static_events);
  config.indeterminate=1;assert(nxs_control_sync(control,&config));draw(control,NULL,0);
  double restart=now();int restarted=0;
  while(now()-restart<2&&!restarted){nxs_native_ui_dispatch_events(.2);restarted=nxs_control_needs_display(control);}
  assert(restarted);
  assert(nxs_control_destroy(control));
  /* A live native timer retains its target. Destruction must stop it before
   * releasing that view; servicing its old deadline must remain safe. */
  nxs_native_ui_dispatch_events(.2);
  assert(nxs_native_ui_dispatch_events(NAN)==-1);
  assert(nxs_native_ui_dispatch_events(-1)==-1);
  printf("{\"frames\":%u,\"unique_native_images\":%u,\"static_invalidations\":%u,\"restart\":true,\"actions\":%u,\"times\":[",frames,unique,static_events,actions);
  for(unsigned i=0;i<frames;i++)printf("%s%.6f",i?",":"",times[i]);
  printf("],\"native_next_delays\":[");
  for(unsigned i=0;i<frames;i++)printf("%s%.6f",i?",":"",waits[i]);
  puts("]}");return 0;
}
