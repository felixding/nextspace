/* Verify real XPCOM ownership and original-model-before-native-close ordering. */
#include <assert.h>
#include <stdio.h>
#include "../../Experiments/FirefoxNativeUI/color-callback.inc"
struct Original {
  const struct NXSGeckoColorCallbackTable *table;
  unsigned references,updates,completions,destroyed;
  int running,release_during_done,release_during_update,new_owner,remove_owner;
  uint32_t status;
  struct NXSGeckoColorCallback *bridge;
};
static struct Original *current;
static unsigned acknowledgements,closed,ignored,passed;
static uint32_t current_token;
static int owner_live;
static unsigned retain_original(void *object){return ++((struct Original *)object)->references;}
static unsigned release_original(void *object)
{
  struct Original *original=object;assert(original->references);
  unsigned remaining=--original->references;if(!remaining)original->destroyed++;
  return remaining;
}
static uint32_t query_original(void *object,const void *interface,void **result)
{(void)interface;retain_original(object);*result=object;return 0;}
static uint32_t update_original(void *object,const void *value)
{
  struct Original *original=object;assert(value);original->updates++;
  if(original->release_during_update)color_callback_release(original->bridge);
  return 0x1122;
}
static uint32_t done_original(void *object,const void *value)
{
  struct Original *original=object;assert(value);original->completions++;original->running=0;
  if(original->new_owner)current_token++;
  if(original->remove_owner)owner_live=0;
  if(original->release_during_done)color_callback_release(original->bridge);
  return original->status;
}
static const struct NXSGeckoColorCallbackTable original_methods={
  query_original,retain_original,release_original,update_original,done_original
};
static void color_callback_completed(uint64_t control,uint32_t token)
{
  assert(current&&!current->running&&!current->destroyed);
  acknowledgements++;
  if(owner_live&&control==42&&token==current_token)closed++;
  else ignored++;
}
static struct NXSGeckoColorCallback *create(struct Original *original)
{
  *original=(struct Original){.table=&original_methods,.references=1,.running=1,.status=0x3344};
  current=original;current_token=19;owner_live=1;
  struct NXSGeckoColorCallback *bridge=color_callback_create(original,42,19);assert(bridge);
  original->bridge=bridge;release_original(original);assert(original->references==1);return bridge;
}
static void finish(struct Original *original)
{assert(original->destroyed==1&&original->references==0);passed++;}
int main(void)
{
  struct Original original;int value=1;void *queried=NULL;
  struct NXSGeckoColorCallback *bridge=create(&original);
  assert(bridge->table->query(bridge,NULL,&queried)==0&&queried==bridge);
  assert(bridge->references==2&&original.references==1);bridge->table->release(queried);
  assert(bridge->table->update(bridge,&value)==0x1122&&original.updates==1);
  unsigned before=closed;
  assert(bridge->table->done(bridge,&value)==0x3344&&original.completions==1&&closed==before+1);
  bridge->table->release(bridge);finish(&original);

  bridge=create(&original);original.status=0x80004005u;before=acknowledgements;
  assert(bridge->table->done(bridge,&value)==0x80004005u&&acknowledgements==before+1);
  bridge->table->release(bridge);finish(&original);

  bridge=create(&original);bridge->table->done(bridge,&value);before=acknowledgements;
  assert(bridge->table->done(bridge,&value)==0&&bridge->table->update(bridge,&value)==0);
  assert(original.completions==1&&original.updates==0&&acknowledgements==before);
  bridge->table->release(bridge);finish(&original);

  bridge=create(&original);original.release_during_done=1;
  bridge->table->done(bridge,&value);finish(&original);

  bridge=create(&original);original.new_owner=1;before=ignored;
  bridge->table->done(bridge,&value);assert(ignored==before+1);
  bridge->table->release(bridge);finish(&original);

  bridge=create(&original);original.remove_owner=1;before=ignored;
  bridge->table->done(bridge,&value);assert(ignored==before+1);
  bridge->table->release(bridge);finish(&original);

  bridge=create(&original);before=acknowledgements;
  bridge->table->release(bridge);assert(acknowledgements==before);finish(&original);

  bridge=create(&original);original.release_during_update=1;
  bridge->table->update(bridge,&value);finish(&original);
  printf("{\"callback_lifetime_cases\":%u,\"original_model_before_close_ack\":true,\"owner_removal_and_reentrancy\":true}\n",passed);
}
