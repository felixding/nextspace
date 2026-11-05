/* Exercise reentrant pre-edit IPC through the browser's shared C transport.
 * GPL-2.0-or-later. */
#define _GNU_SOURCE
#include "NativeUI.h"
#include "Bridge/Protocol.h"
#include <assert.h>
#include <stdio.h>
#include <sys/eventfd.h>
#include <sys/wait.h>
#include <time.h>
static void note(const char *message){fprintf(stderr,"%s\n",message);}
#include "Bridge/Transport.inc"
_Static_assert(sizeof(struct NXSNativeTextEdit)==72,"Text proposal wire ABI");
_Static_assert(sizeof(struct NXSNativeTextDecision)==16,"Text decision wire ABI");
static int proposals,allow,destroy_on_edit,delay_decision;
static const char *expected_value,*expected_text,*expected_command;
static uint64_t expected_start,expected_length;
static struct NXSResponse *request(unsigned operation)
{
  struct NXSControlRequest req={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=operation,.process=identity(),
    .kind=NXS_TEXTFIELD,.control=1,.width=180,.height=24,.enabled=1,.maximum=1};
  struct NXSResponse *r=exchange_bytes(&req,sizeof(req));assert(r);return r;
}
static void value(const char *expected)
{
  struct NXSResponse *r=request(18);assert(r->parts[3].x==1);
  assert(r->size>=sizeof(*r)+sizeof(struct NXSTextResponse));
  struct NXSTextResponse *s=(void *)(r+1);
  assert(s->text_size==strlen(expected)&&r->size==sizeof(*r)+sizeof(*s)+s->text_size);
  assert(!memcmp(s+1,expected,s->text_size));
}
static int model(const char *text,uint64_t start,uint64_t length)
{
  size_t size=sizeof(struct NXSControlTextRequest)+strlen(text);
  struct NXSControlTextRequest *req=calloc(1,size);assert(req);
  *req=(struct NXSControlTextRequest){.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=17,.process=identity(),
    .kind=NXS_TEXTFIELD,.control=1,.text_size=strlen(text),.selection_start=start,.selection_length=length,.editable=1};
  memcpy(req+1,text,strlen(text));struct NXSResponse *r=exchange_bytes(req,size);free(req);assert(r);return r->parts[3].x==1;
}
static int filter(const struct NXSNativeTextEdit *edit,const char *text,const char *command)
{
  proposals++;
  assert(edit->process==identity()&&edit->control==1&&edit->kind==NXS_TEXTFIELD);
  assert(edit->range_start==expected_start&&edit->range_length==expected_length);
  assert(!strcmp(text,expected_text));
  assert(expected_command?(command&&!strcmp(command,expected_command)):!command);
  value(expected_value); /* Nested RPC while the outer native key is pending. */
  if(proposals==1) {
    pid_t child=fork();assert(child>=0);
    if(!child){assert(request(9)->parts[4].width==1);_exit(0);}
    int status;assert(waitpid(child,&status,0)==child&&WIFEXITED(status)&&WEXITSTATUS(status)==0);
  }
  assert(!model("Reentrant",0,0));
  value(expected_value);
  if(destroy_on_edit)assert(request(6)->parts[0].y==1);
  if(delay_decision){struct timespec delay={.tv_sec=2,.tv_nsec=200000000};nanosleep(&delay,NULL);}
  return allow;
}
static void key(unsigned logical,const char *text)
{
  size_t length=text?strlen(text):0,size=sizeof(struct NXSControlInputRequest)+2*length;
  struct NXSControlInputRequest *req=calloc(1,size);assert(req);
  *req=(struct NXSControlInputRequest){.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=8,.process=identity(),
    .kind=NXS_TEXTFIELD,.control=1,.text_size=length,.unmodified_size=length,.key=logical};
  if(length){memcpy(req+1,text,length);memcpy((char *)(req+1)+length,text,length);}
  struct NXSResponse *r=exchange_bytes(req,size);free(req);assert(r&&r->parts[3].x==NXS_INPUT_HANDLED);
}
static void idle_cpu(pid_t helper)
{
  clockid_t clock;struct timespec a,b,pause={.tv_nsec=250000000};assert(!clock_getcpuclockid(helper,&clock));
  assert(!clock_gettime(clock,&a));nanosleep(&pause,NULL);assert(!clock_gettime(clock,&b));
  double cpu=(b.tv_sec-a.tv_sec)+(b.tv_nsec-a.tv_nsec)/1e9;assert(cpu<.1);
}
int main(int argc,char **argv)
{
  assert(argc>=3&&bridge_connect(argv[1]));pid_t helper=atoi(argv[2]);assert(helper>0);
  int notifier=eventfd(0,EFD_CLOEXEC|EFD_NONBLOCK);assert(notifier>=0);
  struct NXSControlRequest owner={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=15,.process=identity()};
  struct NXSResponse *r=exchange_bytes_descriptor(&owner,sizeof(owner),notifier);assert(r&&r->parts[3].x==1);
  assert(native_text_filter_register(filter));
  r=request(1);assert(r->width==180&&r->height==24);
  assert(model("Hello",1,2));
  struct NXSControlInputRequest focus={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=7,.process=identity(),
    .kind=NXS_TEXTFIELD,.control=1,.focused=1};
  r=exchange_bytes(&focus,sizeof(focus));assert(r&&r->parts[3].x==1);
  expected_value="Hello";expected_start=1;expected_length=2;expected_text="X";
  key(NXS_KEY_TEXT,"X");value("Hello");assert(proposals==1&&request(5)->parts[2].width==0);
  allow=1;key(NXS_KEY_TEXT,"X");value("HXlo");assert(proposals==2&&request(5)->parts[2].width==1);
  expected_value="HXlo";expected_start=1;expected_length=1;expected_text="";expected_command="deleteBackward:";
  allow=0;key(NXS_KEY_BACKSPACE,NULL);value("HXlo");assert(proposals==3&&request(5)->parts[2].width==1);
  allow=1;key(NXS_KEY_BACKSPACE,NULL);value("Hlo");assert(proposals==4&&request(5)->parts[2].width==2);
  /* Losing the callback peer vetoes edits and stops its EOF from spinning the
   * native loop. Explicit unregister restores ordinary native editor use. */
  close(native_edit_channel);native_edit_channel=-1;
  key(NXS_KEY_TEXT,"Z");value("Hlo");assert(request(5)->parts[2].width==2);
  assert(native_text_filter_unregister());
  key(NXS_KEY_TEXT,"X");value("HXlo");assert(proposals==4&&request(5)->parts[2].width==3);
  assert(native_text_filter_register(filter));
  expected_value="HXlo";expected_start=2;expected_length=0;expected_text="Z";expected_command=NULL;
  allow=1;delay_decision=1;key(NXS_KEY_TEXT,"Z");value("HXlo");assert(proposals==5);
  idle_cpu(helper);assert(native_text_filter_unregister());
  assert(native_text_filter_register(filter));delay_decision=0;
  destroy_on_edit=1;key(NXS_KEY_TEXT,"Z");assert(proposals==6&&request(18)->parts[3].x==0);
  idle_cpu(helper);
  assert(native_text_filter_unregister());
  owner.operation=16;r=exchange_bytes(&owner,sizeof(owner));assert(r&&r->parts[3].x==1);
  close(notifier);close(channel);
  puts("{\"native_pre_edit_ipc\":true,\"proposals\":6,\"nested_reads\":12,\"nested_mutations_rejected\":6,\"other_process_request_during_validation\":true,\"cancelled_typing_and_deletion\":true,\"accepted_typing_and_deletion\":true,\"callback_peer_loss_veto\":true,\"expired_decision_veto\":true,\"destroy_during_validation\":true,\"idle_after_expiry_and_destroy\":true,\"explicit_unregister\":true}");
}
