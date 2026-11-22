/* Waybar CFFI Spotify widget: rounded album-art thumbnail + track/lyric label,
 * and a hover pop-down with the large cover, track info and synced lyrics.
 *
 * Feeds from a long-running helper (`exec`), one record per line:
 *   class \x1f cover-path \x1f bar-markup \x1f tooltip-markup \x1f track-key   (\x1e = newline)
 * When track-key changes the contents cross-fade (fade out, swap, fade + slide in).
 * Helper: ~/.config/hypr/waybar/scripts/spotify.py status --cffi
 * ABI: https://github.com/Alexays/Waybar/blob/0.15.0/resources/custom_modules/cffi_example/waybar_cffi_module.h
 * Build: sh ~/.config/hypr/waybar/cffi/build-spotify-widget.sh
 */
#include <gtk/gtk.h>
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
  gboolean alive, hovered, tooltip_requested;
  GtkWidget *root, *box, *thumb, *glyph, *label;
  GtkWidget *preview, *cover, *info;
  GSubprocess *child;
  GDataInputStream *stream;
  GCancellable *cancel;
  guint hover_timer, restart_timer, tick_id;
  int phase;                       /* 0 idle, 1 fading out, 2 fading in */
  gint64 anim_start, thumb_start;  /* frame-clock µs; thumb_start 0 = no thumb fade */
  char *key, *pending;
  char *hide_group;               /* name of an ancestor box to hide while idle */
  int size, cover_size, hover_delay, max_chars, label_chars;
  char *command, *cover_path, *klass;
} Spot;

static void spot_unref(Spot *s) {
  if (--s->refs) return;
  g_clear_object(&s->child);
  g_clear_object(&s->stream);
  g_clear_object(&s->cancel);
  g_clear_object(&s->preview);
  g_free(s->command);
  g_free(s->cover_path);
  g_free(s->klass);
  g_free(s->key);
  g_free(s->pending);
  g_free(s->hide_group);
  g_free(s);
}

static const char *option(const wbcffi_config_entry *e, size_t n, const char *key, const char *fb) {
  for (size_t i = 0; i < n; ++i)
    if (strcmp(e[i].key, key) == 0) return e[i].value;
  return fb;
}

static int number(const wbcffi_config_entry *e, size_t n, const char *key, int fb, int max) {
  const char *v = option(e, n, key, NULL);
  if (!v) return fb;
  gint64 x = g_ascii_strtoll(v, NULL, 10);
  return x > 0 && x <= max ? (int)x : fb;
}

/* Square, center-cropped image with rounded corners (radius in logical px). */
static gboolean set_rounded(GtkWidget *image, const char *path, int size, double radius) {
  int scale = gtk_widget_get_scale_factor(image);
  int px = size * scale, w = 0, h = 0;
  if (!gdk_pixbuf_get_file_info(path, &w, &h) || w <= 0 || h <= 0) return FALSE;
  GError *err = NULL;
  GdkPixbuf *pix = gdk_pixbuf_new_from_file_at_scale(path, w >= h ? -1 : px, w >= h ? px : -1,
                                                     TRUE, &err);
  if (!pix) { g_clear_error(&err); return FALSE; }
  cairo_surface_t *surf = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, px, px);
  cairo_t *cr = cairo_create(surf);
  double r = radius * scale;
  cairo_new_sub_path(cr);
  cairo_arc(cr, px - r, r, r, -G_PI / 2, 0);
  cairo_arc(cr, px - r, px - r, r, 0, G_PI / 2);
  cairo_arc(cr, r, px - r, r, G_PI / 2, G_PI);
  cairo_arc(cr, r, r, r, G_PI, 3 * G_PI / 2);
  cairo_close_path(cr);
  cairo_clip(cr);
  gdk_cairo_set_source_pixbuf(cr, pix, (px - gdk_pixbuf_get_width(pix)) / 2.0,
                              (px - gdk_pixbuf_get_height(pix)) / 2.0);
  cairo_paint(cr);
  cairo_destroy(cr);
  cairo_surface_set_device_scale(surf, scale, scale);
  gtk_image_set_from_surface(GTK_IMAGE(image), surf);
  cairo_surface_destroy(surf);
  g_object_unref(pix);
  return TRUE;
}

static void set_class(Spot *s, const char *klass) {
  if (!g_strcmp0(s->klass, klass)) return;
  GtkStyleContext *ctx = gtk_widget_get_style_context(s->box);
  if (s->klass && *s->klass) gtk_style_context_remove_class(ctx, s->klass);
  if (klass && *klass) gtk_style_context_add_class(ctx, klass);
  g_free(s->klass);
  s->klass = g_strdup(klass);
  /* nothing playing: hide the whole island (e.g. the "media" group with the visualizer) */
  if (s->hide_group && *s->hide_group) {
    for (GtkWidget *w = gtk_widget_get_parent(s->root); w; w = gtk_widget_get_parent(w)) {
      if (!g_strcmp0(gtk_widget_get_name(w), s->hide_group)) {
        gtk_widget_set_visible(w, g_strcmp0(klass, "idle") != 0);
        break;
      }
    }
  }
}

static gboolean apply(Spot *s, const char *line) {
  gboolean cover_changed = FALSE;
  char **f = g_strsplit(line, "\x1f", 5);
  if (g_strv_length(f) >= 4) {
    if (f[4]) { g_free(s->key); s->key = g_strdup(f[4]); }
    g_strdelimit(f[3], "\x1e", '\n');
    set_class(s, f[0]);
    const char *cover = f[1];
    if (*cover && g_strcmp0(cover, s->cover_path) != 0) {
      if (set_rounded(s->thumb, cover, s->size, s->size * 0.22) &&
          set_rounded(s->cover, cover, s->cover_size, 14)) {
        g_free(s->cover_path);
        s->cover_path = g_strdup(cover);
        cover_changed = TRUE;
      }
    } else if (!*cover && s->cover_path) {
      g_clear_pointer(&s->cover_path, g_free);
    }
    gboolean has_cover = s->cover_path != NULL;
    gtk_widget_set_visible(s->thumb, has_cover);
    gtk_widget_set_visible(s->glyph, !has_cover);
    gtk_widget_set_visible(s->cover, has_cover);
    gtk_label_set_markup(GTK_LABEL(s->label), f[2]);
    gtk_widget_set_visible(s->label, *f[2] != '\0');
    gtk_label_set_markup(GTK_LABEL(s->info), f[3]);
  }
  g_strfreev(f);
  return cover_changed;
}

/* ---- song-change animation ---- */
#define OUT_US 170000.0
#define IN_US  320000.0
#define THUMB_US 260000.0
#define SLIDE_PX 14.0

static double ease_out(double t) { t = 1 - t; return 1 - t * t * t; }
static double ease_in(double t) { return t * t; }

static void set_fade(Spot *s, double opacity, double slide) {
  gtk_widget_set_opacity(s->thumb, opacity);
  gtk_widget_set_opacity(s->glyph, opacity);
  gtk_widget_set_opacity(s->label, opacity);
  gtk_widget_set_margin_start(s->label, (int)(slide + 0.5));
}

static gboolean tick(GtkWidget *w, GdkFrameClock *clock, gpointer data) {
  (void)w;
  Spot *s = data;
  gint64 now = gdk_frame_clock_get_frame_time(clock);
  if (s->phase == 1) {
    double t = (now - s->anim_start) / OUT_US;
    if (t < 1) {
      set_fade(s, 1 - ease_in(t), 0);
    } else {
      if (s->pending) { apply(s, s->pending); g_clear_pointer(&s->pending, g_free); }
      s->phase = 2;
      s->anim_start = now;
      s->thumb_start = 0;
      set_fade(s, 0, SLIDE_PX);
    }
  } else if (s->phase == 2) {
    double t = (now - s->anim_start) / IN_US;
    if (t < 1) {
      double e = ease_out(t);
      set_fade(s, e, (1 - e) * SLIDE_PX);
    } else {
      set_fade(s, 1, 0);
      s->phase = 0;
    }
  }
  if (s->phase == 0 && s->thumb_start) {
    double t = (now - s->thumb_start) / THUMB_US;
    if (t < 1) gtk_widget_set_opacity(s->thumb, ease_out(t));
    else { gtk_widget_set_opacity(s->thumb, 1); s->thumb_start = 0; }
  }
  if (s->phase == 0 && !s->thumb_start) { s->tick_id = 0; return G_SOURCE_REMOVE; }
  return G_SOURCE_CONTINUE;
}

static void ensure_tick(Spot *s) {
  if (!s->tick_id) s->tick_id = gtk_widget_add_tick_callback(s->box, tick, s, NULL);
}

static void on_line(Spot *s, const char *line) {
  const char *k = strrchr(line, '\x1f');
  int fields = 1;
  for (const char *c = line; *c; ++c) fields += *c == '\x1f';
  const char *key = fields >= 5 && k ? k + 1 : "";
  gboolean changed = *key && s->key && *s->key && strcmp(key, s->key) != 0;
  gboolean can_animate = gtk_widget_get_mapped(s->box);

  if (can_animate && (changed || s->phase == 1)) {
    g_free(s->pending);
    s->pending = g_strdup(line);
    if (s->phase != 1) {
      s->phase = 1;
      s->anim_start = gdk_frame_clock_get_frame_time(gtk_widget_get_frame_clock(s->box));
      s->thumb_start = 0;
      ensure_tick(s);
    }
    return;
  }
  gboolean cover_changed = apply(s, line);
  if (!can_animate) { set_fade(s, 1, 0); s->phase = 0; return; }
  /* cover that arrives after the swap (download finished) fades in by itself */
  if (cover_changed && s->phase == 0) {
    gtk_widget_set_opacity(s->thumb, 0);
    s->thumb_start = gdk_frame_clock_get_frame_time(gtk_widget_get_frame_clock(s->box));
    ensure_tick(s);
  }
}

static void start(Spot *s);

static gboolean restart_cb(gpointer data) {
  Spot *s = data;
  s->restart_timer = 0;
  if (s->alive) start(s);
  return G_SOURCE_REMOVE;
}

static void got_line(GObject *src, GAsyncResult *res, gpointer data) {
  Spot *s = data;
  GError *err = NULL;
  gsize len = 0;
  char *line = g_data_input_stream_read_line_finish_utf8(G_DATA_INPUT_STREAM(src), res, &len, &err);
  if (!s->alive) { g_free(line); g_clear_error(&err); spot_unref(s); return; }
  if (line) {
    on_line(s, line);
    g_free(line);
    g_data_input_stream_read_line_async(s->stream, G_PRIORITY_DEFAULT, s->cancel, got_line, s);
    return;  /* keeps its reference */
  }
  /* EOF or error: helper died, restart it shortly. */
  g_clear_error(&err);
  if (s->child) g_subprocess_force_exit(s->child);
  g_clear_object(&s->stream);
  g_clear_object(&s->child);
  if (!s->restart_timer) s->restart_timer = g_timeout_add_seconds(3, restart_cb, s);
  spot_unref(s);
}

static void start(Spot *s) {
  GError *err = NULL;
  char *cmd = g_strconcat("exec ", s->command, NULL);
  s->child = g_subprocess_new(G_SUBPROCESS_FLAGS_STDOUT_PIPE | G_SUBPROCESS_FLAGS_STDERR_SILENCE,
                              &err, "/bin/sh", "-c", cmd, NULL);
  g_free(cmd);
  if (!s->child) {
    g_warning("spotify-widget: %s", err->message);
    g_clear_error(&err);
    s->restart_timer = g_timeout_add_seconds(5, restart_cb, s);
    return;
  }
  s->stream = g_data_input_stream_new(g_subprocess_get_stdout_pipe(s->child));
  ++s->refs;
  g_data_input_stream_read_line_async(s->stream, G_PRIORITY_DEFAULT, s->cancel, got_line, s);
}

/* ---- hover pop-down (native GTK tooltip, like the photo widget) ---- */
static gboolean show_preview(gpointer data) {
  Spot *s = data;
  s->hover_timer = 0;
  if (!s->alive || !s->hovered) return G_SOURCE_REMOVE;
  s->tooltip_requested = TRUE;
  gtk_widget_trigger_tooltip_query(s->root);
  return G_SOURCE_REMOVE;
}

static gboolean query_tooltip(GtkWidget *w, gint x, gint y, gboolean kb, GtkTooltip *tip, gpointer data) {
  (void)w; (void)x; (void)y; (void)kb;
  Spot *s = data;
  if (!s->alive || !s->hovered || !s->tooltip_requested) return FALSE;
  gtk_tooltip_set_custom(tip, s->preview);
  gtk_widget_show(s->preview);
  return TRUE;
}

static gboolean on_enter(GtkWidget *w, GdkEventCrossing *ev, gpointer data) {
  (void)w;
  Spot *s = data;
  if (ev->detail == GDK_NOTIFY_INFERIOR) return FALSE;
  s->hovered = TRUE;
  if (!s->hover_timer && !s->tooltip_requested)
    s->hover_timer = g_timeout_add(s->hover_delay, show_preview, s);
  return FALSE;
}

static gboolean on_motion(GtkWidget *w, GdkEventMotion *ev, gpointer data) {
  (void)w; (void)ev;
  Spot *s = data;
  if (!s->alive) return FALSE;
  s->hovered = TRUE;
  if (!s->hover_timer && !s->tooltip_requested)
    s->hover_timer = g_timeout_add(s->hover_delay, show_preview, s);
  return FALSE;
}

static gboolean on_leave(GtkWidget *w, GdkEventCrossing *ev, gpointer data) {
  (void)w;
  Spot *s = data;
  if (ev->detail == GDK_NOTIFY_INFERIOR) return FALSE;
  s->hovered = FALSE;
  if (s->hover_timer) g_source_remove(s->hover_timer);
  s->hover_timer = 0;
  s->tooltip_requested = FALSE;
  return FALSE;
}

static const char *CSS =
  "#spotify-cffi { padding: 2px 10px 2px 4px; border-radius: 12px;"
  "  transition: background-color 450ms ease, border-color 450ms ease;"
  "  background-color: rgba(29,185,84,0.12); border: 1px solid rgba(29,185,84,0.35); }"
  "#spotify-cffi.paused { background-color: rgba(255,255,255,0.05); border-color: rgba(255,255,255,0.12); }"
  "#spotify-cffi.idle { padding: 2px 8px; }"
  "#spotify-cffi.login, #spotify-cffi.offline { border-style: dashed; }"
  "#spotify-glyph { color: #1DB954; font-size: 15px; }"
  "#spotify-preview { background: rgba(18,18,22,0.97); color: #f2f2f2;"
  "  border: 1px solid rgba(29,185,84,0.35); border-radius: 18px; }"
  "#spotify-preview label { color: #f2f2f2; }";

static void add_css(GtkWidget *w, GtkCssProvider *css) {
  gtk_style_context_add_provider(gtk_widget_get_style_context(w), GTK_STYLE_PROVIDER(css),
                                 GTK_STYLE_PROVIDER_PRIORITY_APPLICATION);
}

void *wbcffi_init(const wbcffi_init_info *info, const wbcffi_config_entry *e, size_t n) {
  const char *command = option(e, n, "exec", NULL);
  if (!command || !*command) return NULL;
  Spot *s = g_new0(Spot, 1);
  s->refs = 1;
  s->alive = TRUE;
  s->command = g_strdup(command);
  s->cancel = g_cancellable_new();
  s->size = number(e, n, "size", 22, 128);
  s->cover_size = number(e, n, "cover-size", 280, 1000);
  s->hover_delay = number(e, n, "hover-delay", 150, 5000);
  s->max_chars = number(e, n, "tooltip-width-chars", 34, 200);
  s->label_chars = number(e, n, "label-chars", 40, 200);
  s->root = GTK_WIDGET(info->get_root_widget(info->obj));
  s->hide_group = g_strdup(option(e, n, "hide-group-when-idle", ""));

  GtkCssProvider *css = gtk_css_provider_new();
  gtk_css_provider_load_from_data(css, CSS, -1, NULL);

  s->box = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 7);
  gtk_widget_set_name(s->box, "spotify-cffi");
  add_css(s->box, css);
  s->thumb = gtk_image_new();
  gtk_widget_set_size_request(s->thumb, s->size, s->size);
  gtk_widget_set_valign(s->thumb, GTK_ALIGN_CENTER);
  s->glyph = gtk_label_new("\xef\x86\xbc");  /* U+F1BC nf-fa-spotify */
  gtk_widget_set_name(s->glyph, "spotify-glyph");
  add_css(s->glyph, css);
  s->label = gtk_label_new(NULL);
  /* fixed width: the widget never grows/shrinks with lyric length */
  gtk_label_set_width_chars(GTK_LABEL(s->label), s->label_chars);
  gtk_label_set_max_width_chars(GTK_LABEL(s->label), s->label_chars);
  gtk_label_set_ellipsize(GTK_LABEL(s->label), PANGO_ELLIPSIZE_END);
  gtk_label_set_xalign(GTK_LABEL(s->label), 0.0);
  gtk_box_pack_start(GTK_BOX(s->box), s->thumb, FALSE, FALSE, 0);
  gtk_box_pack_start(GTK_BOX(s->box), s->glyph, FALSE, FALSE, 0);
  gtk_box_pack_start(GTK_BOX(s->box), s->label, FALSE, FALSE, 0);
  gtk_container_add(GTK_CONTAINER(s->root), s->box);

  s->preview = gtk_box_new(GTK_ORIENTATION_VERTICAL, 12);
  g_object_ref_sink(s->preview);
  gtk_widget_set_name(s->preview, "spotify-preview");
  add_css(s->preview, css);
  gtk_container_set_border_width(GTK_CONTAINER(s->preview), 14);
  s->cover = gtk_image_new();
  gtk_widget_set_size_request(s->cover, s->cover_size, s->cover_size);
  s->info = gtk_label_new(NULL);
  add_css(s->info, css);
  gtk_label_set_line_wrap(GTK_LABEL(s->info), TRUE);
  gtk_label_set_line_wrap_mode(GTK_LABEL(s->info), PANGO_WRAP_WORD_CHAR);
  gtk_label_set_max_width_chars(GTK_LABEL(s->info), s->max_chars);
  gtk_label_set_justify(GTK_LABEL(s->info), GTK_JUSTIFY_CENTER);
  gtk_box_pack_start(GTK_BOX(s->preview), s->cover, FALSE, FALSE, 0);
  gtk_box_pack_start(GTK_BOX(s->preview), s->info, FALSE, FALSE, 0);
  gtk_widget_show(s->info);
  g_object_unref(css);

  gtk_widget_set_has_tooltip(s->root, TRUE);
  g_signal_connect(s->root, "query-tooltip", G_CALLBACK(query_tooltip), s);
  gtk_widget_add_events(s->root, GDK_ENTER_NOTIFY_MASK | GDK_LEAVE_NOTIFY_MASK | GDK_POINTER_MOTION_MASK);
  g_signal_connect(s->root, "enter-notify-event", G_CALLBACK(on_enter), s);
  g_signal_connect(s->root, "leave-notify-event", G_CALLBACK(on_leave), s);
  g_signal_connect(s->root, "motion-notify-event", G_CALLBACK(on_motion), s);

  gtk_widget_show_all(s->box);
  gtk_widget_hide(s->thumb);
  start(s);
  return s;
}

void wbcffi_deinit(void *instance) {
  Spot *s = instance;
  if (!s) return;
  s->alive = FALSE;
  if (s->hover_timer) g_source_remove(s->hover_timer);
  if (s->restart_timer) g_source_remove(s->restart_timer);
  if (s->tick_id) gtk_widget_remove_tick_callback(s->box, s->tick_id);
  g_signal_handlers_disconnect_by_data(s->root, s);
  gtk_widget_set_has_tooltip(s->root, FALSE);
  g_cancellable_cancel(s->cancel);
  if (s->child) g_subprocess_force_exit(s->child);
  spot_unref(s);
}

void wbcffi_update(void *instance) { (void)instance; }
void wbcffi_refresh(void *instance, int signal_number) { (void)instance; (void)signal_number; }
void wbcffi_doaction(void *instance, const char *action) { (void)instance; (void)action; }
