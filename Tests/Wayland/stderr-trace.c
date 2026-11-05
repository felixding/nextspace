/* Test-only per-process diagnostics. MIT. No application methods are replaced. */
#define _GNU_SOURCE
#include <fcntl.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

__attribute__((constructor)) static void trace_stderr(void) {
  const char *directory = getenv("NEXTSPACE_TEST_STDERR_DIR");
  if (!directory) return;
  char path[PATH_MAX];
  int length = snprintf(path, sizeof(path), "%s/%ld.log", directory, (long)getpid());
  if (length <= 0 || length >= (int)sizeof(path)) return;
  int fd = open(path, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0600);
  if (fd < 0) return;
  if (fd != STDERR_FILENO) {
    dup2(fd, STDERR_FILENO);
    close(fd);
  }
}
