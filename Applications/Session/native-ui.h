/* Session-owned native UI process and private Workspace-role relay.
 * No widget implementation or menu model interpretation. GPL-2.0-or-later. */
struct native_ui_host {
  char *command, *directory, *socket;
  pid_t pid;
  int control, workspace;
  bool ready, inflight, killing;
  unsigned failures;
  int64_t deadline, restart, stable, response_deadline;
  uint64_t serial, sent, flight, waiting;
  size_t request_size, reply_size;
  char request[8192], reply[1024];
};
static void native_ui_queue(struct native_ui_host *host, const void *bytes, size_t size)
{
  memcpy(host->request, bytes, size); host->request_size = size; host->serial++;
}
static bool native_ui_prepare(struct native_ui_host *host)
{
  if (!host->command) return true;
  char *directory = NULL;
  if (asprintf(&directory, "%s/nextspace-native-ui-XXXXXX", getenv("XDG_RUNTIME_DIR")) < 0) return false;
  if (!mkdtemp(directory)) { free(directory); return false; }
  host->directory = directory;
  if (asprintf(&host->socket, "%s/controls", host->directory) < 0) return false;
  if (strlen(host->socket) >= sizeof(((struct sockaddr_un *)0)->sun_path) ||
      setenv("NEXTSPACE_NATIVE_UI_SOCKET", host->socket, 1) < 0) return false;
  const char clear[] = "{\"operation\":\"clear\"}";
  native_ui_queue(host, clear, sizeof(clear)-1);
  return true;
}
static void native_ui_workspace_closed(struct native_ui_host *host)
{
  if (host->workspace >= 0) close(host->workspace);
  host->workspace = -1; host->waiting = 0; host->reply_size = 0;
  const char clear[] = "{\"operation\":\"clear\"}";
  native_ui_queue(host, clear, sizeof(clear)-1);
}
static int native_ui_workspace(struct native_ui_host *host)
{
  if (!host->command || !host->ready) return -1;
  native_ui_workspace_closed(host);
  int pair[2];
  if (socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC | SOCK_NONBLOCK, 0, pair) < 0) return -1;
  host->workspace = pair[0]; return pair[1];
}
static void native_ui_disable(struct native_ui_host *host)
{
  fprintf(stderr, "[session] Native UI host repeatedly failed; continuing without it.\n");
  host->command = NULL; host->ready = false;
  native_ui_workspace_closed(host);
  if (host->socket && unlink(host->socket) < 0 && errno != ENOENT)
    fprintf(stderr, "[session] Cannot remove the failed native UI endpoint: %s\n", strerror(errno));
}
static void native_ui_exited(struct native_ui_host *host)
{
  if (host->control >= 0) close(host->control);
  host->control = -1; host->pid = -1; host->ready = host->inflight = host->killing = false;
  host->sent = 0; host->deadline = 0;
  host->response_deadline = 0;
  if (host->stable && milliseconds()-host->stable >= 10000) host->failures = 0;
  host->stable = 0;
  if (++host->failures >= 3) native_ui_disable(host);
  else host->restart = milliseconds()+100;
}
static void native_ui_failed(struct native_ui_host *host)
{
  if (host->pid > 0 && !host->killing) {
    kill(host->pid, SIGTERM); host->killing = true; host->deadline = milliseconds()+2000;
  }
  host->ready = false;
  if (host->control >= 0) close(host->control);
  host->control = -1; host->inflight = false; host->response_deadline = 0;
}
static bool native_ui_listening(struct native_ui_host *host)
{
  struct stat state;
  if (lstat(host->socket, &state) < 0 || !S_ISSOCK(state.st_mode) || state.st_uid != getuid() || (state.st_mode & 077)) return false;
  int descriptor = socket(AF_UNIX, SOCK_SEQPACKET|SOCK_CLOEXEC|SOCK_NONBLOCK, 0);
  if (descriptor < 0) return false;
  struct sockaddr_un address = {.sun_family=AF_UNIX};
  strcpy(address.sun_path, host->socket);
  struct ucred peer; socklen_t size = sizeof(peer);
  bool ready = connect(descriptor, (struct sockaddr *)&address, sizeof(address)) == 0 &&
    getsockopt(descriptor, SOL_SOCKET, SO_PEERCRED, &peer, &size) == 0 &&
    peer.pid == host->pid && peer.uid == getuid();
  close(descriptor); return ready;
}
static void native_ui_tick(struct native_ui_host *host)
{
  if (!host->command) return;
  if (host->pid < 0 && milliseconds() >= host->restart) {
    int pair[2];
    if (socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, pair) < 0) {
      fprintf(stderr, "[session] Native UI role socket failed: %s\n", strerror(errno)); native_ui_disable(host); return;
    }
    /* The directory and endpoint belong to this supervisor generation. */
    if (unlink(host->socket) < 0 && errno != ENOENT) {
      fprintf(stderr, "[session] Native UI endpoint cleanup failed: %s\n", strerror(errno));
      close(pair[0]); close(pair[1]); native_ui_disable(host); return;
    }
    char *arguments[] = {host->command, NULL};
    host->pid = launch(arguments, pair[1], -1, 'N'); close(pair[1]);
    if (host->pid < 0) { close(pair[0]); native_ui_disable(host); return; }
    host->control = pair[0]; host->deadline = milliseconds()+10000;
    fcntl(host->control, F_SETFL, fcntl(host->control, F_GETFL)|O_NONBLOCK);
  }
  if (host->pid > 0 && !host->ready && !host->killing) {
    if (native_ui_listening(host)) {
      host->ready = true; host->deadline = 0; host->stable = milliseconds();
      printf("NEXTSPACE_NATIVE_UI_SOCKET=%s\n", host->socket); fflush(stdout);
    }
  }
  if (host->deadline && milliseconds() >= host->deadline) {
    if (host->killing) { kill(host->pid, SIGKILL); host->deadline = INT64_MAX; }
    else { fprintf(stderr, "[session] Native UI host startup timed out.\n"); native_ui_failed(host); }
  }
  if (host->response_deadline && milliseconds() >= host->response_deadline) {
    fprintf(stderr, "[session] Native UI host menu reply timed out.\n"); native_ui_failed(host);
  }
}
static void native_ui_timeout(struct native_ui_host *host, int *timeout)
{
  if (!host->command) return;
  int64_t delay = host->pid < 0 ? host->restart-milliseconds() :
    !host->ready ? 100 : INT64_MAX;
  if (host->deadline && host->deadline != INT64_MAX && host->deadline-milliseconds() < delay)
    delay = host->deadline-milliseconds();
  if (host->response_deadline && host->response_deadline-milliseconds() < delay)
    delay = host->response_deadline-milliseconds();
  if (delay == INT64_MAX) return;
  if (delay < 0) delay = 0;
  if (*timeout < 0 || delay < *timeout) *timeout = delay;
}
static void native_ui_dispatch(struct native_ui_host *host, short helper_events, short shell_events)
{
  if (host->workspace >= 0 && shell_events & POLLIN) {
    char bytes[8192];
    ssize_t size = recv(host->workspace, bytes, sizeof(bytes), MSG_DONTWAIT|MSG_TRUNC);
    if (size < 0 && (errno == EAGAIN || errno == EINTR)) {}
    else if (size <= 0 || size > (ssize_t)sizeof(bytes) || host->waiting || host->reply_size)
      native_ui_workspace_closed(host);
    else { native_ui_queue(host, bytes, size); host->waiting = host->serial; }
  }
  if (host->workspace >= 0 && shell_events & (POLLHUP|POLLERR|POLLNVAL)) native_ui_workspace_closed(host);
  if (host->control >= 0 && helper_events & POLLIN) {
    char bytes[1024];
    ssize_t size = recv(host->control, bytes, sizeof(bytes), MSG_DONTWAIT|MSG_TRUNC);
    if (size < 0 && (errno == EAGAIN || errno == EINTR)) {}
    else if (size <= 0 || size > (ssize_t)sizeof(bytes) || !host->inflight) native_ui_failed(host);
    else {
      host->inflight = false;
      host->response_deadline = 0;
      if (host->waiting == host->flight && host->workspace >= 0) {
        memcpy(host->reply, bytes, size); host->reply_size = size; host->waiting = 0;
      }
    }
  }
  if (host->control >= 0 && helper_events & (POLLHUP|POLLERR|POLLNVAL)) native_ui_failed(host);
  if (host->workspace >= 0 && host->reply_size) {
    ssize_t size = send(host->workspace, host->reply, host->reply_size, MSG_DONTWAIT|MSG_NOSIGNAL);
    if (size == (ssize_t)host->reply_size) host->reply_size = 0;
    else if (size >= 0 || (errno != EAGAIN && errno != EINTR)) native_ui_workspace_closed(host);
  }
  if (host->ready && !host->inflight && host->sent != host->serial) {
    ssize_t size = send(host->control, host->request, host->request_size, MSG_DONTWAIT|MSG_NOSIGNAL);
    if (size == (ssize_t)host->request_size) {
      host->sent = host->flight = host->serial; host->inflight = true; host->response_deadline = milliseconds()+30000;
    }
    else if (size >= 0 || (errno != EAGAIN && errno != EINTR)) native_ui_failed(host);
  }
}
static int native_ui_remove(const char *path, const struct stat *state, int type, struct FTW *walk)
{
  (void)state; (void)walk;
  return type == FTW_DP ? rmdir(path) : unlink(path);
}
static bool native_ui_finish(struct native_ui_host *host)
{
  native_ui_workspace_closed(host);
  if (host->control >= 0) close(host->control);
  bool result = true;
  /* This fresh private directory is owned solely by the stopped session host.
     Remove its diagnostics too, and never follow a symlink out of the tree. */
  if (host->directory && nftw(host->directory, native_ui_remove, 16, FTW_DEPTH|FTW_PHYS) < 0 && errno != ENOENT) result = false;
  free(host->directory); free(host->socket); return result;
}
