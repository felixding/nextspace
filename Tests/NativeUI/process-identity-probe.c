/* Forked PID namespaces may report the same getpid(). Exercise the real
 * shared transport through raw clone(), which bypasses pthread_atfork.
 * GPL-2.0-or-later. */
#define _GNU_SOURCE
#include "NativeUI.h"
#include "Bridge/Protocol.h"
#include <assert.h>
#include <stdio.h>
#include <signal.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>
static void note(const char *message) {(void)message;}
static pid_t namespace_pid(void) {return 1;}
#define getpid namespace_pid
#include "Bridge/Transport.inc"
#undef getpid
struct Result {uint32_t cookie;int stable,detached;};
static void *worker(void *value) {*(uint32_t *)value=identity();return NULL;}
int main(void)
{
 struct rlimit limit={0};assert(!setrlimit(RLIMIT_CORE,&limit));
 char folder[]="/tmp/nxs-process-identity-XXXXXX";assert(mkdtemp(folder));
 struct sockaddr_un address={.sun_family=AF_UNIX};
 assert(snprintf(address.sun_path,sizeof(address.sun_path),"%s/native.sock",folder)>0);
 int server=socket(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC,0);assert(server>=0);
 assert(!bind(server,(void *)&address,sizeof(address))&&!listen(server,4));
 assert(bridge_connect(address.sun_path));uint32_t parent=identity();assert(parent);
 int callbacks[2];assert(!socketpair(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC,0,callbacks));
 native_edit_channel=callbacks[0];native_edit_pid=1;native_edit_owner_thread=1;
 native_command_pid=1;native_menu_pid=1;
 struct Result results[2];
 for(unsigned i=0;i<2;i++) {
  int report[2];assert(!pipe(report));
  pid_t child=syscall(SYS_clone,(unsigned long)SIGCHLD,0,0,0,0);assert(child>=0);
  if(!child) {
   close(report[0]);uint32_t value=identity();
   struct Result r={value,value==identity(),native_edit_channel<0&&!native_edit_pid&&
     !native_edit_owner_thread&&!native_command_pid&&!native_menu_pid};
   assert(write(report[1],&r,sizeof(r))==sizeof(r));_exit(0);
  }
  close(report[1]);assert(read(report[0],&results[i],sizeof(results[i]))==sizeof(results[i]));close(report[0]);
  int status;assert(waitpid(child,&status,0)==child&&WIFEXITED(status)&&!WEXITSTATUS(status));
 }
 uint32_t thread_cookie;pthread_t thread;assert(!pthread_create(&thread,NULL,worker,&thread_cookie));
 assert(!pthread_join(thread,NULL));
 int unique=results[0].cookie&&results[1].cookie&&results[0].cookie!=parent&&
   results[1].cookie!=parent&&results[0].cookie!=results[1].cookie;
 int intact=identity()==parent&&thread_cookie==parent&&native_callback_owner()&&native_edit_channel==callbacks[0];
 close(callbacks[0]);close(callbacks[1]);close(channel);close(server);unlink(address.sun_path);rmdir(folder);
 printf("{\"distinct_raw_clone_identities\":%s,\"stable_parent_and_threads\":%s,\"child_callbacks_detached\":%s}\n",
   unique?"true":"false",intact?"true":"false",results[0].detached&&results[1].detached?"true":"false");fflush(stdout);
 assert(unique&&intact&&results[0].stable&&results[1].stable&&results[0].detached&&results[1].detached);
 return 0;
}
