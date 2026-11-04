/* Exercise native Login transport without a GUI. Responses never echo inputs.
   SPDX-License-Identifier: GPL-2.0-or-later */
#import <Foundation/Foundation.h>
#import "GreetdClient.h"
#include <string.h>
#include <stdlib.h>

static NSDictionary *perform(GreetdClient *client, NSDictionary *step)
{
  NSError *error = nil;
  NSString *operation = [step objectForKey:@"operation"];
  NSDictionary *reply = nil;
  if ([operation isEqual:@"begin"]) reply = [client beginSessionForUser:[step objectForKey:@"user"] error:&error];
  else if ([operation isEqual:@"respond"]) reply = [client respond:[step objectForKey:@"response"] error:&error];
  else if ([operation isEqual:@"cancel"]) reply = [client cancelSession:&error];
  else if ([operation isEqual:@"start"]) reply = [client startSessionWithArguments:[step objectForKey:@"arguments"]
    environment:[step objectForKey:@"environment"] error:&error];
  else return nil;
  NSMutableDictionary *result = [NSMutableDictionary dictionaryWithObject:operation forKey:@"operation"];
  if (reply) [result setObject:reply forKey:@"reply"];
  if (error) [result setObject:[NSNumber numberWithInteger:[error code]] forKey:@"error"];
  return result;
}

static void emit(id result)
{
  NSData *output = [NSJSONSerialization dataWithJSONObject:result options:0 error:NULL];
  fwrite([output bytes], 1, [output length], stdout); putchar('\n'); fflush(stdout);
}

int main(int argc, char **argv)
{
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  if (argc != 3) { [pool drain]; return 2; }
  NSError *error = nil;
  GreetdClient *client = [[GreetdClient alloc] initWithSocketPath:[NSString stringWithUTF8String:argv[1]] error:&error];
  NSMutableArray *results = [NSMutableArray array];
  if (!client) {
    [results addObject:[NSDictionary dictionaryWithObjectsAndKeys:@"connect", @"operation",
      [NSNumber numberWithInteger:[error code]], @"error", nil]];
  } else if (strcmp(argv[2], "--stream") == 0) {
    char *line = NULL;
    size_t capacity = 0;
    ssize_t length;
    while ((length = getline(&line, &capacity, stdin)) >= 0) {
      NSAutoreleasePool *requestPool = [NSAutoreleasePool new];
      NSData *data = [NSData dataWithBytes:line length:length];
      memset(line, 0, capacity);
      id step = [NSJSONSerialization JSONObjectWithData:data options:0 error:NULL];
      NSDictionary *result = [step isKindOfClass:[NSDictionary class]] ? perform(client, step) : nil;
      if (!result) { free(line); [client release]; [requestPool drain]; [pool drain]; return 4; }
      emit(result);
      [requestPool drain];
    }
    free(line); [client release]; [pool drain]; return 0;
  } else {
    NSData *data = strcmp(argv[2], "--stdin") == 0 ?
      [[NSFileHandle fileHandleWithStandardInput] readDataToEndOfFile] :
      [NSData dataWithContentsOfFile:[NSString stringWithUTF8String:argv[2]]];
    id script = [NSJSONSerialization JSONObjectWithData:data options:0 error:NULL];
    if (![script isKindOfClass:[NSArray class]]) { [client release]; [pool drain]; return 3; }
    for (NSDictionary *step in script) {
      NSDictionary *result = perform(client, step);
      if (!result) { [client release]; [pool drain]; return 4; }
      [results addObject:result];
    }
  }
  emit(results);
  [client release]; [pool drain];
  return 0;
}
