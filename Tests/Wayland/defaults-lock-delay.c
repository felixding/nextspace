/* Delay one defaults lock acquisition in a disposable pasteboard regression. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

int mkdir(const char *path, mode_t mode)
{
  static int (*real_mkdir)(const char *, mode_t);
  if (!real_mkdir) real_mkdir = dlsym(RTLD_NEXT, "mkdir");
  int result = real_mkdir(path, mode), saved_errno = errno;
  const char *marker = getenv("NEXTSPACE_TEST_DEFAULTS_LOCK_MARKER");
  if (!result && marker && strstr(path, ".GNUstepDefaults.lck")) {
    int fd = open(marker, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
    if (fd >= 0) {
      close(fd);
      struct timespec delay = { .tv_sec = 2 };
      nanosleep(&delay, NULL);
    }
  }
  errno = saved_errno;
  return result;
}
