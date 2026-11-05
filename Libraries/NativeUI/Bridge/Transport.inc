/* Shared Linux native UI transport; no toolkit or widget implementation.
 * Included after Protocol.h and the consumer log function. GPL-2.0-or-later. */
#include <errno.h>
#include <pthread.h>
#include <poll.h>
#include <stdatomic.h>
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
static pid_t native_edit_pid;
static int (*native_edit_handler)(const struct NXSNativeTextEdit *,const char *,const char *);
static int dispatch_native_edit(int *owns_mutex) {
  size_t capacity=sizeof(struct NXSNativeTextEdit)+65536+256;
  unsigned char *data=malloc(capacity+2);if(!data)return 0;
  ssize_t bytes=recv(native_edit_channel,data,capacity,MSG_DONTWAIT|MSG_TRUNC);
  if(bytes<(ssize_t)sizeof(struct NXSNativeTextEdit)||(size_t)bytes>capacity){free(data);return 0;}
  struct NXSNativeTextEdit edit;memcpy(&edit,data,sizeof(edit));
  if(edit.magic!=NXS_NATIVE_TEXT_EDIT_MAGIC||edit.size!=bytes||edit.text_size>65536||edit.command_size>256||
     edit.size!=sizeof(edit)+(size_t)edit.text_size+edit.command_size||
     memchr(data+sizeof(edit),0,edit.text_size+edit.command_size)){free(data);return 0;}
  char *text=(char *)(data+sizeof(edit)),*command=text+edit.text_size+1;
  memmove(command,text+edit.text_size,edit.command_size);text[edit.text_size]=0;command[edit.command_size]=0;
  /* The separately owned proposal survives nested requests and their borrowed
   * response buffers while the engine runs its normal edit transaction. */
  /* The helper withholds the outer key reply until this decision. Let engine
   * callbacks issue normal RPCs, including from another renderer, while the
   * proposal lives in its separate buffer. Reacquire before sending a decision
   * so no other request can consume the outer reply. */
  pthread_mutex_unlock(&shared->mutex);*owns_mutex=0;
  int accepted=native_edit_handler?!!native_edit_handler(&edit,text,edit.command_size?command:NULL):0;
  int locked=pthread_mutex_lock(&shared->mutex);
  if(locked==EOWNERDEAD)pthread_mutex_consistent(&shared->mutex);
  else if(locked){free(data);return 0;}
  *owns_mutex=1;
  struct NXSNativeTextDecision decision={NXS_NATIVE_TEXT_EDIT_MAGIC,accepted,edit.serial};
  free(data);
  return send(native_edit_channel,&decision,sizeof(decision),MSG_NOSIGNAL|MSG_DONTWAIT)==sizeof(decision);
}
/* Renderer PID namespaces may all report PID 1. Allocate a transport identity
 * after each fork rather than using that namespace-local PID as the key. */
static uint32_t identity(void) {
  pid_t pid=getpid();
  if(!process_cookie||pid!=observed_pid) {
    if(native_edit_channel>=0&&pid!=native_edit_pid){close(native_edit_channel);native_edit_channel=-1;}
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
  int locked=pthread_mutex_lock(&shared->mutex);
  if(locked==EOWNERDEAD)pthread_mutex_consistent(&shared->mutex);
  else if(locked)return NULL;
  int owns_mutex=1;
  uint32_t magic=*(const uint32_t *)request,sequence=++shared->sequence;
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
      if(native_edit_channel>=0&&native_edit_pid==getpid()) {
        struct pollfd ready[2]={{channel,POLLIN,0},{native_edit_channel,POLLIN,0}};
        int result;do result=poll(ready,2,2000);while(result<0&&errno==EINTR);
        if(result<=0){bytes=-1;break;}
        if(ready[1].revents) {
          if(!dispatch_native_edit(&owns_mutex)){close(native_edit_channel);native_edit_channel=-1;}
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
  if(bytes<(ssize_t)sizeof(*response)||response->magic!=magic||response->size!=bytes)return NULL;
  return response;
}
static struct NXSResponse *exchange_bytes(void *request,size_t request_size)
{return exchange_bytes_descriptor(request,request_size,-1);}
static struct NXSResponse *exchange(struct NXSRequest req){return exchange_bytes(&req,sizeof(req));}

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
  if(native_edit_channel>=0&&native_edit_pid==getpid()){native_edit_handler=handler;return 1;}
  int endpoints[2];if(socketpair(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC,0,endpoints))return 0;
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=19,.process=process};
  struct NXSResponse *response=exchange_bytes_descriptor(&request,sizeof(request),endpoints[1]);
  close(endpoints[1]);
  if(!response||response->parts[3].x!=1){close(endpoints[0]);return 0;}
  native_edit_channel=endpoints[0];native_edit_pid=getpid();native_edit_handler=handler;return 1;
}
static int __attribute__((unused)) native_text_filter_unregister(void) {
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=20,.process=identity()};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
  int accepted=response&&response->parts[3].x==1;
  if(native_edit_channel>=0)close(native_edit_channel);
  native_edit_channel=-1;native_edit_handler=NULL;return accepted;
}
