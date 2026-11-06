/* Verify stale native proposals cannot cross a host generation. No UI model.
 * SPDX-License-Identifier: GPL-2.0-or-later */
#define _GNU_SOURCE
#include "NativeUI.h"
#include "Bridge/Protocol.h"
#include <assert.h>
static void note(const char *message) {(void)message;}
#include "Bridge/Transport.inc"
static unsigned callbacks;
static int menu(const struct NXSNativeMenuCommand *request) {(void)request; callbacks++; return 1;}
static int command(const struct NXSNativeCommand *request,const char *selector)
{(void)request;(void)selector; callbacks++; return 1;}
static int edit(const struct NXSNativeTextEdit *request,const char *text,const char *selector)
{(void)request;(void)text;(void)selector; callbacks++; return 1;}
static void deliver(int sender,const void *packet,size_t size,int accepted)
{
  unsigned before=callbacks;
  assert(send(sender,packet,size,0)==(ssize_t)size);
  int owns=0;assert(dispatch_native_edit(&owns));
  if(owns)pthread_mutex_unlock(&shared->mutex);
  assert(callbacks==before+accepted);
  char response[64];ssize_t bytes;
  while((bytes=recv(sender,response,sizeof(response),MSG_DONTWAIT))>0)assert(accepted);
  assert(bytes<0 && errno==EAGAIN);
}
static void *reply_epoch(void *argument)
{
  int descriptor=*(int *)argument;
  struct NXSControlRequest request;assert(recv(descriptor,&request,sizeof(request),0)==sizeof(request));
  struct NXSResponse response={.magic=request.magic,.size=sizeof(response),.reserved=request.reserved};
  response.parts[4].x=3ULL<<32;
  assert(send(descriptor,&response,sizeof(response),0)==sizeof(response));return NULL;
}
int main(void)
{
  struct Shared fixture={.mutex=PTHREAD_MUTEX_INITIALIZER};shared=&fixture;
  int pair[2],rpc[2];assert(!socketpair(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC,0,pair));
  assert(!socketpair(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC,0,rpc));channel=rpc[0];
  native_edit_channel=pair[0];native_edit_pid=getpid();native_edit_owner_thread=1;
  native_menu_handler=menu;native_command_handler=command;native_edit_handler=edit;
  atomic_store(&native_host_epoch,2);
  struct NXSNativeMenuCommand action={.magic=NXS_NATIVE_MENU_COMMAND_MAGIC,.size=sizeof(action),.phase=1,.serial=(1ULL<<32)+1};
  deliver(pair[1],&action,sizeof(action),0);
  struct {struct NXSNativeCommand request;char selector[2];} selector={.request={.magic=NXS_NATIVE_COMMAND_MAGIC,.size=sizeof(struct NXSNativeCommand)+2,.phase=1,.serial=(1ULL<<32)+2,.command_size=2},.selector={'x',':'}};
  deliver(pair[1],&selector,sizeof(struct NXSNativeCommand)+2,0);
  struct {struct NXSNativeTextEdit request;char text;} proposal={.request={.magic=NXS_NATIVE_TEXT_EDIT_MAGIC,.size=sizeof(struct NXSNativeTextEdit)+1,.serial=(1ULL<<32)+3,.text_size=1},.text='X'};
  deliver(pair[1],&proposal,sizeof(struct NXSNativeTextEdit)+1,0);
  action.serial=(2ULL<<32)+1;deliver(pair[1],&action,sizeof(action),1);
  selector.request.serial=(2ULL<<32)+2;deliver(pair[1],&selector,sizeof(struct NXSNativeCommand)+2,1);
  proposal.request.serial=(2ULL<<32)+3;deliver(pair[1],&proposal,sizeof(struct NXSNativeTextEdit)+1,1);
  pthread_t worker;assert(!pthread_create(&worker,NULL,reply_epoch,&rpc[1]));
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=9};
  assert(exchange_bytes(&request,sizeof(request)));assert(!pthread_join(worker,NULL));
  assert(atomic_load(&native_host_epoch)==3);deliver(pair[1],&action,sizeof(action),0);
  close(pair[0]);close(pair[1]);close(rpc[0]);close(rpc[1]);
  puts("{\"passed\":8,\"callbacks\":3}");return 0;
}
