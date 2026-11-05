/* Embedder descriptor readiness in the actual native loop. GPL-2.0-or-later. */
#import "ViewHost.h"
#include "Provider.h"
#include <fcntl.h>
#include <stdlib.h>
@interface NXSDescriptorWatcher : NSObject <RunLoopEvents>
@end
@implementation NXSDescriptorWatcher
- (void)receivedEvent:(void *)data type:(RunLoopEventType)type extra:(void *)extra forMode:(NSString *)mode
{
  /* Readiness wakes NSRunLoop.runMode. The embedding application consumes
   * its own messages after dispatch_events returns. Do not read its data. */
}
@end
struct NXSEventSource {
  int descriptor;
  NSRunLoop *loop;
  NXSDescriptorWatcher *watcher;
  struct NXSEventSource *next;
};
static NXSEventSource *sources;
NXSEventSource *nxs_gnustep_source_create(int descriptor)
{
  if(descriptor<0||fcntl(descriptor,F_GETFD)<0)return NULL;
  for(NXSEventSource *source=sources;source;source=source->next)
    if(source->descriptor==descriptor)return NULL;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  if(!nxs_host_initialize()){[pool drain];return NULL;}
  NXSEventSource *source=calloc(1,sizeof(*source));if(!source){[pool drain];return NULL;}
  source->descriptor=descriptor;source->loop=[[NSRunLoop currentRunLoop] retain];source->watcher=[NXSDescriptorWatcher new];
  for(NSString *mode in @[NSDefaultRunLoopMode,NSEventTrackingRunLoopMode])
    [source->loop addEvent:(void *)(intptr_t)descriptor type:ET_RDESC watcher:source->watcher forMode:mode];
  source->next=sources;sources=source;[pool drain];return source;
}
int nxs_gnustep_source_destroy(NXSEventSource *source)
{
  if(!source)return 1;
  NXSEventSource **cursor=&sources;
  while(*cursor&&*cursor!=source)cursor=&(*cursor)->next;
  if(!*cursor||source->loop!=[NSRunLoop currentRunLoop])return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  for(NSString *mode in @[NSDefaultRunLoopMode,NSEventTrackingRunLoopMode])
    [source->loop removeEvent:(void *)(intptr_t)source->descriptor type:ET_RDESC forMode:mode all:NO];
  *cursor=source->next;[source->watcher release];[source->loop release];free(source);[pool drain];return 1;
}
