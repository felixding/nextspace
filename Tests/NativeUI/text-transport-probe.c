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
static int transport_kind=NXS_TEXTFIELD;
static int proposals,allow,destroy_on_edit,delay_decision;
static const char *expected_value,*expected_text,*expected_command;
static uint64_t expected_start,expected_length;
static int command_executed,command_queries,command_enabled=1,command_delay,command_destroy;
static int mixed_late_command;
static struct NXSResponse *request(unsigned operation)
{
  struct NXSControlRequest req={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=operation,.process=identity(),
    .kind=transport_kind,.control=1,.width=180,.height=transport_kind==NXS_TEXTAREA?96:24,.enabled=1,.maximum=1};
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
    .kind=transport_kind,.control=1,.text_size=strlen(text),.selection_start=start,.selection_length=length,.editable=1};
  memcpy(req+1,text,strlen(text));struct NXSResponse *r=exchange_bytes(req,size);free(req);assert(r);return r->parts[3].x==1;
}
static int filter(const struct NXSNativeTextEdit *edit,const char *text,const char *command)
{
  proposals++;
  assert(edit->process==identity()&&edit->control==1&&edit->kind==transport_kind);
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
  if(mixed_late_command) {
    struct NXSNativeCommandDecision late={mixed_late_command==2?NXS_NATIVE_MENU_COMMAND_MAGIC:NXS_NATIVE_COMMAND_MAGIC,mixed_late_command==2?1:-1,edit->serial-1};
    assert(send(native_edit_channel,&late,sizeof(late),MSG_NOSIGNAL)==sizeof(late));mixed_late_command=0;
  }
  return allow;
}
static int command_filter(const struct NXSNativeCommand *command,const char *selector)
{
  assert(command->process==identity()&&command->control==1&&command->kind==transport_kind);
  if(strcmp(selector,"paste:"))return -1;
  value("Hello");assert(!model("Reentrant",0,0));
  if(command->phase==NXS_COMMAND_VALIDATE){command_queries++;return command_enabled;}
  assert(command->phase==NXS_COMMAND_EXECUTE);
  if(!command_enabled)return 0;
  command_executed++;
  if(command_destroy)assert(request(6)->parts[0].y==1);
  if(command_delay){struct timespec delay={.tv_sec=2,.tv_nsec=200000000};nanosleep(&delay,NULL);}
  return 1;
}
static void key_with_modifiers(unsigned logical,const char *text,unsigned modifiers)
{
  size_t length=text?strlen(text):0,size=sizeof(struct NXSControlInputRequest)+2*length;
  struct NXSControlInputRequest *req=calloc(1,size);assert(req);
  *req=(struct NXSControlInputRequest){.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=8,.process=identity(),
    .kind=transport_kind,.control=1,.text_size=length,.unmodified_size=length,.key=logical,.modifiers=modifiers};
  if(length){memcpy(req+1,text,length);memcpy((char *)(req+1)+length,text,length);}
  struct NXSResponse *r=exchange_bytes(req,size);free(req);assert(r&&r->parts[3].x==NXS_INPUT_HANDLED);
}
static void key(unsigned logical,const char *text){key_with_modifiers(logical,text,0);}
static void idle_cpu(pid_t helper)
{
  clockid_t clock;struct timespec a,b,pause={.tv_nsec=250000000};assert(!clock_getcpuclockid(helper,&clock));
  assert(!clock_gettime(clock,&a));nanosleep(&pause,NULL);assert(!clock_gettime(clock,&b));
  double cpu=(b.tv_sec-a.tv_sec)+(b.tv_nsec-a.tv_nsec)/1e9;assert(cpu<.1);
}
int main(int argc,char **argv)
{
  if(argc>3&&!strcmp(argv[3],"--multiline"))transport_kind=NXS_TEXTAREA;
  assert(argc>=3&&bridge_connect(argv[1]));pid_t helper=atoi(argv[2]);assert(helper>0);
  int notifier=eventfd(0,EFD_CLOEXEC|EFD_NONBLOCK);assert(notifier>=0);
  struct NXSControlRequest owner={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=15,.process=identity()};
  struct NXSResponse *r=exchange_bytes_descriptor(&owner,sizeof(owner),notifier);assert(r&&r->parts[3].x==1);
  assert(native_text_filter_register(filter));
  r=request(1);assert(r->width==180&&r->height==(transport_kind==NXS_TEXTAREA?96:24));
  if(transport_kind==NXS_TEXTAREA) {
    assert(model("First\nSecond\nThird\nFourth\nFifth\nSixth\nSeventh\nEighth\nNinth\nTenth\n",0,0));
    r=request(32);assert(r->parts[3].x==1&&r->parts[6].height>r->parts[5].height);
    r=request(34);assert(r->parts[3].x==1&&r->size==sizeof(*r)+sizeof(NXSTextGeometry));
    NXSTextGeometry geometry;memcpy(&geometry,r+1,sizeof(geometry));assert(geometry.size==sizeof(geometry));
    struct NXSControlRequest scroll={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=33,.process=identity(),
      .kind=transport_kind,.control=1,.x=1e9,.y=1e9};
    r=exchange_bytes(&scroll,sizeof(scroll));assert(r&&r->parts[3].x==1&&r->parts[5].y>0);
    assert(r->parts[5].y==geometry.maximum.y&&r->parts[5].x==geometry.maximum.x);
    r=request(33);assert(r->parts[3].x==1&&r->parts[5].y==0);
  }
  assert(model("Hello",1,2));
  struct NXSControlInputRequest focus={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=7,.process=identity(),
    .kind=transport_kind,.control=1,.focused=1};
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
  assert(native_text_filter_register(filter)&&native_command_filter_register(command_filter));
  request(1);assert(model("Hello",1,2));r=exchange_bytes(&focus,sizeof(focus));assert(r&&r->parts[3].x==1);
  key_with_modifiers(NXS_KEY_TEXT,"v",NXS_ALT);value("Hello");assert(command_queries>0&&command_executed==1);
  expected_value="Hello";expected_start=1;expected_length=2;expected_text="X";expected_command=NULL;
  allow=1;destroy_on_edit=0;mixed_late_command=1;key(NXS_KEY_TEXT,"X");value("HXlo");assert(proposals==7);
  assert(model("Hello",1,2));mixed_late_command=2;key(NXS_KEY_TEXT,"X");value("HXlo");assert(proposals==8);
  assert(model("Hello",1,2));
  command_enabled=0;key_with_modifiers(NXS_KEY_TEXT,"v",NXS_ALT);value("Hello");assert(command_executed==1);
  close(native_edit_channel);native_edit_channel=-1;
  key_with_modifiers(NXS_KEY_TEXT,"v",NXS_ALT);value("Hello");assert(command_executed==1);
  idle_cpu(helper);assert(native_text_filter_unregister());
  assert(native_text_filter_register(filter)&&native_command_filter_register(command_filter));
  command_enabled=1;command_delay=1;key_with_modifiers(NXS_KEY_TEXT,"v",NXS_ALT);value("Hello");assert(command_executed==2);
  idle_cpu(helper);assert(native_text_filter_unregister());
  assert(native_text_filter_register(filter)&&native_command_filter_register(command_filter));
  command_delay=0;command_destroy=1;key_with_modifiers(NXS_KEY_TEXT,"v",NXS_ALT);assert(command_executed==3&&request(18)->parts[3].x==0);
  idle_cpu(helper);assert(native_text_filter_unregister());
  owner.operation=16;r=exchange_bytes(&owner,sizeof(owner));assert(r&&r->parts[3].x==1);
  close(notifier);close(channel);
  puts("{\"native_pre_edit_ipc\":true,\"proposals\":8,\"nested_reads\":16,\"nested_mutations_rejected\":8,\"other_process_request_during_validation\":true,\"cancelled_typing_and_deletion\":true,\"accepted_typing_and_deletion\":true,\"callback_peer_loss_veto\":true,\"expired_decision_veto\":true,\"destroy_during_validation\":true,\"idle_after_expiry_and_destroy\":true,\"explicit_unregister\":true,\"native_application_command_ipc\":true,\"application_command_validation\":true,\"command_nested_reads_and_mutation_rejection\":true,\"command_peer_loss_veto\":true,\"command_expiry_veto\":true,\"command_frame_destruction\":true,\"command_idle_after_expiry_and_destroy\":true,\"late_command_before_current_edit_decision\":true,\"late_menu_before_current_edit_decision\":true}");
}
