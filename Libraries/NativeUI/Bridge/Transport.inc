/* Shared Linux native UI transport; no toolkit or widget implementation.
 * Included after Protocol.h and the consumer log function. GPL-2.0-or-later. */
#include <errno.h>
#include <pthread.h>
#include <poll.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/un.h>
#include <unistd.h>
struct Shared {pthread_mutex_t mutex;uint32_t sequence;_Atomic uint32_t next_process;};
static struct Shared *shared;
static pid_t observed_pid;
static uint32_t process_cookie;
static int channel=-1;
static __thread unsigned char *packet;
static __thread size_t packet_capacity;
static int native_edit_channel=-1;
static _Atomic pid_t native_edit_pid;
static __thread int native_edit_owner_thread;
static int (*native_edit_handler)(const struct NXSNativeTextEdit *,const char *,const char *);
static int (*native_command_handler)(const struct NXSNativeCommand *,const char *);
static pid_t native_command_pid;
static int (*native_menu_handler)(const struct NXSNativeMenuCommand *);
static pid_t native_menu_pid;
static uint64_t native_callback_generation;
static __thread uint32_t native_request_sequence;
/* Invalidation workers share this process and request socket, but application
 * models and their native command/edit callbacks belong to the registering UI
 * thread. Workers must leave callback packets queued for that owner. */
static int native_callback_owner(void) {
  return native_edit_owner_thread&&native_edit_pid==getpid();
}
static int dispatch_native_edit(int *owns_mutex) {
  uint64_t generation=native_callback_generation;
  size_t capacity=sizeof(struct NXSNativeTextEdit)+65536+256;
  unsigned char *data=malloc(capacity+2);if(!data)return 0;
  ssize_t bytes=recv(native_edit_channel,data,capacity,MSG_DONTWAIT|MSG_TRUNC);
  if(bytes<8||(size_t)bytes>capacity){free(data);return 0;}
  int is_menu=*(uint32_t *)data==NXS_NATIVE_MENU_COMMAND_MAGIC;
  int is_command=*(uint32_t *)data==NXS_NATIVE_COMMAND_MAGIC;
  struct NXSNativeTextEdit edit={0};struct NXSNativeCommand action={0};
  struct NXSNativeMenuCommand menu={0};
  char *text=NULL,*command=NULL;uint64_t serial;uint32_t magic;
  if(is_menu) {
    if(bytes!=sizeof(menu)){free(data);return 0;}
    memcpy(&menu,data,sizeof(menu));
    if(menu.size!=sizeof(menu)||menu.phase>1){free(data);return 0;}
    serial=menu.serial;magic=menu.magic;
  } else if(is_command) {
    if(bytes<(ssize_t)sizeof(action)){free(data);return 0;}
    memcpy(&action,data,sizeof(action));
    if(action.size!=bytes||!action.command_size||action.command_size>256||action.phase>1||
       action.size!=sizeof(action)+action.command_size||memchr(data+sizeof(action),0,action.command_size)){free(data);return 0;}
    command=(char *)(data+sizeof(action));command[action.command_size]=0;serial=action.serial;magic=action.magic;
  } else {
    if(bytes<(ssize_t)sizeof(edit)){free(data);return 0;}
    memcpy(&edit,data,sizeof(edit));
    if(edit.magic!=NXS_NATIVE_TEXT_EDIT_MAGIC||edit.size!=bytes||edit.text_size>65536||edit.command_size>256||
       edit.size!=sizeof(edit)+(size_t)edit.text_size+edit.command_size||
       memchr(data+sizeof(edit),0,edit.text_size+edit.command_size)){free(data);return 0;}
    text=(char *)(data+sizeof(edit));command=text+edit.text_size+1;
    memmove(command,text+edit.text_size,edit.command_size);text[edit.text_size]=0;command[edit.command_size]=0;
    serial=edit.serial;magic=edit.magic;
  }
  /* The separately owned proposal survives nested requests and their borrowed
   * response buffers while the engine runs its normal edit transaction. */
  /* The helper withholds the outer key reply until this decision. Let engine
   * callbacks issue normal RPCs, including from another renderer, while the
   * proposal lives in its separate buffer. Reacquire before sending a decision
   * so no other request can consume the outer reply. */
  uint32_t outer_sequence=native_request_sequence;
  if(is_menu) {
    struct NXSNativeMenuAck ack={NXS_NATIVE_MENU_ACK_MAGIC,outer_sequence,serial};
    if(send(native_edit_channel,&ack,sizeof(ack),MSG_NOSIGNAL|MSG_DONTWAIT)!=sizeof(ack)){free(data);return 0;}
  }
  if(*owns_mutex){pthread_mutex_unlock(&shared->mutex);*owns_mutex=0;}
  int accepted=is_menu?(native_menu_handler?native_menu_handler(&menu):0):
    is_command?(native_command_handler?native_command_handler(&action,command):-1):
    (native_edit_handler?!!native_edit_handler(&edit,text,edit.command_size?command:NULL):0);
  if(accepted<(is_command?-1:0)||accepted>1)accepted=0;
  int locked=pthread_mutex_lock(&shared->mutex);
  if(locked==EOWNERDEAD)pthread_mutex_consistent(&shared->mutex);
  else if(locked){free(data);return 0;}
  *owns_mutex=1;
  struct NXSNativeCommandDecision decision={magic,accepted,serial};
  free(data);
  /* An application command can remove/re-register its endpoint. Its old
   * decision must never be sent to a replacement socket, even after fd reuse. */
  int accepted_reply=generation==native_callback_generation&&
    send(native_edit_channel,&decision,sizeof(decision),MSG_NOSIGNAL|MSG_DONTWAIT)==sizeof(decision);
  if(is_menu&&outer_sequence) {
    struct NXSControlRequest resume={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=31,.process=menu.process,.control=serial};
    if(send(channel,&resume,sizeof(resume),MSG_NOSIGNAL|MSG_DONTWAIT)!=sizeof(resume))return 0;
  }
  return generation!=native_callback_generation||accepted_reply;
}
/* A worker can hold the shared request lock while the helper waits for an
 * idle menu acknowledgment. An owner entering another RPC must service its
 * callback endpoint before blocking on that worker's lock. */
static int native_request_lock(void) {
  for(;;) {
    int locked=pthread_mutex_trylock(&shared->mutex);
    if(locked!=EBUSY)return locked;
    if(!native_callback_owner()||native_edit_channel<0)return pthread_mutex_lock(&shared->mutex);
    struct pollfd ready={.fd=native_edit_channel,.events=POLLIN};
    int result;do result=poll(&ready,1,5);while(result<0&&errno==EINTR);
    if(result<0)return errno;
    if(result>0) {
      int owns_mutex=0;
      if(!dispatch_native_edit(&owns_mutex)) {
        close(native_edit_channel);native_edit_channel=-1;native_command_pid=0;native_menu_pid=0;
      }
      if(owns_mutex)return 0;
    }
  }
}
/* Renderer PID namespaces may all report PID 1. Allocate a transport identity
 * after each fork rather than using that namespace-local PID as the key. */
static uint32_t identity(void) {
  pid_t pid=getpid();
  if(!process_cookie||pid!=observed_pid) {
    if(native_edit_channel>=0&&pid!=native_edit_pid){close(native_edit_channel);native_edit_channel=-1;native_command_pid=0;native_command_handler=NULL;native_menu_pid=0;native_menu_handler=NULL;}
    int locked=pthread_mutex_lock(&shared->mutex);
    if(locked==EOWNERDEAD)pthread_mutex_consistent(&shared->mutex);
    else if(locked)return 0;
    if(!process_cookie||pid!=observed_pid){process_cookie=atomic_fetch_add(&shared->next_process,1)+1;observed_pid=pid;}
    pthread_mutex_unlock(&shared->mutex);
  }
  return process_cookie;
}

static struct NXSResponse *exchange_bytes_descriptor(void *request,size_t request_size,int descriptor_to_send) {
  if(channel<0||!shared)return NULL;
  if(!packet){packet_capacity=1024*1024;packet=malloc(packet_capacity);}
  if(!packet)return NULL;
  int locked=native_request_lock();
  if(locked==EOWNERDEAD)pthread_mutex_consistent(&shared->mutex);
  else if(locked)return NULL;
  int owns_mutex=1;
  uint32_t magic=*(const uint32_t *)request,sequence=++shared->sequence;
  uint32_t previous_sequence=native_request_sequence;native_request_sequence=sequence;
  memcpy((char *)request+28,&sequence,4);
  ssize_t bytes;
  if(descriptor_to_send>=0) {
    struct iovec buffer={.iov_base=request,.iov_len=request_size};
    char ancillary[CMSG_SPACE(sizeof(int))];memset(ancillary,0,sizeof(ancillary));
    struct msghdr message={.msg_iov=&buffer,.msg_iovlen=1,.msg_control=ancillary,.msg_controllen=sizeof(ancillary)};
    struct cmsghdr *control=CMSG_FIRSTHDR(&message);
    control->cmsg_level=SOL_SOCKET;control->cmsg_type=SCM_RIGHTS;control->cmsg_len=CMSG_LEN(sizeof(int));
    memcpy(CMSG_DATA(control),&descriptor_to_send,sizeof(int));
    bytes=sendmsg(channel,&message,MSG_NOSIGNAL);
  } else bytes=send(channel,request,request_size,MSG_NOSIGNAL);
  struct NXSResponse *response=(struct NXSResponse *)packet;
  if(bytes==(ssize_t)request_size) {
    for(;;) {
      if(native_callback_owner()&&native_edit_channel>=0) {
        struct pollfd ready[2]={{channel,POLLIN,0},{native_edit_channel,POLLIN,0}};
        int result;do result=poll(ready,2,2000);while(result<0&&errno==EINTR);
        if(result<=0){bytes=-1;break;}
        /* A completed RPC precedes a later idle menu callback. Consume its
         * already-queued reply first; callback acknowledgments protect replies
         * which the helper has not sent yet. */
        if(ready[1].revents&&!(ready[0].revents&POLLIN)) {
          if(!dispatch_native_edit(&owns_mutex)){close(native_edit_channel);native_edit_channel=-1;native_command_pid=0;}
          if(!owns_mutex){bytes=-1;break;}
          continue;
        }
      }
      struct iovec buffer={.iov_base=packet,.iov_len=packet_capacity};
      char ancillary[CMSG_SPACE(sizeof(int)*4)];
      struct msghdr message={.msg_iov=&buffer,.msg_iovlen=1,.msg_control=ancillary,.msg_controllen=sizeof(ancillary)};
      bytes=recvmsg(channel,&message,MSG_CMSG_CLOEXEC);
      if(bytes<0&&errno==EINTR)continue;
      int descriptor=-1;
      for(struct cmsghdr *c=CMSG_FIRSTHDR(&message);bytes>=0&&c;c=CMSG_NXTHDR(&message,c)) {
        if(c->cmsg_level!=SOL_SOCKET||c->cmsg_type!=SCM_RIGHTS)continue;
        size_t count=(c->cmsg_len-CMSG_LEN(0))/sizeof(int);int *fds=(int *)CMSG_DATA(c);
        for(size_t i=0;i<count;i++){if(descriptor<0)descriptor=fds[i];else close(fds[i]);}
      }
      response=(struct NXSResponse *)packet;
      if(bytes<(ssize_t)sizeof(*response)||(message.msg_flags&(MSG_TRUNC|MSG_CTRUNC))) {
        if(descriptor>=0)close(descriptor);bytes=-1;break;
      }
      if((uint32_t)response->reserved!=sequence){if(descriptor>=0)close(descriptor);continue;}
      if(descriptor>=0) {
        struct stat metadata;
        size_t pixels=response->size>=sizeof(*response)?response->size-sizeof(*response):0;
        int valid=bytes==(ssize_t)sizeof(*response)&&pixels<=32*1024*1024&&pixels>0&&
          !fstat(descriptor,&metadata)&&(uint64_t)metadata.st_size==pixels;
        void *mapped=valid?mmap(NULL,pixels,PROT_READ,MAP_SHARED,descriptor,0):MAP_FAILED;
        close(descriptor);
        if(mapped==MAP_FAILED){bytes=-1;break;}
        if(response->size>packet_capacity) {
          size_t capacity=response->size;unsigned char *larger=realloc(packet,capacity);
          if(!larger){munmap(mapped,pixels);bytes=-1;break;}
          packet=larger;packet_capacity=capacity;response=(struct NXSResponse *)packet;
        }
        memcpy(response+1,mapped,pixels);munmap(mapped,pixels);bytes=response->size;
      }
      break;
    }
  }
  if(owns_mutex)pthread_mutex_unlock(&shared->mutex);
  native_request_sequence=previous_sequence;
  if(bytes<(ssize_t)sizeof(*response)||response->magic!=magic||response->size!=bytes)return NULL;
  return response;
}
static struct NXSResponse *exchange_bytes(void *request,size_t request_size)
{return exchange_bytes_descriptor(request,request_size,-1);}
/* An owner-loop wake may have no outstanding RPC. Drain the same callback
 * channel on its UI owner, preserving nested RPC and reply locking rules. */
static int __attribute__((unused)) native_callbacks_dispatch(void) {
  if(!shared||!native_callback_owner()||native_edit_channel<0)return 0;
  /* Receive/acknowledge before taking the shared request lock. A worker may
   * own it while waiting for a reply which the callback handshake will allow
   * the helper to service. Only this UI thread reads the callback endpoint. */
  int owns_mutex=0,count=0;
  while(native_edit_channel>=0) {
    struct pollfd ready={.fd=native_edit_channel,.events=POLLIN};
    int result;do result=poll(&ready,1,0);while(result<0&&errno==EINTR);
    if(result<=0)break;
    if(!dispatch_native_edit(&owns_mutex)) {
      close(native_edit_channel);native_edit_channel=-1;native_command_pid=0;native_menu_pid=0;break;
    }
    count++;if(!owns_mutex)break;
  }
  if(owns_mutex)pthread_mutex_unlock(&shared->mutex);
  return count;
}
static struct NXSResponse *exchange(struct NXSRequest req){return exchange_bytes(&req,sizeof(req));}
static struct NXSResponse * __attribute__((unused)) native_pointer_press(int kind,uint64_t control,double x,double y,unsigned modifiers,unsigned clicks) {
  if(!clicks||clicks>INT32_MAX)return NULL;
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=22,
    .process=identity(),.kind=kind,.control=control,.x=x,.y=y,.modifiers=modifiers,.state=(int32_t)clicks};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
  return response&&response->parts[3].x==1?response:NULL;
}

static int bridge_connect(const char *socket_path) {
  if(!socket_path||strlen(socket_path)>=sizeof(((struct sockaddr_un *)0)->sun_path))return 0;
  channel=socket(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC,0);struct sockaddr_un address={.sun_family=AF_UNIX};strcpy(address.sun_path,socket_path);
  if(channel<0||connect(channel,(void *)&address,sizeof(address))){note("native helper unavailable; unchanged");if(channel>=0)close(channel);channel=-1;return 0;}
  struct timeval timeout={.tv_sec=2};setsockopt(channel,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof(timeout));
  shared=mmap(NULL,sizeof(*shared),PROT_READ|PROT_WRITE,MAP_SHARED|MAP_ANONYMOUS,-1,0);
  if(shared==MAP_FAILED){shared=NULL;close(channel);channel=-1;return 0;}
  pthread_mutexattr_t attr;pthread_mutexattr_init(&attr);pthread_mutexattr_setpshared(&attr,PTHREAD_PROCESS_SHARED);pthread_mutexattr_setrobust(&attr,PTHREAD_MUTEX_ROBUST);pthread_mutex_init(&shared->mutex,&attr);pthread_mutexattr_destroy(&attr);
  observed_pid=getpid();process_cookie=0;
  uint32_t seed;
  if(!getentropy(&seed,sizeof(seed)))atomic_store(&shared->next_process,seed);
  return 1;
}

static int __attribute__((unused)) native_text_filter_register(int (*handler)(const struct NXSNativeTextEdit *,const char *,const char *)) {
  uint32_t process=identity();if(!process||!handler)return 0;
  if(native_edit_pid==getpid()&&!native_callback_owner())return 0;
  if(native_edit_channel>=0&&native_edit_pid==getpid()) {
    native_edit_handler=handler;return 1;
  }
  int endpoints[2];if(socketpair(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC,0,endpoints))return 0;
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=19,.process=process};
  struct NXSResponse *response=exchange_bytes_descriptor(&request,sizeof(request),endpoints[1]);
  close(endpoints[1]);
  if(!response||response->parts[3].x!=1){close(endpoints[0]);return 0;}
  native_edit_handler=handler;native_command_pid=0;native_menu_pid=0;native_edit_channel=endpoints[0];
  native_callback_generation++;
  native_edit_owner_thread=1;native_edit_pid=getpid();return 1;
}
static int __attribute__((unused)) native_text_filter_unregister(void) {
  uint32_t process=identity();if(!native_callback_owner())return 0;
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=20,.process=process};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
  int accepted=response&&response->parts[3].x==1;
  if(native_edit_channel>=0)close(native_edit_channel);
  native_edit_channel=-1;native_edit_handler=NULL;native_command_pid=0;native_command_handler=NULL;
  native_menu_pid=0;native_menu_handler=NULL;
  native_callback_generation++;
  native_edit_owner_thread=0;native_edit_pid=0;return accepted;
}
static int __attribute__((unused)) native_command_filter_register(int (*handler)(const struct NXSNativeCommand *,const char *)) {
  uint32_t process=identity();if(!handler||!native_callback_owner()||native_edit_channel<0)return 0;
  if(native_command_pid==getpid()){native_command_handler=handler;return 1;}
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=23,.process=process,.state=1};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
  if(!response||response->parts[3].x!=1)return 0;
  native_command_handler=handler;native_command_pid=getpid();return 1;
}
static int native_menu_reject_edit(const struct NXSNativeTextEdit *edit,const char *text,const char *command)
{(void)edit;(void)text;(void)command;return 0;}
static int __attribute__((unused)) native_menu_filter_register(int (*handler)(const struct NXSNativeMenuCommand *)) {
  uint32_t process=identity();if(!handler)return 0;
  if(native_edit_channel<0||native_edit_pid!=getpid()) {
    if(!native_text_filter_register(native_menu_reject_edit))return 0;
  }
  if(!native_callback_owner())return 0;
  if(native_menu_pid==getpid()){native_menu_handler=handler;return 1;}
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=24,.process=process,.state=1};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
  if(!response||response->parts[3].x!=1)return 0;
  native_menu_handler=handler;native_menu_pid=getpid();return 1;
}
