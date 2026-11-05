/* User-session supervisor. SPDX-License-Identifier: GPL-2.0-or-later */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <getopt.h>
#include <limits.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/random.h>
#include <sys/signalfd.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static int64_t milliseconds(void)
{
  struct timespec now;
  clock_gettime(CLOCK_MONOTONIC, &now);
  return (int64_t)now.tv_sec * 1000 + now.tv_nsec / 1000000;
}

#include "logind.h"

static bool request_lock(int broker, char request, bool *requested, pid_t locker, unsigned *failures, int64_t *restart)
{
  if (send(broker, &request, 1, MSG_NOSIGNAL) != 1) return false;
  *requested = true;
  if (locker < 0) { *failures = 0; *restart = 0; }
  return true;
}

/* Sources are CLOEXEC in the supervisor. Only these explicit child duplicates
   survive exec; the shell never inherits the broker or compositor output pipe. */
static void install_fd(int source, int target)
{
  if (source == target) {
    if (fcntl(source, F_SETFD, 0) < 0) _exit(126);
  } else if (dup2(source, target) < 0) _exit(126);
}

static pid_t launch(char *const arguments[], int descriptor, int output, char role)
{
  pid_t parent = getpid();
  pid_t pid = fork();
  if (pid < 0) fprintf(stderr, "[session] Cannot fork %s: %s\n", arguments[0], strerror(errno));
  if (pid != 0) return pid;
  if (prctl(PR_SET_PDEATHSIG, SIGTERM) < 0 || getppid() != parent) _exit(126);
  if (output >= 0) install_fd(output, STDOUT_FILENO);
  if (descriptor >= 0) install_fd(descriptor, 3);
  if ((role == 'I' || role == 'L' || role == 'V') && setenv("WAYLAND_SOCKET", "3", 1) < 0) _exit(126);
  if (close_range(descriptor >= 0 ? 4 : 3, UINT_MAX, 0) < 0) _exit(126);
  sigset_t empty;
  sigemptyset(&empty);
  /* Packaged swaylock treats SIGUSR1 as an unauthenticated unlock. Keep it
     blocked in the locker; SIGUSR1 to this supervisor only requests locking. */
  if (role == 'L') sigaddset(&empty, SIGUSR1);
  sigprocmask(SIG_SETMASK, &empty, NULL);
  signal(SIGPIPE, SIG_DFL); signal(SIGTERM, SIG_DFL); signal(SIGINT, SIG_DFL);
  signal(SIGHUP, SIG_DFL); signal(SIGCHLD, SIG_DFL);
  execvp(arguments[0], arguments);
  fprintf(stderr, "[session] Cannot execute %s: %s\n", arguments[0], strerror(errno));
  _exit(127);
}

static pid_t launch_client(int broker, char role, char *const arguments[])
{
  int endpoints[2];
  if (socketpair(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0, endpoints) < 0) return -1;
  char byte = role;
  struct iovec vector = { &byte, 1 };
  union { struct cmsghdr align; char bytes[CMSG_SPACE(sizeof(int))]; } ancillary = {0};
  struct msghdr message = { .msg_iov = &vector, .msg_iovlen = 1,
    .msg_control = ancillary.bytes, .msg_controllen = sizeof(ancillary.bytes) };
  struct cmsghdr *header = CMSG_FIRSTHDR(&message);
  header->cmsg_level = SOL_SOCKET; header->cmsg_type = SCM_RIGHTS;
  header->cmsg_len = CMSG_LEN(sizeof(int));
  memcpy(CMSG_DATA(header), &endpoints[0], sizeof(int));
  pid_t pid = -1;
  if (sendmsg(broker, &message, MSG_NOSIGNAL) == 1)
    pid = launch(arguments, endpoints[1], -1, role);
  close(endpoints[0]); close(endpoints[1]);
  return pid;
}

static pid_t launch_workspace(int broker, char *const arguments[], bool initial)
{
  /* Login does not consume the Workspace protocol. Do not grant it a shell
     connection that toolkit helpers could inherit before it is marked CLOEXEC. */
  const char *session_class = getenv("XDG_SESSION_CLASS");
  if (session_class && strcmp(session_class, "greeter") == 0)
    return launch(arguments, -1, -1, false);
  pid_t pid = -1;
  size_t count = 0;
  while (arguments[count]) count++;
  char **shell_arguments = calloc(count + 4, sizeof(char *));
  if (shell_arguments) {
    memcpy(shell_arguments, arguments, count * sizeof(char *));
    shell_arguments[count] = "--nextspace-shell-fd";
    shell_arguments[count + 1] = "3";
    if (initial) shell_arguments[count + 2] = "--nextspace-restore-settings";
    pid = launch_client(broker, 'C', shell_arguments);
    free(shell_arguments);
  }
  return pid;
}

struct session_service {
  char *command;
  const char *name;
  char role;
  bool persistent;
  pid_t pid;
  unsigned failures;
  int64_t first_failure, restart, stop_deadline;
};

static void service_start(struct session_service *service, int broker, bool blocked)
{
  if (blocked && service->pid > 0 && !service->stop_deadline) {
    kill(service->pid, SIGTERM);
    service->stop_deadline = milliseconds() + 5000;
  }
  if (service->stop_deadline && milliseconds() >= service->stop_deadline) {
    kill(service->pid, SIGKILL);
    service->stop_deadline = INT64_MAX;
  }
  if (!blocked && service->command && service->pid < 0 && milliseconds() >= service->restart) {
    char *arguments[] = {service->command, NULL};
    service->pid = launch_client(broker, service->role, arguments);
    if (service->pid < 0) {
      fprintf(stderr, "[session] Cannot start %s.\n", service->name);
      service->command = NULL;
    }
  }
}

static void service_exited(struct session_service *service, bool revoked)
{
  service->pid = -1;
  if (revoked || service->stop_deadline) {
    service->stop_deadline = 0; service->failures = 0; service->restart = 0;
    return;
  }
  int64_t now = milliseconds();
  if (now - service->first_failure > 10000) { service->first_failure = now; service->failures = 0; }
  if (++service->failures >= 3) {
    if (service->persistent) {
      fprintf(stderr, "[session] %s repeatedly failed; retrying in five seconds.\n", service->name);
      service->failures = 0; service->restart = now + 5000;
    } else {
      fprintf(stderr, "[session] %s repeatedly failed; continuing without it.\n", service->name);
      service->command = NULL;
    }
  } else service->restart = now + 100;
}

static void service_timeout(struct session_service *service, bool blocked, int *timeout)
{
  int64_t wake = service->stop_deadline;
  if (!wake && !blocked && service->command && service->pid < 0) wake = service->restart;
  if (wake == INT64_MAX || (!wake && (blocked || !service->command || service->pid >= 0))) return;
  int64_t delay = wake - milliseconds();
  if (delay < 0) delay = 0;
  if (*timeout < 0 || delay < *timeout) *timeout = (int)delay;
}

static bool environment(void)
{
  const char *runtime = getenv("XDG_RUNTIME_DIR");
  struct stat state;
  if (!runtime || lstat(runtime, &state) < 0 || !S_ISDIR(state.st_mode) ||
      state.st_uid != getuid() || (state.st_mode & 077) != 0) {
    fprintf(stderr, "[session] XDG_RUNTIME_DIR must be a private directory owned by this user.\n");
    return false;
  }
  unsigned char random[16];
  size_t offset = 0;
  while (offset < sizeof(random)) {
    ssize_t count = getrandom(random + offset, sizeof(random) - offset, 0);
    if (count < 0 && errno == EINTR) continue;
    if (count <= 0) return false;
    offset += count;
  }
  char identifier[41] = "wayland-";
  for (size_t index = 0; index < sizeof(random); index++)
    snprintf(identifier + 8 + index * 2, 3, "%02x", random[index]);
  unsetenv("DISPLAY"); unsetenv("WAYLAND_DISPLAY"); unsetenv("WAYLAND_SOCKET");
  unsetenv("NEXTSPACE_SHELL_SOCKET"); unsetenv("XAUTHORITY");
  const char *session_class = getenv("XDG_SESSION_CLASS");
  if ((!session_class || !*session_class) && setenv("XDG_SESSION_CLASS", "user", 1) < 0) return false;
  const char *cursor_theme = getenv("XCURSOR_THEME");
  if ((!cursor_theme || !*cursor_theme) && setenv("XCURSOR_THEME", "NextSpace", 1) < 0) return false;
  if (setenv("NEXTSPACE_SESSION_ID", identifier, 1) < 0 ||
      setenv("NEXTSPACE_GS_BACKEND", "wayland", 1) < 0 ||
      setenv("XDG_SESSION_TYPE", "wayland", 1) < 0 ||
      setenv("XDG_SESSION_DESKTOP", "NextSpace", 1) < 0 ||
      setenv("DESKTOP_SESSION", "nextspace-wayland", 1) < 0 ||
      setenv("XDG_CURRENT_DESKTOP", "NEXTSPACE", 1) < 0) return false;
  printf("NEXTSPACE_SESSION_ID=%s\n", identifier); fflush(stdout);
  return true;
}

static bool remove_private_bus(char *directory)
{
  if (!directory) return true;
  char path[PATH_MAX];
  bool removed = true;
  int length = snprintf(path, sizeof(path), "%s/bus", directory);
  if (length > 0 && length < (int)sizeof(path) && unlink(path) < 0 && errno != ENOENT) removed = false;
  if (rmdir(directory) < 0 && errno != ENOENT) removed = false;
  free(directory);
  return removed;
}

static bool start_private_bus(pid_t *bus, char **directory)
{
  const char *names[] = {"DBUS_SESSION_BUS_ADDRESS", "DBUS_SESSION_BUS_PID",
    "DBUS_SESSION_BUS_WINDOWID", "DBUS_STARTER_BUS_TYPE", "DBUS_STARTER_ADDRESS"};
  for (unsigned i = 0; i < sizeof(names) / sizeof(*names); i++) unsetenv(names[i]);
  char *pattern = NULL;
  if (asprintf(&pattern, "%s/nextspace-bus-XXXXXX", getenv("XDG_RUNTIME_DIR")) < 0) return false;
  if (!mkdtemp(pattern)) { free(pattern); return false; }
  *directory = pattern;
  struct sockaddr_un socket_address;
  int length = snprintf(socket_address.sun_path, sizeof(socket_address.sun_path), "%s/bus", pattern);
  if (length < 0 || length >= (int)sizeof(socket_address.sun_path)) return false;
  char listen[sizeof(socket_address.sun_path) * 3 + 16];
  char *next = listen + sprintf(listen, "unix:path=");
  /* D-Bus address values escape bytes outside the specification's safe set. */
  for (const unsigned char *p = (const unsigned char *)socket_address.sun_path; *p; p++) {
    if ((*p >= 'a' && *p <= 'z') || (*p >= 'A' && *p <= 'Z') || (*p >= '0' && *p <= '9') ||
        *p == '/' || *p == '.' || *p == '_' || *p == '-' || *p == '*') *next++ = *p;
    else next += sprintf(next, "%%%02x", *p);
  }
  *next = 0;
  int output[2];
  if (pipe2(output, O_CLOEXEC | O_NONBLOCK) < 0) return false;
  char *arguments[] = {"dbus-daemon", "--session", "--nofork", "--nopidfile", "--address", listen, "--print-address=1", NULL};
  *bus = launch(arguments, -1, output[1], false);
  close(output[1]);
  if (*bus < 0) { close(output[0]); return false; }
  char address[1024];
  size_t used = 0;
  bool ready = false;
  int64_t deadline = milliseconds() + 5000;
  while (milliseconds() < deadline && used < sizeof(address) - 1) {
    struct pollfd descriptor = {output[0], POLLIN, 0};
    int remaining = (int)(deadline - milliseconds());
    if (poll(&descriptor, 1, remaining > 0 ? remaining : 0) < 0) {
      if (errno == EINTR) continue;
      break;
    }
    ssize_t count = read(output[0], address + used, sizeof(address) - used - 1);
    if (count < 0) { if (errno == EAGAIN || errno == EINTR) continue; break; }
    if (count == 0) break;
    used += count;
    address[used] = 0;
    char *newline = strchr(address, '\n');
    if (newline) {
      *newline = 0;
      ready = strncmp(address, "unix:", 5) == 0 && setenv("DBUS_SESSION_BUS_ADDRESS", address, 1) == 0;
      break;
    }
  }
  close(output[0]);
  return ready;
}

/* The supervisor owns this fresh bus. Publish only after both requested
   display sockets exist, before any session client or input method starts. */
static bool publish_activation_environment(void)
{
  char *arguments[] = {"dbus-update-activation-environment", "NEXTSPACE_SESSION_ID",
    "NEXTSPACE_GS_BACKEND", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "XDG_SESSION_TYPE", "XDG_SESSION_CLASS",
    "XDG_SESSION_DESKTOP", "XDG_CURRENT_DESKTOP", "DESKTOP_SESSION", "XCURSOR_THEME", NULL};
  pid_t child = launch(arguments, -1, -1, false);
  if (child < 0) return false;
  int64_t deadline = milliseconds() + 5000;
  for (;;) {
    int status;
    pid_t result = waitpid(child, &status, WNOHANG);
    if (result == child) return WIFEXITED(status) && WEXITSTATUS(status) == 0;
    if (result < 0) { if (errno == EINTR) continue; return false; }
    if (milliseconds() >= deadline) {
      kill(child, SIGKILL);
      while (waitpid(child, NULL, 0) < 0 && errno == EINTR) {}
      fprintf(stderr, "[session] D-Bus environment publication timed out.\n");
      return false;
    }
    poll(NULL, 0, 10);
  }
}

/* No arbitrary compositor output becomes an environment variable. */
static void ready_line(char *line, bool *wayland)
{
  char *value = strchr(line, '=');
  if (!value) return;
  *value++ = 0;
  if (strcmp(line, "WAYLAND_DISPLAY") == 0 && *value && !strchr(value, '/')) {
    setenv(line, value, 1); *wayland = true;
  } else return;
  printf("%s=%s\n", line, value); fflush(stdout);
}

static bool read_ready(int descriptor, bool *wayland)
{
  static char line[256];
  static size_t used;
  char bytes[256];
  ssize_t count = read(descriptor, bytes, sizeof(bytes));
  if (count < 0) return errno == EAGAIN || errno == EINTR;
  if (count == 0) return false;
  for (ssize_t index = 0; index < count; index++) {
    if (bytes[index] == '\n') {
      line[used] = 0; ready_line(line, wayland); used = 0;
    } else if (used < sizeof(line) - 1) line[used++] = bytes[index];
    else return false;
  }
  return true;
}

static void report_compositor_exit(pid_t pid)
{
  /* A dying child can close its files before its exit status is waitable. */
  int64_t deadline = milliseconds() + 50;
  for (;;) {
    siginfo_t status = {0};
    if (waitid(P_PID, pid, &status, WEXITED | WNOHANG | WNOWAIT) < 0) {
      fprintf(stderr, "[session] Cannot inspect compositor exit: %s\n", strerror(errno)); return;
    }
    if (status.si_pid) {
      fprintf(stderr, "[session] Compositor terminal status: code=%d, status=%d.\n", status.si_code, status.si_status);
      return;
    }
    if (milliseconds() >= deadline) {
      fprintf(stderr, "[session] No compositor exit status available before cleanup.\n"); return;
    }
    poll(NULL, 0, 1);
  }
}

/* The supervisor owns a process group and remains its live leader until cleanup
   finishes. A subreaper also collects helpers orphaned by a Workspace crash. */
static int owned_children(int signal)
{
  char path[96];
  snprintf(path, sizeof(path), "/proc/self/task/%d/children", getpid());
  FILE *children = fopen(path, "r");
  if (!children) return -1;
  int pid, count = 0;
  while (fscanf(children, "%d", &pid) == 1) {
    /* NSTask starts children in new process groups. Ownership follows retained
       child ancestry, including descendants adopted by the subreaper. */
    if (pid <= 1) continue;
    count++;
    if (signal) kill(pid, signal);
  }
  fclose(children);
  return count;
}

static bool stop_children(void)
{
  kill(-getpgrp(), SIGTERM);  /* SIGTERM stays blocked in this supervisor. */
  int64_t deadline = milliseconds() + 3000;
  for (;;) {
    pid_t child;
    do { child = waitpid(-1, NULL, WNOHANG); } while (child > 0 || (child < 0 && errno == EINTR));
    if (child < 0 && errno == ECHILD) return true;
    if (owned_children(SIGTERM) == 0) return true;
    if (milliseconds() >= deadline) break;
    poll(NULL, 0, 20);
  }
  /* Read only our own unreaped child IDs. With no other reaping thread, these
     cannot be recycled between reading and signaling; orphaned descendants are
     adopted here after their parent exits. Never signal a stale saved PID. */
  deadline = milliseconds() + 2000;
  fprintf(stderr, "[session] Forcing remaining session processes to exit.\n");
  do {
    if (owned_children(SIGKILL) < 0) return false;
    pid_t child;
    do { child = waitpid(-1, NULL, WNOHANG); } while (child > 0 || (child < 0 && errno == EINTR));
    if (child < 0 && errno == ECHILD) return true;
    if (owned_children(0) == 0) return true;
    poll(NULL, 0, 20);
  } while (milliseconds() < deadline);
  fprintf(stderr, "[session] Some session children did not exit.\n");
  return false;
}

/* Hooks have no privileged client descriptor. Keep termination responsive while
   waiting for a user's command, and leave unrelated child reaping to the loop. */
static int run_hook(const char *command, const char *phase, int signals, int compositor_output,
    int *stop_result)
{
  char *arguments[] = {(char *)command, (char *)phase, NULL};
  pid_t child = launch(arguments, -1, -1, false);
  if (child < 0) return 1;
  bool lock_pending = false;
  int status = 0;
  int64_t cancel_deadline = 0;
  for (;;) {
    pid_t reaped = waitpid(child, &status, WNOHANG);
    if (reaped == child) break;
    if (reaped < 0 && errno != EINTR) { status = 1 << 8; break; }
    struct pollfd descriptors[] = {{signals, POLLIN, 0}, {compositor_output, 0, 0}};
    poll(descriptors, 2, 100);
    struct signalfd_siginfo info;
    while (read(signals, &info, sizeof(info)) == sizeof(info)) {
      if (info.ssi_signo == SIGUSR1) lock_pending = true;
      else if (info.ssi_signo != SIGCHLD && *stop_result < 0) *stop_result = 0;
    }
    if ((descriptors[1].revents & (POLLHUP | POLLERR)) && *stop_result < 0) *stop_result = 1;
    if (*stop_result >= 0 && !cancel_deadline) {
      kill(child, SIGTERM);
      cancel_deadline = milliseconds() + 2000;
    }
    if (cancel_deadline && milliseconds() >= cancel_deadline) kill(child, SIGKILL);
  }
  if (lock_pending) kill(getpid(), SIGUSR1);
  kill(getpid(), SIGCHLD);
  int code = WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
  if (code) fprintf(stderr, "[session] %s exited with %d.\n", phase, code);
  return code;
}

int main(int argc, char **argv)
{
  const char *compositor = "nextspace-compositor";
  char *locker_command = NULL, *profile_command = NULL, *hook_command = NULL;
  struct session_service method = {.name = "Input method", .role = 'I', .pid = -1};
  struct session_service capture = {.name = "Capture backend", .role = 'V', .persistent = true, .pid = -1};
  bool want_private_bus = false;
  static const struct option options[] = {
    {"compositor", required_argument, NULL, 'c'},
    {"input-method", required_argument, NULL, 'i'},
    {"capture-backend", required_argument, NULL, 'v'},
    {"locker", required_argument, NULL, 'l'},
    {"greeter-profile", required_argument, NULL, 'p'},
    {"private-bus", no_argument, NULL, 'd'},
    {"session-hook", required_argument, NULL, 'u'},
    {"help", no_argument, NULL, 'h'}, {NULL, 0, NULL, 0}
  };
  int option;
  while ((option = getopt_long(argc, argv, "+c:i:v:l:u:p:dh", options, NULL)) != -1) {
    if (option == 'c') compositor = optarg;
    else if (option == 'i') method.command = optarg;
    else if (option == 'v') capture.command = optarg;
    else if (option == 'l') locker_command = optarg;
    else if (option == 'p') profile_command = optarg;
    else if (option == 'd') want_private_bus = true;
    else if (option == 'u') hook_command = optarg;
    else {
      fprintf(stderr, "Usage: %s [--compositor PATH] [--input-method EXECUTABLE] [--capture-backend EXECUTABLE] [--locker EXECUTABLE] [--greeter-profile EXECUTABLE] [--session-hook EXECUTABLE] [--private-bus] -- WORKSPACE [ARGUMENTS...]\n", argv[0]);
      return option == 'h' ? 0 : 1;
    }
  }
  if (optind == argc || !environment()) return 1;
  if (hook_command && strcmp(getenv("XDG_SESSION_CLASS"), "user") != 0) {
    fprintf(stderr, "[session] Hooks require an authenticated user session.\n"); return 1;
  }
  if (locker_command && strcmp(getenv("XDG_SESSION_CLASS"), "greeter") == 0) {
    fprintf(stderr, "[session] The greeter cannot run a user locker.\n"); return 1;
  }
  if (capture.command && strcmp(getenv("XDG_SESSION_CLASS"), "greeter") == 0) {
    fprintf(stderr, "[session] The greeter cannot run a capture backend.\n"); return 1;
  }
  if (profile_command && strcmp(getenv("XDG_SESSION_CLASS"), "greeter") != 0) {
    fprintf(stderr, "[session] Display preparation is only for the greeter.\n"); return 1;
  }
  for (int descriptor = 0; descriptor <= 2; descriptor++) {
    if (fcntl(descriptor, F_GETFD) < 0 && open("/dev/null", O_RDWR) < 0) return 1;
  }
  if ((getpgrp() != getpid() && setpgid(0, 0) < 0) || prctl(PR_SET_CHILD_SUBREAPER, 1) < 0) return 1;
  sigset_t mask;
  sigemptyset(&mask); sigaddset(&mask, SIGCHLD); sigaddset(&mask, SIGTERM);
  sigaddset(&mask, SIGINT); sigaddset(&mask, SIGHUP);
  sigaddset(&mask, SIGUSR1);
  if (sigprocmask(SIG_BLOCK, &mask, NULL) < 0) return 1;
  int signals = signalfd(-1, &mask, SFD_CLOEXEC | SFD_NONBLOCK);
  int broker[2], output[2];
  if (signals < 0 || socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, broker) < 0 ||
      pipe2(output, O_CLOEXEC | O_NONBLOCK) < 0) return 1;
  pid_t bus = -1;
  struct session_logind logind = {.sleep_inhibitor = -1};
  char *bus_directory = NULL;
  int result = 1;
  int hook_status = 0;
  bool hooks_started = false;
  if (want_private_bus && !start_private_bus(&bus, &bus_directory)) {
    fprintf(stderr, "[session] Cannot start a private D-Bus session.\n");
    close(broker[1]); close(output[1]);
    goto cleanup;
  }
  char *compositor_arguments[] = {(char *)compositor, "-S", "3", NULL};
  pid_t server = launch(compositor_arguments, broker[1], output[1], false);
  close(broker[1]); close(output[1]);
  if (server < 0) goto cleanup;
  pid_t workspace = -1;
  pid_t locker = -1;
  pid_t profile = -1;
  bool profile_ready = !profile_command;
  int64_t profile_deadline = 0;
  bool lock_requested = false;
  bool lock_confirmed = false;
  unsigned lock_failures = 0;
  int64_t lock_restart = 0, lock_deadline = 0;
  bool wayland = false, stopping = false, initial = true;
  bool activation_ready = !want_private_bus;
  unsigned failures = 0;
  int64_t deadline = milliseconds() + 10000, first_failure = 0, restart = 0;
  if (locker_command && !session_logind_init(&logind))
    fprintf(stderr, "[session] No logind session for this process; explicit locking remains available.\n");
  while (!stopping) {
    session_logind_process(&logind);
    if (logind.publish_hint) {
      logind.publish_hint = false;
      session_logind_hint(&logind, lock_confirmed);
    }
    if (logind.sleep_begin_pending) {
      logind.sleep_begin_pending = false;
      if (!request_lock(broker[0], 'P', &lock_requested, locker, &lock_failures, &lock_restart)) break;
    }
    if (logind.sleep_resume_pending) {
      logind.sleep_resume_pending = false;
      const char resumed = 'W';
      if (send(broker[0], &resumed, 1, MSG_NOSIGNAL) != 1) break;
      session_logind_inhibit(&logind);
    }
    if (logind.lock_requested) {
      logind.lock_requested = false;
      if (!request_lock(broker[0], 'R', &lock_requested, locker, &lock_failures, &lock_restart)) break;
    }
    if (!activation_ready && wayland) {
      if (!publish_activation_environment()) {
        fprintf(stderr, "[session] Cannot publish the D-Bus activation environment.\n"); break;
      }
      activation_ready = true;
      printf("DBUS_SESSION_BUS_ADDRESS=%s\n", getenv("DBUS_SESSION_BUS_ADDRESS")); fflush(stdout);
    }
    if (hook_command && !hooks_started && wayland && activation_ready) {
      hooks_started = true;
      int stop_result = -1;
      int code = run_hook(hook_command, "LoginHook", signals, output[0], &stop_result);
      if (stop_result >= 0) { result = stop_result; break; }
      hook_status |= code;
    }
    if (!profile_ready && profile < 0 && wayland && activation_ready) {
      char *arguments[] = {profile_command, "--nextspace-shell-fd", "3", NULL};
      profile = launch_client(broker[0], 'C', arguments);
      if (profile < 0) {
        fprintf(stderr, "[session] Cannot prepare greeter displays; keeping the safe layout.\n");
        profile_ready = true;
      } else profile_deadline = milliseconds() + 10000;
    }
    if (profile >= 0 && profile_deadline && milliseconds() >= profile_deadline) {
      fprintf(stderr, "[session] Display preparation timed out; keeping the safe layout.\n");
      kill(profile, SIGKILL); profile_deadline = 0;
    }
    if (wayland && activation_ready && profile_ready) {
      service_start(&method, broker[0], false);
      service_start(&capture, broker[0], lock_requested || lock_confirmed);
    }
    if (lock_requested && locker_command && locker < 0 && lock_failures < 3 &&
        wayland && activation_ready && milliseconds() >= lock_restart) {
      char *arguments[] = {locker_command, NULL};
      locker = launch_client(broker[0], 'L', arguments);
      if (locker < 0) { fprintf(stderr, "[session] Cannot start locker; desktop remains locked.\n"); break; }
      lock_deadline = milliseconds() + 10000;
    }
    if (locker >= 0 && lock_deadline && milliseconds() >= lock_deadline) {
      fprintf(stderr, "[session] Locker startup timed out; desktop remains locked.\n");
      kill(locker, SIGKILL); lock_deadline = 0;
    }
    if (workspace < 0 && wayland && activation_ready && profile_ready && milliseconds() >= restart) {
      workspace = launch_workspace(broker[0], argv + optind, initial);
      if (workspace < 0) { fprintf(stderr, "[session] Cannot start Workspace.\n"); break; }
      initial = false;
    }
    int timeout = workspace < 0 ? (int)((wayland ? restart : deadline) - milliseconds()) : -1;
    if (timeout < 0 && workspace < 0) {
      if (!wayland) {
        fprintf(stderr, "[session] Compositor startup timed out.\n"); break;
      }
      timeout = 0;
    }
    if (!profile_ready && profile >= 0) {
      int delay = (int)(profile_deadline - milliseconds());
      timeout = profile_deadline ? (delay > 0 ? delay : 0) : -1;
    }
    if (wayland && activation_ready && profile_ready) {
      service_timeout(&method, false, &timeout);
      service_timeout(&capture, lock_requested || lock_confirmed, &timeout);
    }
    int64_t lock_wake = locker >= 0 ? lock_deadline :
      lock_requested && locker_command && lock_failures < 3 ? lock_restart : 0;
    if (lock_wake) {
      int delay = (int)(lock_wake - milliseconds());
      if (delay < 0) delay = 0;
      if (timeout < 0 || delay < timeout) timeout = delay;
    }
    struct pollfd logind_poll = session_logind_poll(&logind, &timeout);
    struct pollfd descriptors[] = {{signals, POLLIN, 0}, {output[0], POLLIN, 0}, {broker[0], POLLIN, 0}, logind_poll};
    if (poll(descriptors, 4, timeout) < 0) {
      if (errno == EINTR) continue;
      fprintf(stderr, "[session] Event polling failed: %s\n", strerror(errno)); break;
    }
    if (descriptors[1].revents & (POLLHUP | POLLERR | POLLNVAL)) {
      fprintf(stderr, "[session] Compositor output closed (poll events %#x).\n", descriptors[1].revents);
      report_compositor_exit(server);
      result = 1; break;
    }
    if ((descriptors[1].revents & POLLIN) && !read_ready(output[0], &wayland)) {
      fprintf(stderr, "[session] Invalid compositor readiness output.\n"); result = 1; break;
    }
    if (descriptors[2].revents) {
      char event;
      ssize_t count = recv(broker[0], &event, 1, MSG_DONTWAIT | MSG_TRUNC);
      if (count != 1) {
        fprintf(stderr, "[session] Compositor broker receive failed (%zd bytes): %s\n",
          count, count < 0 ? strerror(errno) : "closed or malformed message");
        report_compositor_exit(server);
        result = 1; break;
      }
      if (event == 'R') {
        if (!lock_requested) { lock_requested = true; lock_failures = 0; }
        if (!locker_command) fprintf(stderr, "[session] No locker configured; desktop remains locked.\n");
      } else if (event == 'K') {
        lock_deadline = 0;
        lock_confirmed = true;
        session_logind_hint(&logind, true);
        printf("NEXTSPACE_LOCKED=1\n"); fflush(stdout);
      } else if (event == 'U') {
        lock_requested = false; lock_deadline = 0;
        lock_confirmed = false;
        session_logind_hint(&logind, false);
        printf("NEXTSPACE_LOCKED=0\n"); fflush(stdout);
      } else if (event == 'S') {
        session_logind_sleep_protected(&logind);
        lock_confirmed = true;
        session_logind_hint(&logind, true);
      } else {
        fprintf(stderr, "[session] Unexpected compositor broker event %#x.\n", (unsigned char)event);
        result = 1; break;
      }
    }
    if (!descriptors[0].revents) continue;
    struct signalfd_siginfo info;
    while (read(signals, &info, sizeof(info)) == sizeof(info)) {
      if (info.ssi_signo == SIGUSR1) {
        if (locker_command && wayland) {
          if (!request_lock(broker[0], 'R', &lock_requested, locker, &lock_failures, &lock_restart))
            { result = 1; stopping = true; }
        }
      } else if (info.ssi_signo != SIGCHLD) { result = 0; stopping = true; }
    }
    int status;
    pid_t child;
    while ((child = waitpid(-1, &status, WNOHANG)) > 0) {
      if (child == server || child == bus) {
        fprintf(stderr, "[session] %s exited with %d.\n", child == server ? "Compositor" : "D-Bus daemon",
          WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status));
        stopping = true; result = 1;
      }
      else if (child == profile) {
        profile = -1; profile_ready = true; profile_deadline = 0;
        if (!WIFEXITED(status) || WEXITSTATUS(status) != 0)
          fprintf(stderr, "[session] Display preparation failed; keeping the safe layout.\n");
      }
      else if (child == locker) {
        locker = -1; lock_deadline = 0;
        if (lock_requested) {
          int code = WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
          fprintf(stderr, "[session] Locker exited with %d; desktop remains locked.\n", code);
          int64_t now = milliseconds();
          if (++lock_failures >= 3)
            fprintf(stderr, "[session] Locker repeatedly failed; desktop remains locked. Send SIGUSR1 to retry.\n");
          else lock_restart = now + 100;
        }
      }
      else if (child == method.pid) service_exited(&method, false);
      else if (child == capture.pid) service_exited(&capture, lock_requested || lock_confirmed);
      else if (child == workspace && !stopping) {
        workspace = -1;
        int code = WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
        if (code == 0 || code == 129) { result = code; stopping = true; continue; }
        int64_t now = milliseconds();
        if (now - first_failure > 10000) { first_failure = now; failures = 0; }
        if (++failures >= 3) { fprintf(stderr, "[session] Workspace repeatedly failed.\n"); stopping = true; continue; }
        fprintf(stderr, "[session] Workspace exited with %d; restarting.\n", code);
        restart = now + 100;
      }
    }
  }
cleanup:
  if (hooks_started) {
    /* Workspace has finished, but keep its native display and user services
       available until the final user hook completes. */
    struct signalfd_siginfo info;
    while (read(signals, &info, sizeof(info)) == sizeof(info)) {}
    int stop_result = -1;
    hook_status |= run_hook(hook_command, "LogoutHook", signals, -1, &stop_result);
    result |= hook_status;
  }
  close(broker[0]); close(output[0]);
  if (!stop_children()) result = 1;
  close(signals);
  session_logind_finish(&logind);
  if (!remove_private_bus(bus_directory)) {
    fprintf(stderr, "[session] Cannot remove the private bus socket directory.\n"); result = 1;
  }
  return result;
}
