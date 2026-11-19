/* Original XPCOM callback ownership only; no color control implementation.
 * Complete the original browser callback before acknowledging native close.
 * GPL-2.0-or-later. */
#include <stdint.h>
#include <stdlib.h>
struct NXSGeckoColorCallbackTable {
  uint32_t (*query)(void *,const void *,void **);
  unsigned (*retain)(void *);
  unsigned (*release)(void *);
  uint32_t (*update)(void *,const void *);
  uint32_t (*done)(void *,const void *);
};
_Static_assert(sizeof(struct NXSGeckoColorCallbackTable)==5*sizeof(void *),"Original Gecko callback vtable ABI");
struct NXSGeckoColorCallback {
  const struct NXSGeckoColorCallbackTable *table;
  void *delegate;
  uint64_t control;
  uint32_t token;
  unsigned references;
  int finished;
};
static void color_callback_completed(uint64_t,uint32_t);
static const struct NXSGeckoColorCallbackTable *color_callback_table(void *object)
{return *(const struct NXSGeckoColorCallbackTable **)object;}
static unsigned color_callback_retain(void *object)
{return ++((struct NXSGeckoColorCallback *)object)->references;}
static unsigned color_callback_release(void *object)
{
  struct NXSGeckoColorCallback *entry=object;
  unsigned remaining=--entry->references;
  if(!remaining) {color_callback_table(entry->delegate)->release(entry->delegate);free(entry);}
  return remaining;
}
static uint32_t color_callback_query(void *object,const void *interface,void **result)
{
  struct NXSGeckoColorCallback *entry=object;color_callback_retain(entry);
  uint32_t status=color_callback_table(entry->delegate)->query(entry->delegate,interface,result);
  if(!(status&0x80000000u)&&*result==entry->delegate) {
    color_callback_table(entry->delegate)->release(entry->delegate);
    *result=entry;color_callback_retain(entry);
  }
  color_callback_release(entry);return status;
}
static uint32_t color_callback_update(void *object,const void *value)
{
  struct NXSGeckoColorCallback *entry=object;
  if(entry->finished)return 0;
  color_callback_retain(entry);
  uint32_t status=color_callback_table(entry->delegate)->update(entry->delegate,value);
  color_callback_release(entry);return status;
}
static uint32_t color_callback_done(void *object,const void *value)
{
  struct NXSGeckoColorCallback *entry=object;
  if(entry->finished)return 0;
  color_callback_retain(entry);entry->finished=1;
  uint32_t status=color_callback_table(entry->delegate)->done(entry->delegate,value);
  /* The original callback may remove its owner or open another picker. The
   * shared host checks this original session token before completing close. */
  color_callback_completed(entry->control,entry->token);
  color_callback_release(entry);return status;
}
static const struct NXSGeckoColorCallbackTable color_callback_methods={
  color_callback_query,color_callback_retain,color_callback_release,
  color_callback_update,color_callback_done
};
static struct NXSGeckoColorCallback *color_callback_create(void *delegate,uint64_t control,uint32_t token)
{
  if(!delegate||!control||!token)return NULL;
  struct NXSGeckoColorCallback *entry=calloc(1,sizeof(*entry));if(!entry)return NULL;
  *entry=(struct NXSGeckoColorCallback){.table=&color_callback_methods,.delegate=delegate,
    .control=control,.token=token,.references=1};
  color_callback_table(delegate)->retain(delegate);return entry;
}
