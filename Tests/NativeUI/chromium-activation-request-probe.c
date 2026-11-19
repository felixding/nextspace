/* Exercise the production Ozone adapter's token timing and input generation.
 * The original transport is observed at its request/callback boundary. */
#define _GNU_SOURCE
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdatomic.h>
#include <unistd.h>
#include <sys/socket.h>
#include <dlfcn.h>
struct OzoneActivationToken;
struct OzoneGeometryWindow {struct OzoneGeometryWindow *next;void *window,*observation;unsigned depth;int retired;struct OzoneActivationToken *tokens;};
static struct OzoneGeometryWindow *ozone_geometry_windows;
static void *ozone_field(void *object,size_t offset){return *(void **)((char *)object+offset);}
static uintptr_t base;
static int log_fd=-1;
static _Atomic uint32_t native_host_epoch=1;
static unsigned wayland_auxiliary_capabilities=1;
struct Detour {uintptr_t offset;const void *bytes;void *replacement;void **original;};
static int prepare_detours(void *items,size_t count){return 1;}
static void activate_detours(void *items,size_t count){}
static void note(const char *message){}
static int pair[2],resets,pointers,requests,published;
static uint32_t last_serial,last_ticket;
static int (*watch_callback)(int,unsigned,void *);
static struct {void (*callback)(void *,const char *);void *context;} pending[8];
static int request_token(void *surface,void *seat,uint32_t serial,void (*callback)(void *,const char *),void *context)
{assert(surface==(void *)0x56);last_serial=serial;pending[requests++]=(typeof(pending[0])){callback,context};return 1;}
static int (*wayland_request_activation)(void *,void *,uint32_t,void (*)(void *,const char *),void *)=request_token;
static const char *parent(void *surface){return "original-parent";}
static const char *(*wayland_surface_parent)(void *)=parent;
static int native_auxiliary_source_watch(void){assert(!socketpair(AF_UNIX,SOCK_SEQPACKET,0,pair));return pair[0];}
static void native_auxiliary_source_pointer(uint64_t surface){assert(surface==0x34);pointers++;}
static int native_auxiliary_token_publish(uint64_t surface,uint32_t serial,const char *token,const char *owner)
{assert(surface==0x34&&!serial&&!token&&!owner);resets++;return 1;}
static int native_auxiliary_token_publish_query(uint64_t surface,uint32_t serial,const char *token,const char *owner,uint32_t ticket)
{assert(surface==0x34&&serial&&token&&!strcmp(owner,"original-parent"));published++;last_ticket=ticket;return 1;}
static unsigned add_watch(int descriptor,unsigned condition,int (*callback)(int,unsigned,void *),void *context)
{assert(descriptor==pair[0]);watch_callback=callback;return 1;}
static int remove_watch(unsigned source){return 1;}
static void *probe_dlsym(void *handle,const char *name)
{return !strcmp(name,"g_unix_fd_add")?(void *)add_watch:!strcmp(name,"g_source_remove")?(void *)remove_watch:NULL;}
#define dlsym probe_dlsym
#ifndef NXS_CHROMIUM_ACTIVATION_SOURCE
#define NXS_CHROMIUM_ACTIVATION_SOURCE "../../Experiments/ChromiumScrollers/wayland-activation.inc"
#endif
#include NXS_CHROMIUM_ACTIVATION_SOURCE
#undef dlsym
static unsigned checks;
static void check(const char *name,int passed)
{printf("{\"case\":\"%s\",\"passed\":%s}\n",name,passed?"true":"false");fflush(stdout);assert(passed);checks++;}
static void request(uint64_t ticket)
{assert(send(pair[1],&ticket,sizeof(ticket),0)==sizeof(ticket));assert(watch_callback(pair[0],1,NULL));}
int main(void)
{
  struct OzoneGeometryWindow window={.window=(void *)0x34,.observation=(void *)0x56};
  struct OzoneActivationFocus focus={.device=(void *)0x12,.window=window.window};
  ozone_geometry_windows=&window;ozone_activation_focus=&focus;
  ozone_activation_input(focus.device,0,10,1);
  check("input-does-not-cache-an-expiring-token",requests==0);
  check("real-input-retires-prior-grant-before-presentation",resets==1&&pointers==1&&watch_callback);
  request(1);
  check("presentation-requests-original-token-with-real-serial",requests==1&&last_serial==10&&!published);
  pending[0].callback(pending[0].context,"fresh-token");
  check("original-token-carries-presentation-ticket",published==1&&last_ticket==1);
  ozone_activation_input(focus.device,0,11,1);request(2);
  ozone_activation_input(focus.device,0,12,1);
  pending[1].callback(pending[1].context,"superseded-token");
  check("new-input-rejects-an-inflight-old-token",published==1);
  request(3);pending[2].callback(pending[2].context,"current-token");
  check("next-presentation-uses-current-input-and-ticket",published==2&&last_serial==12&&last_ticket==3);
  ozone_activation_input(focus.device,0,13,0);
  check("release-does-not-create-another-input-grant",resets==3&&requests==3);
  ozone_activation_focus=NULL;ozone_activation_input(focus.device,0,14,1);
  check("unowned-input-does-not-supply-a-source",resets==3&&requests==3);
  watch_callback(pair[0],16,NULL);close(pair[1]);
  printf("{\"complete\":true,\"checks\":%u}\n",checks);
  return 0;
}
