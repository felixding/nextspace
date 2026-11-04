/* Per-session storage fixture. LGPL-2.0-or-later. */
#import <Foundation/Foundation.h>
#import <AppKit/NSPasteboard.h>
#import <AppKit/NSApplication.h>
#import <GNUstepGUI/GSPasteboardServer.h>

int main(int argc, char **argv)
{
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  NSString *mode = argc > 1 ? [NSString stringWithUTF8String:argv[1]] : @"";
  int result = 0;
  if ([mode isEqual:@"--ping"]) {
    result = [NSConnection rootProxyForConnectionWithRegisteredName:GSPasteboardServerName() host:@""] ? 0 : 1;
  } else if ([mode isEqual:@"--name"]) {
    puts([GSPasteboardServerName() UTF8String]);
  } else if ([mode isEqual:@"--library-dir"]) {
    puts([[NSSearchPathForDirectoriesInDomains(NSLibraryDirectory, NSUserDomainMask, YES) lastObject] UTF8String]);
  } else if ([mode isEqual:@"--export-text"] || [mode isEqual:@"--primary-export-text"]) {
    NSPasteboard *pasteboard = [mode isEqual:@"--primary-export-text"] ?
      [NSPasteboard pasteboardWithName:@"Selection"] : [NSPasteboard generalPasteboard];
    NSData *text = [[[pasteboard stringForType:NSStringPboardType]
      dataUsingEncoding:NSUTF8StringEncoding] retain];
    if (text) fwrite([text bytes], 1, [text length], stdout);
    else result = 1;
    [text release];
  } else if ([mode isEqual:@"--clear"]) {
    NSPasteboard *pasteboard = [NSPasteboard generalPasteboard];
    NSInteger declared = [pasteboard declareTypes:[NSArray arrayWithObject:NSStringPboardType] owner:nil];
    result = ![pasteboard setString:@"pending" forType:NSStringPboardType];
    if (result) fprintf(stderr, "Pasteboard clear rejected: declared=%ld current=%ld\n",
      (long)declared, (long)[pasteboard changeCount]);
  } else if (([mode isEqual:@"--text-file"] || [mode isEqual:@"--primary-text-file"]) && argc == 3) {
    NSString *expected = [NSString stringWithContentsOfFile:[NSString stringWithUTF8String:argv[2]]
      encoding:NSUTF8StringEncoding error:NULL];
    NSPasteboard *pasteboard = [mode isEqual:@"--primary-text-file"] ?
      [NSPasteboard pasteboardWithName:@"Selection"] : [NSPasteboard generalPasteboard];
    NSString *actual = [pasteboard stringForType:NSStringPboardType];
    result = ![actual isEqual:expected];
    if (result) fprintf(stderr, "Pasteboard mismatch: expected %lu characters, got %s%lu\n",
      (unsigned long)[expected length], actual ? "" : "nil, ", (unsigned long)[actual length]);
  } else if ([mode isEqual:@"--primary-empty"]) {
    result = [[[NSPasteboard pasteboardWithName:@"Selection"] types] count] != 0;
  } else if ([mode isEqual:@"--service"]) {
    [NSApplication sharedApplication];
    NSArray *types = [NSArray arrayWithObject:NSStringPboardType];
    [NSApp registerServicesMenuSendTypes:types returnTypes:types];
    NSPasteboard *pasteboard = [NSPasteboard pasteboardWithUniqueName];
    NSData *binary = [@"opaque service data" dataUsingEncoding:NSUTF8StringEncoding];
    [pasteboard declareTypes:[NSArray arrayWithObjects:NSStringPboardType, @"org.nextspace.test.binary", nil] owner:nil];
    [pasteboard setString:@"日本語" forType:NSStringPboardType];
    [pasteboard setData:binary forType:@"org.nextspace.test.binary"];
    result = !(NSPerformService(@"NextSpace Wayland Echo", pasteboard) &&
      [[pasteboard stringForType:NSStringPboardType] isEqual:@"Services:日本語"] &&
      [[pasteboard dataForType:@"org.nextspace.test.binary"] isEqual:binary]);
    [pasteboard releaseGlobally];
  } else {
    NSPasteboard *pasteboard = [NSPasteboard generalPasteboard];
    NSString *custom = @"org.nextspace.test.binary";
    const unsigned char bytes[] = {0, 1, 127, 128, 255};
    NSData *binary = [NSData dataWithBytes:bytes length:sizeof(bytes)];
    NSString *text = @"Native pasteboard: 日本語, 한글, UTF-8";
    if ([mode isEqual:@"--write"] || [mode isEqual:@"--write-hold"]) {
      id owner = [mode isEqual:@"--write-hold"] ? [[[NSObject alloc] init] autorelease] : nil;
      [pasteboard declareTypes:[NSArray arrayWithObjects:NSStringPboardType, custom, nil] owner:owner];
      result = !([pasteboard setString:text forType:NSStringPboardType] && [pasteboard setData:binary forType:custom]);
      if (!result && [mode isEqual:@"--write-hold"]) {
        puts("Pasteboard data ready"); fflush(stdout);
        [[NSRunLoop currentRunLoop] run];
      }
    } else if ([mode isEqual:@"--read"]) {
      result = !([[pasteboard stringForType:NSStringPboardType] isEqual:text] &&
        [[pasteboard dataForType:custom] isEqual:binary]);
      if (result) NSLog(@"Pasteboard read mismatch: types=%@ text=%@ data=%@",
        [pasteboard types], [pasteboard stringForType:NSStringPboardType], [pasteboard dataForType:custom]);
    } else if ([mode isEqual:@"--empty"]) {
      result = [[pasteboard types] count] != 0;
    } else result = 2;
  }
  [pool drain];
  return result;
}
