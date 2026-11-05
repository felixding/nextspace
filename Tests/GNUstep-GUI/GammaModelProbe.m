/* Exercise native gamma model/RPC and main-thread dispatch without a GPU. */
#import <AppKit/AppKit.h>
#import <SystemKit/OSEWaylandDisplay.h>
#include <math.h>
#include <stdio.h>

static void require(BOOL value, const char *message)
{ if (!value) { fprintf(stderr, "%s\n", message); exit(1); } }

@interface GammaSettings : NSObject <OSESessionSettings>
{
@public
  NSUInteger requests;
  BOOL refuse;
}
@end
@implementation GammaSettings
- (bycopy NSData *)nextspaceSettingsRequest:(bycopy NSData *)data
{
  require([NSThread isMainThread], "Gamma RPC escaped the main thread");
  NSDictionary *request = OSESessionSettingsDecode(data);
  require([[request objectForKey:@"schema"] intValue] == 1 &&
    [[request objectForKey:@"action"] isEqual:@"gamma"], "Wrong gamma RPC");
  requests++;
  NSMutableDictionary *gamma = [NSMutableDictionary dictionary];
  NSDictionary *settings = [request objectForKey:@"settings"];
  for (NSString *key in [NSArray arrayWithObjects:@"red", @"green", @"blue", @"brightness", nil])
    [gamma setObject:[NSNumber numberWithDouble:round([[settings objectForKey:key] doubleValue] * 256) / 256] forKey:key];
  return OSESessionSettingsEncode([NSDictionary dictionaryWithObjectsAndKeys:
    [NSNumber numberWithBool:!refuse], @"success", gamma, @"gamma", nil]);
}
@end

@interface GammaWorker : NSObject
{
  OSEDisplay *display;
}
- (id)initWithDisplay:(OSEDisplay *)value;
@end
@implementation GammaWorker
- (id)initWithDisplay:(OSEDisplay *)value
{ if ((self = [super init])) display = [value retain]; return self; }
- (void)dealloc { [display release]; [super dealloc]; }
- (void)change:(id)sender
{
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  [display setGamma:0.8]; [pool drain];
}
@end

int main(void)
{
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  GammaSettings *provider = [GammaSettings new]; OSERegisterSessionSettings(provider);
  NSDictionary *one = [NSDictionary dictionaryWithObjectsAndKeys:@1, @"red", @1, @"green", @1, @"blue", @1, @"brightness", nil];
  NSMutableDictionary *head = [NSMutableDictionary dictionaryWithObjectsAndKeys:
    @1, @"id", @1, @"enabled", @256, @"gamma_size", one, @"gamma", @"TEST-1", @"name", @"model", @"model", @"serial", @"serial", nil];
  OSEDisplay *display = [[OSEDisplay alloc] initWithDescriptor:head screen:nil duplicateIdentity:NO];
  require([display isGammaSupported] && [display gamma] == 1 && [display gammaBrightness] == 1, "Initial gamma capability/state");
  [display setGammaRed:0.5 green:1.5 blue:2 brightness:0.75];
  NSDictionary *description = [display gammaDescription];
  require([[description objectForKey:OSEDisplayGammaRedKey] doubleValue] == 0.5 &&
    [[description objectForKey:OSEDisplayGammaGreenKey] doubleValue] == 1.5 &&
    [[description objectForKey:OSEDisplayGammaBlueKey] doubleValue] == 2 && [display gammaBrightness] == 0.75,
    "Channel/brightness mapping");
  [display setGamma:0];
  require([display gamma] == 1 && [display gammaBrightness] == 0.75, "Zero gamma legacy convention or brightness changed");
  [display setGammaBrightness:0.5]; require([display gamma] == 1 && [display gammaBrightness] == 0.5, "Brightness changed channels");
  NSUInteger before = provider->requests;
  [display setGamma:NAN]; [display setGamma:-1]; [display setGammaBrightness:3];
  [display setGammaFromDescription:[NSDictionary dictionaryWithObject:@"invalid" forKey:OSEDisplayGammaRedKey]];
  require(provider->requests == before && [display gamma] == 1, "Invalid gamma mutated state");
  NSDictionary *previous = [[display gammaDescription] retain];
  provider->refuse = YES; [display setGamma:2];
  require([[display gammaDescription] isEqual:previous], "Rejected gamma changed cached state");
  provider->refuse = NO; [previous release];
  GammaWorker *worker = [[GammaWorker alloc] initWithDisplay:display];
  NSThread *thread = [[NSThread alloc] initWithTarget:worker selector:@selector(change:) object:nil]; [thread start];
  NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:5];
  while (![thread isFinished] && [deadline timeIntervalSinceNow] > 0)
    [[NSRunLoop currentRunLoop] runMode:NSDefaultRunLoopMode beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.01]];
  require([thread isFinished] && [display gamma] == 205.0/256 && [display gammaBrightness] == 0.5,
    "Worker setter did not serialize onto main thread or retain accepted wire precision");
  [thread release]; [worker release];
  [display fadeTo:0 interval:0 brightness:0.5]; require([display gammaBrightness] == 0, "Fade-to-black target");
  [display fadeTo:1 interval:0 brightness:0.5]; require([display gammaBrightness] == 0.5, "Fade-to-normal target");
  [head setObject:@0 forKey:@"gamma_size"];
  OSEDisplay *unsupported = [[OSEDisplay alloc] initWithDescriptor:head screen:nil duplicateIdentity:NO];
  before = provider->requests; [unsupported setGamma:2]; [unsupported fadeToBlack:1];
  require(![unsupported isGammaSupported] && [unsupported gamma] == 1 && provider->requests == before,
    "Unsupported head claimed or applied gamma");
  [unsupported release]; [display release]; OSERegisterSessionSettings(nil); [provider release];
  puts("Native gamma model: channel/brightness mapping, invalid/rejected state, worker dispatch, fades and unsupported head PASS");
  [pool drain]; return 0;
}
