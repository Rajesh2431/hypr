/* Waybar CFFI workspace buttons fed by scripts/workspaces.py.
 *
 * Feed (one line per change): entries joined by \x1d, each
 *   id \x1c label-markup \x1c classes (space separated: active empty urgent)
 * Renders GtkButtons inside a box named "workspaces", so the existing
 * `#workspaces button.active` etc. CSS applies unchanged.
 * Click switches workspace (ignored on the active one: the config uses
 * workspace back-and-forth, which would jump away).
 * Scroll: next / previous shown workspace.
 *
 * Build: sh ~/.config/hypr/waybar/cffi/build-workspaces-widget.sh
 */
#define _POSIX_C_SOURCE 200809L
#include <gtk/gtk.h>
#include <gtk-layer-shell.h>
#include <signal.h>
#include <stdlib.h>
#include <string.h>

typedef struct wbcffi_module wbcffi_module;
typedef struct {
  wbcffi_module *obj;
  const char *waybar_version;
  GtkContainer *(*get_root_widget)(wbcffi_module *);
  void (*queue_update)(wbcffi_module *);
} wbcffi_init_info;
typedef struct { const char *key; const char *value; } wbcffi_config_entry;

const size_t wbcffi_version = 1;

typedef struct {
  unsigned refs;
  gboolean alive;
  GtkWidget *root, *ebox, *box;
  GSubprocess *child;
  GDataInputStream *stream;
  GOutputStream *in;          /* helper stdin: "monitor X Y W H" (which output this bar is on) */
  GCancellable *cancel;
  guint restart_timer;
  char *command, *ids;   /* ids: "1,2,3,…" of current buttons */
  int active;
} WS;

static void ws_unref(WS *w) {
  if (--w->refs) return;
  g_clear_object(&w->child);
  g_clear_object(&w->stream);
  g_clear_object(&w->in);
  g_clear_object(&w->cancel);
  g_free(w->command);
  g_free(w->ids);
  g_free(w);
}

static const char *option(const wbcffi_config_entry *e, size_t n, const char *key, const char *fb) {
  for (size_t i = 0; i < n; ++i)
    if (strcmp(e[i].key, key) == 0) return e[i].value;
  return fb;
}

static void go(int id) {
  char *cmd = g_strdup_printf("hyprctl dispatch 'hl.dsp.focus({ workspace = %d })' >/dev/null", id);
  const char *argv[] = {"/bin/sh", "-c", cmd, NULL};
  g_spawn_async(NULL, (char **)argv, NULL, G_SPAWN_DEFAULT, NULL, NULL, NULL, NULL);
  g_free(cmd);
}

static void on_click(GtkButton *b, gpointer data) {
  WS *w = data;
  int id = GPOINTER_TO_INT(g_object_get_data(G_OBJECT(b), "ws-id"));
  if (id != w->active) go(id);
}

static gboolean on_scroll(GtkWidget *wd, GdkEventScroll *ev, gpointer data) {
  (void)wd;
  WS *w = data;
  int dir = 0;
  if (ev->direction == GDK_SCROLL_UP) dir = -1;
  else if (ev->direction == GDK_SCROLL_DOWN) dir = 1;
  else if (ev->direction == GDK_SCROLL_SMOOTH) dir = ev->delta_y < 0 ? -1 : ev->delta_y > 0 ? 1 : 0;
  if (!dir) return FALSE;
  GList *kids = gtk_container_get_children(GTK_CONTAINER(w->box));
  int n = g_list_length(kids), cur = -1, i = 0;
  for (GList *k = kids; k; k = k->next, ++i)
    if (GPOINTER_TO_INT(g_object_get_data(k->data, "ws-id")) == w->active) cur = i;
  if (cur >= 0 && cur + dir >= 0 && cur + dir < n)
    go(GPOINTER_TO_INT(g_object_get_data(g_list_nth_data(kids, cur + dir), "ws-id")));
  g_list_free(kids);
  return TRUE;
}

static void set_classes(GtkWidget *b, const char *classes) {
  GtkStyleContext *ctx = gtk_widget_get_style_context(b);
  const char *all[] = {"active", "empty", "urgent", "focused", "persistent"};
  for (size_t i = 0; i < G_N_ELEMENTS(all); ++i) gtk_style_context_remove_class(ctx, all[i]);
  char **cl = g_strsplit(classes, " ", -1);
  for (char **c = cl; *c; ++c)
    if (**c) gtk_style_context_add_class(ctx, *c);
  g_strfreev(cl);
}

static void apply(WS *w, const char *line) {
  char **entries = g_strsplit(line, "\x1d", -1);
  GString *ids = g_string_new(NULL);
  for (char **e = entries; *e; ++e) {
    char **f = g_strsplit(*e, "\x1c", 3);
    if (f[0]) g_string_append_printf(ids, "%s,", f[0]);
    g_strfreev(f);
  }
  gboolean same = !g_strcmp0(ids->str, w->ids);
  if (!same) {  /* different set of workspaces: rebuild the buttons */
    GList *kids = gtk_container_get_children(GTK_CONTAINER(w->box));
    for (GList *k = kids; k; k = k->next) gtk_widget_destroy(k->data);
    g_list_free(kids);
    g_free(w->ids);
    w->ids = g_strdup(ids->str);
  }
  GList *kids = gtk_container_get_children(GTK_CONTAINER(w->box));
  GList *k = kids;
  w->active = 0;
  for (char **e = entries; *e; ++e) {
    char **f = g_strsplit(*e, "\x1c", 3);
    if (!f[0] || !f[1]) { g_strfreev(f); continue; }
    int id = atoi(f[0]);
    const char *classes = f[2] ? f[2] : "";
    GtkWidget *b;
    if (same && k) {
      b = k->data;
      k = k->next;
    } else {
      b = gtk_button_new();
      gtk_button_set_relief(GTK_BUTTON(b), GTK_RELIEF_NONE);
      gtk_container_add(GTK_CONTAINER(b), gtk_label_new(NULL));
      g_object_set_data(G_OBJECT(b), "ws-id", GINT_TO_POINTER(id));
      g_signal_connect(b, "clicked", G_CALLBACK(on_click), w);
      gtk_box_pack_start(GTK_BOX(w->box), b, FALSE, FALSE, 0);
    }
    gtk_label_set_markup(GTK_LABEL(gtk_bin_get_child(GTK_BIN(b))), f[1]);
    set_classes(b, classes);
    if (strstr(classes, "active")) w->active = id;
    gtk_widget_show_all(b);
    g_strfreev(f);
  }
  g_list_free(kids);
  g_string_free(ids, TRUE);
  g_strfreev(entries);
}

/* tell the helper which monitor this bar lives on (logical geometry, matched to hyprctl monitors) */
static void send_monitor(WS *w) {
  if (!w->in) return;
  /* the output waybar assigned to this bar's layer surface (reliable), else ask GDK */
  GtkWidget *top = gtk_widget_get_toplevel(w->root);
  GdkMonitor *mon = GTK_IS_WINDOW(top) ? gtk_layer_get_monitor(GTK_WINDOW(top)) : NULL;
  if (!mon) {
    GdkWindow *win = gtk_widget_get_window(w->root);
    mon = win ? gdk_display_get_monitor_at_window(gtk_widget_get_display(w->root), win) : NULL;
  }
  if (!mon) return;
  GdkRectangle r;
  gdk_monitor_get_geometry(mon, &r);
  char *msg = g_strdup_printf("monitor %d %d %d %d\n", r.x, r.y, r.width, r.height);
  g_output_stream_write_all(w->in, msg, strlen(msg), NULL, NULL, NULL);
  g_free(msg);
}

static void on_map(GtkWidget *wd, gpointer data) { (void)wd; send_monitor(data); }

static void start(WS *w);

static gboolean restart_cb(gpointer data) {
  WS *w = data;
  w->restart_timer = 0;
  if (w->alive) start(w);
  return G_SOURCE_REMOVE;
}

static void got_line(GObject *src, GAsyncResult *res, gpointer data) {
  WS *w = data;
  GError *err = NULL;
  char *line = g_data_input_stream_read_line_finish_utf8(G_DATA_INPUT_STREAM(src), res, NULL, &err);
  if (!w->alive) { g_free(line); g_clear_error(&err); ws_unref(w); return; }
  if (line) {
    apply(w, line);
    g_free(line);
    g_data_input_stream_read_line_async(w->stream, G_PRIORITY_DEFAULT, w->cancel, got_line, w);
    return;
  }
  g_clear_error(&err);
  if (w->child) g_subprocess_force_exit(w->child);
  g_clear_object(&w->stream);
  g_clear_object(&w->in);
  g_clear_object(&w->child);
  if (!w->restart_timer) w->restart_timer = g_timeout_add_seconds(2, restart_cb, w);
  ws_unref(w);
}

static void start(WS *w) {
  GError *err = NULL;
  char *cmd = g_strconcat("exec ", w->command, NULL);
  w->child = g_subprocess_new(G_SUBPROCESS_FLAGS_STDOUT_PIPE | G_SUBPROCESS_FLAGS_STDIN_PIPE |
                              G_SUBPROCESS_FLAGS_STDERR_SILENCE,
                              &err, "/bin/sh", "-c", cmd, NULL);
  g_free(cmd);
  if (!w->child) {
    g_warning("workspaces-widget: %s", err->message);
    g_clear_error(&err);
    w->restart_timer = g_timeout_add_seconds(5, restart_cb, w);
    return;
  }
  w->in = g_object_ref(g_subprocess_get_stdin_pipe(w->child));
  w->stream = g_data_input_stream_new(g_subprocess_get_stdout_pipe(w->child));
  send_monitor(w);
  ++w->refs;
  g_data_input_stream_read_line_async(w->stream, G_PRIORITY_DEFAULT, w->cancel, got_line, w);
}

void *wbcffi_init(const wbcffi_init_info *info, const wbcffi_config_entry *e, size_t n) {
  const char *command = option(e, n, "exec", NULL);
  if (!command || !*command) return NULL;
  signal(SIGPIPE, SIG_IGN);
  WS *w = g_new0(WS, 1);
  w->refs = 1;
  w->alive = TRUE;
  w->command = g_strdup(command);
  w->cancel = g_cancellable_new();
  w->root = GTK_WIDGET(info->get_root_widget(info->obj));

  w->ebox = gtk_event_box_new();
  gtk_widget_add_events(w->ebox, GDK_SCROLL_MASK | GDK_SMOOTH_SCROLL_MASK);
  g_signal_connect(w->ebox, "scroll-event", G_CALLBACK(on_scroll), w);
  w->box = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 0);
  gtk_widget_set_name(w->box, "workspaces");
  gtk_container_add(GTK_CONTAINER(w->ebox), w->box);
  gtk_container_add(GTK_CONTAINER(w->root), w->ebox);
  gtk_widget_show_all(w->ebox);
  g_signal_connect(w->root, "map", G_CALLBACK(on_map), w);
  start(w);
  return w;
}

void wbcffi_deinit(void *instance) {
  WS *w = instance;
  if (!w) return;
  w->alive = FALSE;
  if (w->restart_timer) g_source_remove(w->restart_timer);
  g_signal_handlers_disconnect_by_data(w->root, w);
  g_cancellable_cancel(w->cancel);
  if (w->child) g_subprocess_force_exit(w->child);
  ws_unref(w);
}

void wbcffi_update(void *instance) { (void)instance; }
void wbcffi_refresh(void *instance, int signal_number) { (void)instance; (void)signal_number; }
void wbcffi_doaction(void *instance, const char *action) { (void)instance; (void)action; }
