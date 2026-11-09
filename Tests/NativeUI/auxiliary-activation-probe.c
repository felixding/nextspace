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
  check("publication-does-not-wait-for-a-reply",native_auxiliary_token_publish(42,123,token));
  unsigned char buffer[8192];ssize_t size=recv(pair[1],buffer,sizeof(buffer),MSG_DONTWAIT);
  struct NXSControlRequest *request=(void *)buffer;
  check("publication-is-one-atomic-envelope",size==(ssize_t)(sizeof(*request)+strlen(token))&&
      request->magic==NXS_CHROMIUM_CONTROL_MAGIC&&request->operation==64&&request->process==17&&
      request->control==42&&request->state==1&&request->x==123&&request->reserved==0&&
      !memcmp(buffer+sizeof(*request),token,strlen(token)));
  check("publication-inserts-no-extra-packet",recv(pair[1],buffer,sizeof(buffer),MSG_DONTWAIT)<0&&errno==EAGAIN);
  check("empty-and-unowned-publications-are-rejected",!native_auxiliary_token_publish(0,123,token)&&
      !native_auxiliary_token_publish(42,123,"")&&
      !native_auxiliary_token_publish(42,123,NULL));
  check("toolkit-owned-serial-needs-no-private-metadata",native_auxiliary_token_publish(42,0,token));
  size=recv(pair[1],buffer,sizeof(buffer),MSG_DONTWAIT);
  check("toolkit-token-keeps-serial-unavailable",size==(ssize_t)(sizeof(*request)+strlen(token))&&request->x==0);
  char huge[4098];memset(huge,'a',sizeof(huge)-1);huge[sizeof(huge)-1]=0;
  check("oversize-token-is-rejected",!native_auxiliary_token_publish(42,123,huge));
  int small=4096;assert(!setsockopt(pair[0],SOL_SOCKET,SO_SNDBUF,&small,sizeof(small)));
  while(send(pair[0],buffer,512,MSG_DONTWAIT|MSG_NOSIGNAL)>0){}
  assert(errno==EAGAIN);
  alarm(2);
  check("full-queue-cannot-block-the-toolkit-thread",!native_auxiliary_token_publish(42,123,token));
  alarm(0);close(pair[1]);
  check("closed-service-cannot-raise-sigpipe",!native_auxiliary_token_publish(42,123,token));
  close(channel);channel=-1;
  check("missing-service-is-explicitly-unavailable",!native_auxiliary_token_publish(42,123,token));
  printf("{\"passed\":%u,\"api_bytes\":%zu}\n",checks,sizeof(NXSNativeUIAPI));return 0;
}
