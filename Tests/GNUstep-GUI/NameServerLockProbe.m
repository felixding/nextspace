/* Exercise actual Foundation name-server locking across process death. MIT. */
#import <Foundation/Foundation.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

@interface NSMessagePortNameServer (LockProbe)
+ (id)_fileLock;
@end

int main(int argc, char **argv)
{
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  if (argc==2 && !strcmp(argv[1],"--register")) {
    for (unsigned index=0;index<100;index++) {
      NSPort *port=[NSMessagePort port];
      NSString *name=[NSString stringWithFormat:@"NextSpaceLockProbe-%ld-%u",(long)getpid(),index];
      NSPortNameServer *server=[NSMessagePortNameServer sharedInstance];
      if (![server registerPort:port forName:name] || ![server removePortForName:name]) return 1;
      [port invalidate];
    }
    puts("{\"registered\":100}");[pool drain];return 0;
  }
  id lock=[NSMessagePortNameServer _fileLock];
  if (!lock) { [pool drain];return 2; }
  if (argc==2 && !strcmp(argv[1],"--hold")) {
    pid_t child=fork();
    if (!child) { execl("/bin/sleep","sleep","30",NULL);_exit(127); }
    printf("{\"pid\":%ld,\"child\":%ld}\n",(long)getpid(),(long)child);fflush(stdout);
    for (;;) pause();
  }
  [lock unlock];puts("{\"locked\":true}");[pool drain];return 0;
}
