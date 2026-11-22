/* Waybar CFFI "menu widget": a bar label that drops down a native GTK menu on
 * left click (the same kind of menu nm-applet shows for Wi-Fi).
 *
 * A long-running helper (`exec`) writes one record per line on stdout:
 *   class \x1f bar-markup \x1f tooltip-markup \x1f menu [\x1f hover-markup]
 * hover-markup (optional) slides out next to the bar text while the pointer is over it.
 * menu = entries separated by \x1d; entry fields separated by \x1c:
 *   header \x1c markup                      greyed section title
 *   item   \x1c markup \x1c command          click runs `sh -c command`
 *   check  \x1c markup \x1c command \x1c 1|0 check item (toggle)
 *   note   \x1c markup                      greyed, informational
 *   sub    \x1c markup   ...entries...  end  submenu
 *   sep                                     separator
 * In all fields \x1e stands for a newline.
 * The widget writes "open\n" / "close\n" to the helper's stdin when the menu
 * is shown / hidden; while it is open, new records rebuild the menu live.
 *
 * Build: sh ~/.config/hypr/waybar/cffi/build-menu-widget.sh
 * ABI: https://github.com/Alexays/Waybar/blob/0.15.0/resources/custom_modules/cffi_example/waybar_cffi_module.h
 */
#define _POSIX_C_SOURCE 200809L
#include <gtk/gtk.h>
#include <signal.h>
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
  gboolean alive, building;
  GtkWidget *root, *box, *label, *menu, *reveal, *extra;   /* extra: slides out on hover */
  GSubprocess *child;
  GDataInputStream *stream;
  GOutputStream *in;
  GCancellable *cancel;
  guint restart_timer, hover_timer;
  char *command, *klass, *spec, *sig;   /* sig: structure of the built menu */
} MW;

static void mw_unref(MW *m) {
  if (--m->refs) return;
  g_clear_object(&m->child);
  g_clear_object(&m->stream);
  g_clear_object(&m->in);
  g_clear_object(&m->cancel);
  g_free(m->command);
  g_free(m->klass);
  g_free(m->spec);
  g_free(m->sig);
  g_free(m);
}

static const char *option(const wbcffi_config_entry *e, size_t n, const char *key, const char *fb) {
  for (size_t i = 0; i < n; ++i)
    if (strcmp(e[i].key, key) == 0) return e[i].value;
  return fb;
}

static void tell(MW *m, const char *msg) {
  if (m->in) g_output_stream_write_all(m->in, msg, strlen(msg), NULL, NULL, NULL);
}

/* ---------------- menu ---------------- */
static void run_cmd(GtkMenuItem *item, gpointer data) {
  (void)data;
  if (GTK_IS_CHECK_MENU_ITEM(item) && g_object_get_data(G_OBJECT(item), "mw-building")) return;
  const char *cmd = g_object_get_data(G_OBJECT(item), "mw-cmd");
  if (!cmd || !*cmd) return;
  GError *err = NULL;
  const char *argv[] = {"/bin/sh", "-c", cmd, NULL};
  if (!g_spawn_async(NULL, (char **)argv, NULL, G_SPAWN_DEFAULT, NULL, NULL, NULL, &err)) {
    g_warning("menu-widget: %s", err->message);
    g_clear_error(&err);
  }
}

static GtkWidget *labelled(GtkWidget *item, const char *markup) {
  GtkWidget *child = gtk_bin_get_child(GTK_BIN(item));
  if (!GTK_IS_LABEL(child)) {
    child = gtk_label_new(NULL);
    gtk_container_add(GTK_CONTAINER(item), child);
  }
  gtk_label_set_markup(GTK_LABEL(child), markup);
  gtk_label_set_xalign(GTK_LABEL(child), 0.0);
  return item;
}

static void fill(MW *m, GtkWidget *menu, const char *spec) {
  GList *kids = gtk_container_get_children(GTK_CONTAINER(menu));
  for (GList *k = kids; k; k = k->next) gtk_widget_destroy(k->data);
  g_list_free(kids);

  GPtrArray *stack = g_ptr_array_new();
  GtkWidget *cur = menu;
  char **entries = g_strsplit(spec ? spec : "", "\x1d", -1);
  for (char **e = entries; *e; ++e) {
    if (!**e) continue;
    char **f = g_strsplit(*e, "\x1c", 4);
    for (char **x = f; *x; ++x) g_strdelimit(*x, "\x1e", '\n');
    const char *kind = f[0], *markup = f[1] ? f[1] : "", *cmd = f[1] && f[2] ? f[2] : "";
    GtkWidget *item = NULL;
    if (!strcmp(kind, "sep")) {
      item = gtk_separator_menu_item_new();
    } else if (!strcmp(kind, "header") || !strcmp(kind, "note")) {
      item = labelled(gtk_menu_item_new(), markup);
      gtk_widget_set_sensitive(item, FALSE);
    } else if (!strcmp(kind, "item")) {
      item = labelled(gtk_menu_item_new(), markup);
      g_object_set_data_full(G_OBJECT(item), "mw-cmd", g_strdup(cmd), g_free);
      g_signal_connect(item, "activate", G_CALLBACK(run_cmd), m);
    } else if (!strcmp(kind, "check")) {
      item = labelled(gtk_check_menu_item_new(), markup);
      g_object_set_data(G_OBJECT(item), "mw-building", GINT_TO_POINTER(1));
      gtk_check_menu_item_set_active(GTK_CHECK_MENU_ITEM(item), f[1] && f[2] && f[3] && f[3][0] == '1');
      g_object_set_data(G_OBJECT(item), "mw-building", NULL);
      g_object_set_data_full(G_OBJECT(item), "mw-cmd", g_strdup(cmd), g_free);
      g_signal_connect(item, "toggled", G_CALLBACK(run_cmd), m);
    } else if (!strcmp(kind, "sub")) {
      item = labelled(gtk_menu_item_new(), markup);
      gtk_menu_shell_append(GTK_MENU_SHELL(cur), item);
      GtkWidget *submenu = gtk_menu_new();
      gtk_menu_item_set_submenu(GTK_MENU_ITEM(item), submenu);
      g_ptr_array_add(stack, cur);
      cur = submenu;
      item = NULL;
    } else if (!strcmp(kind, "end")) {
      if (stack->len) cur = g_ptr_array_steal_index(stack, stack->len - 1);
    }
    if (item) gtk_menu_shell_append(GTK_MENU_SHELL(cur), item);
    g_strfreev(f);
  }
  g_strfreev(entries);
  g_ptr_array_free(stack, TRUE);
  gtk_widget_show_all(menu);
}

/* structure of a spec: the kinds of all entries, e.g. "header,check,sep,sub,item,end,…" */
static char *signature(const char *spec) {
  GString *g = g_string_new(NULL);
  char **entries = g_strsplit(spec ? spec : "", "\x1d", -1);
  for (char **e = entries; *e; ++e) {
    if (!**e) continue;
    const char *end = strchr(*e, '\x1c');
    g_string_append_len(g, *e, end ? (gssize)(end - *e) : (gssize)strlen(*e));
    g_string_append_c(g, ',');
  }
  g_strfreev(entries);
  return g_string_free(g, FALSE);
}

/* Same structure as what is shown: only refresh labels / check marks / commands,
 * so hover highlight and open submenus survive live updates. */
static int update_items(GtkWidget *menu, char **entries, int i) {
  GList *kids = gtk_container_get_children(GTK_CONTAINER(menu)), *k = kids;
  while (entries[i]) {
    if (!*entries[i]) { ++i; continue; }
    char **f = g_strsplit(entries[i], "\x1c", 4);
    for (char **x = f; *x; ++x) g_strdelimit(*x, "\x1e", '\n');
    const char *kind = f[0];
    if (!strcmp(kind, "end")) { g_strfreev(f); ++i; break; }
    if (!k) { g_strfreev(f); break; }
    GtkWidget *item = k->data;
    k = k->next;
    if (strcmp(kind, "sep")) {
      GtkWidget *lab = gtk_bin_get_child(GTK_BIN(item));
      if (GTK_IS_LABEL(lab) && f[1] && g_strcmp0(gtk_label_get_label(GTK_LABEL(lab)), f[1]))
        gtk_label_set_markup(GTK_LABEL(lab), f[1]);
      if ((!strcmp(kind, "item") || !strcmp(kind, "check")) && f[1] && f[2])
        g_object_set_data_full(G_OBJECT(item), "mw-cmd", g_strdup(f[2]), g_free);
      if (!strcmp(kind, "check") && f[1] && f[2] && f[3]) {
        gboolean want = f[3][0] == '1';
        if (gtk_check_menu_item_get_active(GTK_CHECK_MENU_ITEM(item)) != want) {
          g_object_set_data(G_OBJECT(item), "mw-building", GINT_TO_POINTER(1));
          gtk_check_menu_item_set_active(GTK_CHECK_MENU_ITEM(item), want);
          g_object_set_data(G_OBJECT(item), "mw-building", NULL);
        }
      }
      if (!strcmp(kind, "sub")) {
        GtkWidget *sub = gtk_menu_item_get_submenu(GTK_MENU_ITEM(item));
        g_strfreev(f);
        i = sub ? update_items(sub, entries, i + 1) : i + 1;
        continue;
      }
    }
    g_strfreev(f);
    ++i;
  }
  g_list_free(kids);
  return i;
}

static void refresh_open_menu(MW *m) {
  char *sig = signature(m->spec);
  if (!g_strcmp0(sig, m->sig)) {
    char **entries = g_strsplit(m->spec ? m->spec : "", "\x1d", -1);
    update_items(m->menu, entries, 0);
    g_strfreev(entries);
    g_free(sig);
  } else {
    fill(m, m->menu, m->spec);   /* items added/removed: rebuild */
    g_free(m->sig);
    m->sig = sig;
  }
}

static void on_menu_hide(GtkWidget *w, gpointer data) {
  (void)w;
  tell(data, "close\n");
}

static gboolean on_press(GtkWidget *w, GdkEventButton *ev, gpointer data) {
  (void)w;
  MW *m = data;
  if (ev->type != GDK_BUTTON_PRESS || ev->button != 1) return FALSE;
  fill(m, m->menu, m->spec);
  g_free(m->sig);
  m->sig = signature(m->spec);
  tell(m, "open\n");
  gtk_menu_popup_at_widget(GTK_MENU(m->menu), m->box, GDK_GRAVITY_SOUTH_WEST,
                           GDK_GRAVITY_NORTH_WEST, (GdkEvent *)ev);
  return TRUE;
}

/* hover: slide the optional extra text out / back in.
 * Leaving starts a short timer; entering any of our windows cancels it, so moving
 * between the outer and inner event boxes doesn't flicker, and leaving the bar
 * entirely (where GTK may report stale coordinates) still hides it. */
static gboolean hover_off(gpointer data) {
  MW *m = data;
  m->hover_timer = 0;
  gtk_revealer_set_reveal_child(GTK_REVEALER(m->reveal), FALSE);
  return G_SOURCE_REMOVE;
}

static gboolean on_hover(GtkWidget *w, GdkEventCrossing *ev, gpointer data) {
  (void)w;
  MW *m = data;
  if (ev->type == GDK_ENTER_NOTIFY) {
    if (m->hover_timer) { g_source_remove(m->hover_timer); m->hover_timer = 0; }
    const char *t = gtk_label_get_text(GTK_LABEL(m->extra));
    if (t && *t) gtk_revealer_set_reveal_child(GTK_REVEALER(m->reveal), TRUE);
  } else if (ev->detail != GDK_NOTIFY_INFERIOR && !m->hover_timer) {
    m->hover_timer = g_timeout_add(150, hover_off, m);
  }
  return FALSE;
}

/* ---------------- feed ---------------- */
static void set_class(MW *m, const char *klass) {
  if (!g_strcmp0(m->klass, klass)) return;
  GtkStyleContext *ctx = gtk_widget_get_style_context(m->box);
  /* the class field may hold several space-separated classes (e.g. "connected s3") */
  if (m->klass && *m->klass) {
    char **old = g_strsplit(m->klass, " ", -1);
    for (char **c = old; *c; ++c) if (**c) gtk_style_context_remove_class(ctx, *c);
    g_strfreev(old);
  }
  if (klass && *klass) {
    char **nw = g_strsplit(klass, " ", -1);
    for (char **c = nw; *c; ++c) if (**c) gtk_style_context_add_class(ctx, *c);
    g_strfreev(nw);
  }
  g_free(m->klass);
  m->klass = g_strdup(klass);
}

static void apply(MW *m, const char *line) {
  char **f = g_strsplit(line, "\x1f", 5);
  if (g_strv_length(f) >= 3) {
    g_strdelimit(f[1], "\x1e", '\n');
    g_strdelimit(f[2], "\x1e", '\n');
    set_class(m, f[0]);
    gtk_label_set_markup(GTK_LABEL(m->label), f[1]);
    const char *hover = (f[3] && f[4]) ? f[4] : "";
    gtk_label_set_markup(GTK_LABEL(m->extra), hover);
    if (!*hover) gtk_revealer_set_reveal_child(GTK_REVEALER(m->reveal), FALSE);
    gtk_widget_set_tooltip_markup(m->box, *f[2] ? f[2] : NULL);
    const char *spec = f[3] ? f[3] : "";
    if (g_strcmp0(spec, m->spec)) {
      g_free(m->spec);
      m->spec = g_strdup(spec);
      if (gtk_widget_get_visible(m->menu)) refresh_open_menu(m);  /* live update, keeps hover */
    }
  }
  g_strfreev(f);
}

static void start(MW *m);

static gboolean restart_cb(gpointer data) {
  MW *m = data;
  m->restart_timer = 0;
  if (m->alive) start(m);
  return G_SOURCE_REMOVE;
}

static void got_line(GObject *src, GAsyncResult *res, gpointer data) {
  MW *m = data;
  GError *err = NULL;
  char *line = g_data_input_stream_read_line_finish_utf8(G_DATA_INPUT_STREAM(src), res, NULL, &err);
  if (!m->alive) { g_free(line); g_clear_error(&err); mw_unref(m); return; }
  if (line) {
    apply(m, line);
    g_free(line);
    g_data_input_stream_read_line_async(m->stream, G_PRIORITY_DEFAULT, m->cancel, got_line, m);
    return;
  }
  g_clear_error(&err);
  if (m->child) g_subprocess_force_exit(m->child);
  g_clear_object(&m->stream);
  g_clear_object(&m->in);
  g_clear_object(&m->child);
  if (!m->restart_timer) m->restart_timer = g_timeout_add_seconds(3, restart_cb, m);
  mw_unref(m);
}

static void start(MW *m) {
  GError *err = NULL;
  char *cmd = g_strconcat("exec ", m->command, NULL);
  m->child = g_subprocess_new(G_SUBPROCESS_FLAGS_STDOUT_PIPE | G_SUBPROCESS_FLAGS_STDIN_PIPE |
                              G_SUBPROCESS_FLAGS_STDERR_SILENCE, &err, "/bin/sh", "-c", cmd, NULL);
  g_free(cmd);
  if (!m->child) {
    g_warning("menu-widget: %s", err->message);
    g_clear_error(&err);
    m->restart_timer = g_timeout_add_seconds(5, restart_cb, m);
    return;
  }
  m->in = g_object_ref(g_subprocess_get_stdin_pipe(m->child));
  m->stream = g_data_input_stream_new(g_subprocess_get_stdout_pipe(m->child));
  ++m->refs;
  g_data_input_stream_read_line_async(m->stream, G_PRIORITY_DEFAULT, m->cancel, got_line, m);
}

void *wbcffi_init(const wbcffi_init_info *info, const wbcffi_config_entry *e, size_t n) {
  const char *command = option(e, n, "exec", NULL);
  if (!command || !*command) return NULL;
  signal(SIGPIPE, SIG_IGN);  /* never let a dead helper's stdin kill waybar */
  MW *m = g_new0(MW, 1);
  m->refs = 1;
  m->alive = TRUE;
  m->command = g_strdup(command);
  m->cancel = g_cancellable_new();
  m->root = GTK_WIDGET(info->get_root_widget(info->obj));

  m->box = gtk_event_box_new();
  gtk_widget_set_name(m->box, option(e, n, "name", "menu-widget"));
  m->label = gtk_label_new(NULL);
  GtkWidget *row = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 0);
  gtk_box_pack_start(GTK_BOX(row), m->label, FALSE, FALSE, 0);
  m->reveal = gtk_revealer_new();
  gtk_revealer_set_transition_type(GTK_REVEALER(m->reveal), GTK_REVEALER_TRANSITION_TYPE_SLIDE_RIGHT);
  gtk_revealer_set_transition_duration(GTK_REVEALER(m->reveal), 220);
  m->extra = gtk_label_new(NULL);
  gtk_widget_set_name(m->extra, "hover");
  gtk_container_add(GTK_CONTAINER(m->reveal), m->extra);
  gtk_box_pack_start(GTK_BOX(row), m->reveal, FALSE, FALSE, 0);
  gtk_container_add(GTK_CONTAINER(m->box), row);
  gtk_widget_add_events(m->box, GDK_ENTER_NOTIFY_MASK | GDK_LEAVE_NOTIFY_MASK);
  g_signal_connect(m->box, "enter-notify-event", G_CALLBACK(on_hover), m);
  g_signal_connect(m->box, "leave-notify-event", G_CALLBACK(on_hover), m);
  /* also the module's own event box (outer container), like the Spotify widget's hover */
  gtk_widget_add_events(m->root, GDK_ENTER_NOTIFY_MASK | GDK_LEAVE_NOTIFY_MASK);
  g_signal_connect(m->root, "enter-notify-event", G_CALLBACK(on_hover), m);
  g_signal_connect(m->root, "leave-notify-event", G_CALLBACK(on_hover), m);
  gtk_container_add(GTK_CONTAINER(m->root), m->box);
  gtk_widget_add_events(m->box, GDK_BUTTON_PRESS_MASK);
  g_signal_connect(m->box, "button-press-event", G_CALLBACK(on_press), m);

  m->menu = gtk_menu_new();
  g_object_ref_sink(m->menu);
  gtk_menu_set_reserve_toggle_size(GTK_MENU(m->menu), TRUE);
  g_signal_connect(m->menu, "hide", G_CALLBACK(on_menu_hide), m);

  gtk_widget_show_all(m->box);
  start(m);
  return m;
}

void wbcffi_deinit(void *instance) {
  MW *m = instance;
  if (!m) return;
  m->alive = FALSE;
  if (m->restart_timer) g_source_remove(m->restart_timer);
  if (m->hover_timer) g_source_remove(m->hover_timer);
  g_signal_handlers_disconnect_by_data(m->root, m);
  g_signal_handlers_disconnect_by_data(m->menu, m);
  gtk_widget_destroy(m->menu);
  g_object_unref(m->menu);
  g_cancellable_cancel(m->cancel);
  if (m->child) g_subprocess_force_exit(m->child);
  mw_unref(m);
}

void wbcffi_update(void *instance) { (void)instance; }
void wbcffi_refresh(void *instance, int signal_number) { (void)instance; (void)signal_number; }
void wbcffi_doaction(void *instance, const char *action) { (void)instance; (void)action; }
