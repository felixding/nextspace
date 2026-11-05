/* Native menu/edit callbacks must run on their registering UI thread.
 * Uses the real transport with a bounded fake peer, without a GUI dependency.
 * GPL-2.0-or-later. */
#define _GNU_SOURCE
#include "NativeUI.h"
#include "Bridge/Protocol.h"
#include <assert.h>
#include <stdio.h>
#include <stddef.h>
#include <limits.h>
#include <sys/socket.h>
#include <sys/un.h>
static void note(const char *message) {(void)message;}
#include "Bridge/Transport.inc"
static pthread_t owner;
static int calls,edits,wrong_thread,edit_registration,command_registration,worker_unregister;
static int proposals(const struct NXSNativeTextEdit *edit,const char *text,const char *command)
{
  assert(edit->serial==102&&!strcmp(text,"X")&&!strcmp(command,"insertText:"));
  edits++;if(!pthread_equal(owner,pthread_self()))wrong_thread++;return 0;
}
static int command(const struct NXSNativeCommand *request,const char *selector)
{
  assert(request->process==identity()&&request->serial==100+request->phase&&!strcmp(selector,"copy:"));
  calls++;if(!pthread_equal(owner,pthread_self()))wrong_thread++;
  return 1;
}
static void reply(int connection,const struct NXSControlRequest *request)
{
  struct NXSResponse response={.magic=request->magic,.size=sizeof(response),.reserved=request->reserved};
  response.parts[3].x=1;
  assert(send(connection,&response,sizeof(response),MSG_NOSIGNAL)==sizeof(response));
}
static void decision(int callback,unsigned turn)
{
  struct pollfd ready={.fd=callback,.events=POLLIN};assert(poll(&ready,1,1500)==1);
  struct NXSNativeCommandDecision result;
  assert(recv(callback,&result,sizeof(result),0)==sizeof(result));
  assert(result.magic==(turn==2?NXS_NATIVE_TEXT_EDIT_MAGIC:NXS_NATIVE_COMMAND_MAGIC));
  assert(result.serial==100+turn&&result.result==(turn==2?0:1));
}
static void *peer(void *context)
{
  int server=*(int *)context,connection=accept(server,NULL,NULL),callback=-1,queries=0,decided=0;
  assert(connection>=0);
  for(;;) {
    struct NXSControlRequest request;
    struct iovec buffer={.iov_base=&request,.iov_len=sizeof(request)};
    char ancillary[CMSG_SPACE(sizeof(int))];
    struct msghdr message={.msg_iov=&buffer,.msg_iovlen=1,.msg_control=ancillary,.msg_controllen=sizeof(ancillary)};
    ssize_t bytes=recvmsg(connection,&message,0);if(bytes==0)break;
    assert(bytes==sizeof(request));
    if(request.operation==19) {
      struct cmsghdr *c=CMSG_FIRSTHDR(&message);
      assert(c&&c->cmsg_level==SOL_SOCKET&&c->cmsg_type==SCM_RIGHTS);
      memcpy(&callback,CMSG_DATA(c),sizeof(callback));assert(callback>=0);
    } else if(request.operation==9) {
      unsigned turn=queries/2;
      if(queries++%2==0) {
        decided=0;
        if(turn<2) {
          struct {struct NXSNativeCommand command;char selector[5];} packet={
            .command={.magic=NXS_NATIVE_COMMAND_MAGIC,.size=sizeof(struct NXSNativeCommand)+5,
              .process=request.process,.kind=NXS_TEXTFIELD,.control=1,.serial=100+turn,
              .phase=turn,.command_size=5},.selector={'c','o','p','y',':'}};
          assert(send(callback,&packet,packet.command.size,MSG_NOSIGNAL)==packet.command.size);
        } else {
          struct {struct NXSNativeTextEdit edit;char text[12];} packet={
            .edit={.magic=NXS_NATIVE_TEXT_EDIT_MAGIC,.size=sizeof(struct NXSNativeTextEdit)+12,
              .process=request.process,.kind=NXS_TEXTFIELD,.control=1,.serial=102,
              .text_size=1,.command_size=11},.text="XinsertText:"};
          assert(send(callback,&packet,packet.edit.size,MSG_NOSIGNAL)==packet.edit.size);
        }
        /* The correct transport leaves callbacks queued for their UI owner. */
        struct pollfd ready={.fd=callback,.events=POLLIN};int result=poll(&ready,1,200);assert(result>=0);
        if(result){decision(callback,turn);decided=1;}
      } else if(!decided){decision(callback,turn);decided=1;}
    }
    reply(connection,&request);
  }
  assert(queries==6&&decided);close(callback);close(connection);return NULL;
}
static void *worker(void *unused)
{
  (void)unused;
  edit_registration=native_text_filter_register(proposals);
  command_registration=native_command_filter_register(command);
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=9,.process=identity()};
  assert(exchange_bytes(&request,sizeof(request)));return NULL;
}
static void *unregister_worker(void *unused)
{(void)unused;worker_unregister=native_text_filter_unregister();return NULL;}
int main(void)
{
  char directory[]="/tmp/nxs-command-owner-XXXXXX";assert(mkdtemp(directory));
  struct sockaddr_un address={.sun_family=AF_UNIX};
  int length=snprintf(address.sun_path,sizeof(address.sun_path),"%s/native.sock",directory);
  assert(length>0&&(size_t)length<sizeof(address.sun_path));
  int server=socket(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC,0);assert(server>=0);
  assert(!bind(server,(void *)&address,sizeof(address))&&!listen(server,1));
  pthread_t helper,background;assert(!pthread_create(&helper,NULL,peer,&server));owner=pthread_self();
  assert(bridge_connect(address.sun_path));assert(native_text_filter_register(proposals));
  assert(native_command_filter_register(command));
  for(int turn=0;turn<3;turn++) {
    assert(!pthread_create(&background,NULL,worker,NULL));assert(!pthread_join(background,NULL));
    struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=9,.process=identity()};
    assert(exchange_bytes(&request,sizeof(request)));
  }
  assert(!pthread_create(&background,NULL,unregister_worker,NULL));assert(!pthread_join(background,NULL));
  int owner_unregister=native_text_filter_unregister();close(channel);channel=-1;
  assert(!pthread_join(helper,NULL));close(server);unlink(address.sun_path);rmdir(directory);
  int passed=calls==2&&edits==1&&!wrong_thread&&!edit_registration&&!command_registration&&!worker_unregister&&owner_unregister;
  printf("{\"passed\":%s,\"command_callbacks\":%d,\"edit_callbacks\":%d,\"wrong_thread_callbacks\":%d,\"worker_edit_registration\":%d,\"worker_command_registration\":%d,\"worker_unregister\":%d,\"owner_unregister\":%d}\n",
    passed?"true":"false",calls,edits,wrong_thread,edit_registration,command_registration,worker_unregister,owner_unregister);
  return !passed;
}
