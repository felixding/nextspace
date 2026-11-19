/* Shared one-way publication contract; no provider or toolkit is linked. */
#define _GNU_SOURCE
#include "../../Libraries/NativeUI/Bridge/Protocol.h"
#include "../../Libraries/NativeUI/NativeUI.h"
#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>
static int channel=-1;
static uint32_t identity(void){return 17;}
#include "../../Libraries/NativeUI/Bridge/AuxiliaryActivation.inc"
_Static_assert(offsetof(NXSNativeUIAPI,control_auxiliary_capabilities)==720,"Preserve previous provider prefix");
static unsigned checks;
static void check(const char *name,int passed)
{printf("{\"case\":\"%s\",\"passed\":%s}\n",name,passed?"true":"false");fflush(stdout);assert(passed);checks++;}
int main(void)
{
  int pair[2];assert(!socketpair(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC,0,pair));channel=pair[0];
  const char *token="opaque-test-token";
  check("publication-does-not-wait-for-a-reply",native_auxiliary_token_publish(42,123,token,NULL));
  unsigned char buffer[8192];ssize_t size=recv(pair[1],buffer,sizeof(buffer),MSG_DONTWAIT);
  struct NXSControlRequest *request=(void *)buffer;
  check("publication-is-one-atomic-envelope",size==(ssize_t)(sizeof(*request)+strlen(token))&&
      request->magic==NXS_CHROMIUM_CONTROL_MAGIC&&request->operation==64&&request->process==17&&
      request->control==42&&request->state==1&&request->x==123&&request->reserved==0&&
      !memcmp(buffer+sizeof(*request),token,strlen(token)));
  check("publication-inserts-no-extra-packet",recv(pair[1],buffer,sizeof(buffer),MSG_DONTWAIT)<0&&errno==EAGAIN);
  check("empty-and-unowned-publications-are-rejected",!native_auxiliary_token_publish(0,123,token,NULL)&&
      !native_auxiliary_token_publish(42,123,"",NULL)&&
      !native_auxiliary_token_publish(42,123,NULL,NULL));
  check("toolkit-owned-serial-needs-no-private-metadata",native_auxiliary_token_publish(42,0,token,NULL));
  size=recv(pair[1],buffer,sizeof(buffer),MSG_DONTWAIT);
  check("toolkit-token-keeps-serial-unavailable",size==(ssize_t)(sizeof(*request)+strlen(token))&&request->x==0);
  char huge[4098];memset(huge,'a',sizeof(huge)-1);huge[sizeof(huge)-1]=0;
  check("oversize-token-is-rejected",!native_auxiliary_token_publish(42,123,huge,NULL));
  check("parent-handle-shares-the-authenticated-envelope",native_auxiliary_token_publish(42,123,token,"exported-parent"));
  size=recv(pair[1],buffer,sizeof(buffer),MSG_DONTWAIT);
  check("parent-payload-keeps-token-and-owner-separate",request->state==2&&
    size==(ssize_t)(sizeof(*request)+strlen(token)+1+strlen("exported-parent"))&&
    !strcmp((char *)buffer+sizeof(*request),token)&&
    !memcmp(buffer+sizeof(*request)+strlen(token)+1,"exported-parent",strlen("exported-parent")));
  check("oversize-parent-is-rejected",!native_auxiliary_token_publish(42,123,token,huge));
  int watch=native_auxiliary_source_watch();
  check("presentation-token-source-registers-without-a-reply",watch>=0);
  char ancillary[CMSG_SPACE(sizeof(int))];struct iovec payload={buffer,sizeof(buffer)};
  struct msghdr message={.msg_iov=&payload,.msg_iovlen=1,.msg_control=ancillary,.msg_controllen=sizeof(ancillary)};
  size=recvmsg(pair[1],&message,MSG_CMSG_CLOEXEC);
  struct cmsghdr *descriptor=CMSG_FIRSTHDR(&message);int remote=-1;
  if(descriptor&&descriptor->cmsg_level==SOL_SOCKET&&descriptor->cmsg_type==SCM_RIGHTS)
    memcpy(&remote,CMSG_DATA(descriptor),sizeof(remote));
  check("source-registration-preserves-the-private-endpoint",size==sizeof(*request)&&request->state==3&&remote>=0&&!request->control&&!request->value);
  uint64_t query=0x12345678,received=0;
  assert(send(remote,&query,sizeof(query),MSG_NOSIGNAL)==sizeof(query));
  check("toolkit-receives-opaque-presentation-request",recv(watch,&received,sizeof(received),0)==sizeof(received)&&received==query);
  check("requested-token-publishes-with-the-original-ticket",native_auxiliary_token_publish_query(42,0,token,"exported-parent",query));
  size=recv(pair[1],buffer,sizeof(buffer),MSG_DONTWAIT);
  check("requested-token-retains-ordinary-payload-and-ticket",size>(ssize_t)sizeof(*request)&&request->value==query&&request->state==2);
  close(remote);close(watch);
  int small=4096;assert(!setsockopt(pair[0],SOL_SOCKET,SO_SNDBUF,&small,sizeof(small)));
  while(send(pair[0],buffer,512,MSG_DONTWAIT|MSG_NOSIGNAL)>0){}
  assert(errno==EAGAIN);
  alarm(2);
  check("full-queue-cannot-block-the-toolkit-thread",!native_auxiliary_token_publish(42,123,token,NULL));
  alarm(0);close(pair[1]);
  check("closed-service-cannot-raise-sigpipe",!native_auxiliary_token_publish(42,123,token,NULL));
  close(channel);channel=-1;
  check("missing-service-is-explicitly-unavailable",!native_auxiliary_token_publish(42,123,token,NULL));
  printf("{\"passed\":%u,\"api_bytes\":%zu}\n",checks,sizeof(NXSNativeUIAPI));return 0;
}
