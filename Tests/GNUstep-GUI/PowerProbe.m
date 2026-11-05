/* Request only the power action selected by the isolated test bus fixture.
   SPDX-License-Identifier: GPL-2.0-or-later */
#import <Foundation/Foundation.h>
#import <SystemKit/OSEPower.h>
#include <time.h>
#include <string.h>
#include <stdlib.h>

static double now(void)
{ struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t); return t.tv_sec+t.tv_nsec/1e9; }
int main(int argc,char **argv)
{
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  const char *testBus=getenv("NEXTSPACE_POWER_TEST_BUS"), *systemBus=getenv("DBUS_SYSTEM_BUS_ADDRESS");
  if (argc!=2 || !testBus || !systemBus || strcmp(testBus,systemBus)!=0 ||
      strncmp(testBus,"unix:path=/tmp/nextspace-power-",31)!=0) { [pool drain]; return 2; }
  OSEPowerAction action=strcmp(argv[1],"off")==0 ? OSEPowerOff :
    (strcmp(argv[1],"reboot")==0 ? OSEPowerReboot : (OSEPowerAction)99);
  NSError *error=nil;
  double started=now();
  BOOL accepted=[OSEPower requestAction:action error:&error];
  NSMutableDictionary *row=[NSMutableDictionary dictionaryWithObjectsAndKeys:
    [NSNumber numberWithBool:accepted],@"accepted",[NSNumber numberWithDouble:now()-started],@"seconds",nil];
  if (error) { [row setObject:[NSNumber numberWithInteger:[error code]] forKey:@"error"];
    [row setObject:[error localizedDescription] forKey:@"message"]; }
  NSData *json=[NSJSONSerialization dataWithJSONObject:row options:0 error:NULL];
  fwrite([json bytes],1,[json length],stdout);putchar('\n');
  [pool drain];return 0;
}
