/* Exercise real native menu RPC and UI-owner callbacks without a GUI toolkit.
 * Fixture model data is application-owned; UI behavior stays in NativeUI. */
#define _GNU_SOURCE
#include "NativeUI.h"
#include "Bridge/Protocol.h"
#include <assert.h>
#include <stdio.h>
#include <stddef.h>
#include <limits.h>
#include <sys/eventfd.h>
#include <sched.h>
static void note(const char *text){(void)text;}
#include "Bridge/Transport.inc"
static int wake_fd,allow=1,actions,queries,idle_callbacks,rpc_depth,slow,paused;
static uint64_t last;
static pthread_t owner;
static void *worker_request(void *unused) {
  (void)unused;
  struct NXSControlRequest req={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=28,.process=identity(),.control=1,.state=-1};
  struct NXSResponse *reply=exchange_bytes(&req,sizeof(req));assert(reply&&reply->parts[3].x==1);
  return NULL;
}
static struct NXSResponse *request(unsigned op,int state) {
  struct NXSControlRequest req={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=op,.process=identity(),.control=1,.state=state};
  rpc_depth++;struct NXSResponse *response=exchange_bytes(&req,sizeof(req));rpc_depth--;return response;
}
static int menu_command(const struct NXSNativeMenuCommand *command) {
  assert(command->process==identity()&&command->control==1&&command->command>=1&&command->command<=4);
  assert(pthread_equal(owner,pthread_self()));
  int idle=!rpc_depth;idle_callbacks+=idle;
  struct NXSResponse *read=request(28,-1);assert(read&&read->parts[3].x==1&&read->parts[0].y==1);
  struct NXSResponse *mutation=request(26,0);assert(mutation&&mutation->parts[3].x==0);
  if(command->phase==NXS_COMMAND_VALIDATE)queries++;
  else {actions++;last=command->command;}
  printf("{\"event\":\"menu-command\",\"command\":%llu,\"phase\":%u,\"idle\":%d}\n",(unsigned long long)command->command,command->phase,idle);
  if(slow&&idle){struct timespec delay={.tv_sec=2,.tv_nsec=200000000};nanosleep(&delay,NULL);}
  if(command->phase==NXS_COMMAND_EXECUTE&&command->command==3)assert(request(29,0)->parts[3].x==1);
  if(command->phase==NXS_COMMAND_EXECUTE&&command->command==4) {
    assert(native_text_filter_unregister());assert(native_menu_filter_register(menu_command));
    puts("{\"event\":\"endpoint-replaced\"}");
  }
  return allow;
}
static void model(int bad) {
  const char title[]="IPC menu fixture";
  const char *labels[]={"Edit","Undo","Direct","Remove menu","Replace endpoint"},*keys[]={"","z","d","r","e"};
  const int parents[]={-1,0,-1,-1,-1};const uint64_t commands[]={0,1,2,3,4};
  unsigned char bytes[1024] __attribute__((aligned(8)))={0};size_t used=sizeof(struct NXSMenuModelRequest);
  memcpy(bytes+used,title,strlen(title));used+=strlen(title);
  for(int i=0;i<5;i++) {
    struct NXSMenuWireItem item={.parent=bad==1&&i==4?99:parents[i],.flags=i?0:NXS_MENU_SUBMENU,.command=commands[i],
      .modifiers=i?NXS_MENU_COMMAND:0,.title_size=strlen(labels[i]),.key_size=strlen(keys[i])};
    memcpy(bytes+used,&item,sizeof(item));used+=sizeof(item);
    memcpy(bytes+used,labels[i],item.title_size);used+=item.title_size;
    memcpy(bytes+used,keys[i],item.key_size);used+=item.key_size;
  }
  struct NXSMenuModelRequest *req=(void *)bytes;
  *req=(struct NXSMenuModelRequest){.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=25,.process=identity(),
    .control=1,.text_size=used-sizeof(*req),.count=bad==2?4097:5,.title_size=strlen(title)};
  rpc_depth++;struct NXSResponse *response=exchange_bytes(req,used);rpc_depth--;
  assert(response&&response->parts[3].x==(bad?0:1));
}
int main(int argc,char **argv) {
  assert(argc>=2);owner=pthread_self();setvbuf(stdout,NULL,_IOLBF,0);assert(bridge_connect(argv[1]));
  slow=argc>2&&!strcmp(argv[2],"--expire");
  struct NXSRequest metrics={.magic=NXS_CHROMIUM_MAGIC,.operation=7};
  struct NXSResponse *bootstrap=exchange(metrics);assert(bootstrap&&bootstrap->parts[5].height==1);
  wake_fd=eventfd(0,EFD_NONBLOCK|EFD_CLOEXEC);assert(wake_fd>=0);
  struct NXSControlRequest subscription={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=15,.process=identity()};
  assert(exchange_bytes_descriptor(&subscription,sizeof(subscription),wake_fd)->parts[3].x==1);
  assert(native_menu_filter_register(menu_command));model(0);assert(request(26,1)->parts[3].x==1);
  printf("{\"event\":\"menu-live\",\"pid\":%d,\"process\":%u}\n",getpid(),identity());
  int done=0;
  while(!done) {
    struct pollfd ready[]={{.fd=0,.events=POLLIN},{.fd=paused?-1:wake_fd,.events=POLLIN}};
    int result;do result=poll(ready,2,-1);while(result<0&&errno==EINTR);assert(result>0);
    if(ready[1].revents) {uint64_t count;read(wake_fd,&count,sizeof(count));native_callbacks_dispatch();}
    if(ready[0].revents) {
      char line[64];if(!fgets(line,sizeof(line),stdin)||!strncmp(line,"quit",4)){done=1;continue;}
      if(!strncmp(line,"pause",5))paused=1;
      else if(!strncmp(line,"resume-with-rpc",15))paused=0;
      else if(!strncmp(line,"worker-with-menu",16)) {
        paused=0;pthread_t worker;assert(!pthread_create(&worker,NULL,worker_request,NULL));
        struct timespec start,now;clock_gettime(CLOCK_MONOTONIC,&start);
        for(;;) {
          int result=pthread_mutex_trylock(&shared->mutex);
          if(result==EBUSY)break;
          assert(!result);pthread_mutex_unlock(&shared->mutex);sched_yield();
          clock_gettime(CLOCK_MONOTONIC,&now);assert(now.tv_sec-start.tv_sec<2);
        }
        assert(native_callbacks_dispatch()>0);assert(!pthread_join(worker,NULL));
        puts("{\"event\":\"worker-reply\",\"owner_callbacks\":true}");
      }
      else if(!strncmp(line,"key ",4)) {
        struct {struct NXSControlInputRequest request;char text[2];} packet={
          .request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=27,.process=identity(),.control=1,
            .text_size=1,.unmodified_size=1,.type=NXS_KEY_DOWN,.modifiers=NXS_ALT,.key=NXS_KEY_TEXT}};
        packet.text[0]=packet.text[1]=line[4];rpc_depth++;
        struct NXSResponse *r=exchange_bytes(&packet,sizeof(packet.request)+2);rpc_depth--;
        assert(r&&r->parts[3].x==1);
      } else if(!strncmp(line,"disable",7))allow=0;
      else if(!strncmp(line,"enable",6))allow=1;
      else if(!strncmp(line,"peer-loss",9)) {close(native_edit_channel);native_edit_channel=-1;}
      else if(!strncmp(line,"destroy",7))assert(request(29,0)->parts[3].x==1);
      else if(!strncmp(line,"cancel",6))assert(request(30,0)->parts[3].x==1);
      else if(!strncmp(line,"show",4))assert(request(26,1)->parts[3].x==1);
      else if(!strncmp(line,"model",5))model(0);
      else if(!strncmp(line,"bad-model",9))model(1);
      else if(!strncmp(line,"bad-count",9))model(2);
      int index=-1;sscanf(line,"state %d",&index);
      struct NXSResponse *state=request(28,index);assert(state);
      struct NXSResponse copy=*state;
      printf("{\"event\":\"state\",\"accepted\":%d,\"visible\":%d,\"tracking\":%d,\"enabled\":%d,\"highlighted\":%d,\"actions\":%d,\"idle_callbacks\":%d,\"last\":%llu,\"frame\":[%.3f,%.3f,%.3f,%.3f],\"item\":[%.3f,%.3f,%.3f,%.3f]}\n",
        (int)copy.parts[3].x,(int)copy.parts[3].y,(int)copy.parts[0].y,(int)copy.parts[3].width,(int)copy.parts[3].height,
        actions,idle_callbacks,(unsigned long long)last,copy.parts[1].x,copy.parts[1].y,copy.parts[1].width,copy.parts[1].height,
        copy.parts[2].x,copy.parts[2].y,copy.parts[2].width,copy.parts[2].height);
    }
  }
  native_text_filter_unregister();
  struct NXSControlRequest unsubscribe={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=16,.process=identity()};
  assert(exchange_bytes(&unsubscribe,sizeof(unsubscribe)));close(wake_fd);close(channel);
  printf("{\"event\":\"done\",\"queries\":%d,\"actions\":%d,\"idle_callbacks\":%d}\n",queries,actions,idle_callbacks);return 0;
}
