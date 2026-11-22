/* Waybar CFFI "Spider-Sense" radar, fed by scripts/radar.py.
 *
 * A small spider-web radar: ink disc + blue misprint, octagonal web rings and
 * 8 spokes, a crimson sweep with a fading trail and a yellow leading edge.
 * Blips light up as the sweep passes over them and fade until the next pass;
 * "pulse" blips also throw out an expanding ring. Level changes the mood:
 *   calm   - slow crimson sweep
 *   alert  - faster sweep, yellow edge brighter
 *   danger - fast sweep, the rim flashes crimson / yellow
 *
 * Feed (one line per change):
 *   level \x1f tooltip-markup \x1f blips [\x1f badge \x1f focus(0|1)]
 *   badge: unread-notification count drawn as a yellow sticker (empty = none);
 *   focus: a purple dashed inner ring while a Focus / Do Not Disturb mode is on
 *   blips: entries joined by \x1d, each  angle_deg \x1c dist(0..1) \x1c #rrggbb \x1c pulse(0|1)
 * Config: "exec" (feed), "size" (px, default 30), "fps" (default 10), "on-click", "on-click-right" (shell commands).
 *
 * Build: sh ~/.config/hypr/waybar/cffi/build-radar-widget.sh
 */
#define _POSIX_C_SOURCE 200809L
#include <gtk/gtk.h>
#include <math.h>
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

#define MAX_BLIPS 16
typedef struct { double ang, dist, r, g, b; gboolean pulse; } Blip;

typedef struct {
  unsigned refs;
  gboolean alive;
  GtkWidget *root, *ebox, *area;
  GSubprocess *child;
  GDataInputStream *stream;
  GCancellable *cancel;
  guint restart_timer, tick;
  char *command, *click, *rclick;
  int size;
  int level;              /* 0 calm, 1 alert, 2 danger */
  double sweep;           /* degrees, 0 = up, clockwise */
  gint64 last_us;
  int nblips;
  Blip blips[MAX_BLIPS];
  char badge[8];
  gboolean focus;
  double badge_pop;       /* 1 -> 0: the badge "punches" in when the count goes up */
} Radar;

static void radar_unref(Radar *w) {
  if (--w->refs) return;
  g_clear_object(&w->child);
  g_clear_object(&w->stream);
  g_clear_object(&w->cancel);
  g_free(w->command);
  g_free(w->click);
  g_free(w->rclick);
  g_free(w);
}

static const char *option(const wbcffi_config_entry *e, size_t n, const char *key, const char *fb) {
  for (size_t i = 0; i < n; ++i)
    if (strcmp(e[i].key, key) == 0) return e[i].value;
  return fb;
}

/* waybar passes config values as JSON text: strip the quotes of a string value */
static char *unquote(const char *v) {
  if (!v) return NULL;
  size_t l = strlen(v);
  if (l >= 2 && v[0] == '"' && v[l - 1] == '"') return g_strndup(v + 1, l - 2);
  return g_strdup(v);
}

static void hex(const char *s, double *r, double *g, double *b) {
  unsigned v = 0xff1744;
  if (s && *s == '#') v = (unsigned)strtoul(s + 1, NULL, 16);
  *r = ((v >> 16) & 255) / 255.0; *g = ((v >> 8) & 255) / 255.0; *b = (v & 255) / 255.0;
}

/* ---------------------------------------------------------------- drawing */
static void octagon(cairo_t *cr, double cx, double cy, double rad) {
  for (int i = 0; i <= 8; ++i) {
    double a = (i * 45.0 + 22.5) * G_PI / 180.0;
    double x = cx + rad * cos(a), y = cy + rad * sin(a);
    if (i == 0) cairo_move_to(cr, x, y); else cairo_line_to(cr, x, y);
  }
  cairo_close_path(cr);
}

static gboolean on_draw(GtkWidget *wd, cairo_t *cr, gpointer data) {
  Radar *w = data;
  int W = gtk_widget_get_allocated_width(wd), H = gtk_widget_get_allocated_height(wd);
  double s = MIN(W, H) - 3.0;          /* leave room for the misprint */
  double R = s / 2.0, cx = (H - 2.0) / 2.0, cy = (H - 2.0) / 2.0;   /* disc left; the badge overlaps top-right */
  double t = g_get_monotonic_time() / 1e6;
  cairo_set_antialias(cr, CAIRO_ANTIALIAS_BEST);

  /* misprint + ink disc */
  cairo_arc(cr, cx + 2, cy + 2, R, 0, 2 * G_PI);
  cairo_set_source_rgba(cr, 0, 0.72, 1, 0.95);
  cairo_fill(cr);
  cairo_arc(cr, cx, cy, R, 0, 2 * G_PI);
  cairo_set_source_rgb(cr, 0.043, 0.035, 0.051);
  cairo_fill_preserve(cr);
  cairo_set_source_rgb(cr, 0.02, 0.012, 0.024);
  cairo_set_line_width(cr, 1.6);
  cairo_stroke(cr);

  /* web: octagon rings + spokes */
  cairo_save(cr);
  cairo_arc(cr, cx, cy, R - 1, 0, 2 * G_PI);
  cairo_clip(cr);
  cairo_set_line_width(cr, 0.8);
  cairo_set_source_rgba(cr, 1, 0.09, 0.27, 0.42);
  for (int k = 1; k <= 3; ++k) { octagon(cr, cx, cy, (R - 1) * k / 3.2); cairo_stroke(cr); }
  cairo_set_source_rgba(cr, 1, 0.09, 0.27, 0.28);
  for (int i = 0; i < 8; ++i) {
    double a = i * G_PI / 4;
    cairo_move_to(cr, cx, cy);
    cairo_line_to(cr, cx + R * cos(a), cy + R * sin(a));
    cairo_stroke(cr);
  }

  /* sweep trail: thin wedges fading behind the leading edge */
  double lead = (w->sweep - 90.0) * G_PI / 180.0;   /* 0deg = up */
  const int slices = 18;
  double trail = 70.0 * G_PI / 180.0;
  for (int i = 0; i < slices; ++i) {
    double a1 = lead - trail * i / slices, a0 = lead - trail * (i + 1) / slices;
    double alpha = 0.55 * (1.0 - (double)i / slices);
    cairo_move_to(cr, cx, cy);
    cairo_arc(cr, cx, cy, R, a0, a1);
    cairo_close_path(cr);
    if (w->level == 2) cairo_set_source_rgba(cr, 1, 0.83, 0.23, alpha);
    else cairo_set_source_rgba(cr, 1, 0.09, 0.27, alpha);
    cairo_fill(cr);
  }
  /* leading edge */
  cairo_set_line_width(cr, 1.4);
  cairo_set_source_rgba(cr, 1, 0.83, 0.23, w->level ? 1.0 : 0.85);
  cairo_move_to(cr, cx, cy);
  cairo_line_to(cr, cx + R * cos(lead), cy + R * sin(lead));
  cairo_stroke(cr);

  /* blips */
  for (int i = 0; i < w->nblips; ++i) {
    Blip *b = &w->blips[i];
    double behind = fmod(w->sweep - b->ang + 720.0, 360.0);   /* degrees since the sweep passed */
    double glow = 1.0 - behind / 360.0 * 0.75;
    double a = (b->ang - 90.0) * G_PI / 180.0;
    double d = CLAMP(b->dist, 0.12, 0.92) * (R - 2);
    double x = cx + d * cos(a), y = cy + d * sin(a);
    double br = MAX(1.6, R * 0.13);
    if (b->pulse) {   /* expanding ring, once per second */
      double ph = fmod(t, 1.0);
      cairo_arc(cr, x, y, br + ph * R * 0.45, 0, 2 * G_PI);
      cairo_set_source_rgba(cr, b->r, b->g, b->b, 0.7 * (1 - ph));
      cairo_set_line_width(cr, 1.0);
      cairo_stroke(cr);
    }
    cairo_arc(cr, x, y, br + 0.9, 0, 2 * G_PI);
    cairo_set_source_rgba(cr, 0.02, 0.012, 0.024, glow);
    cairo_fill(cr);
    cairo_arc(cr, x, y, br, 0, 2 * G_PI);
    cairo_set_source_rgba(cr, b->r, b->g, b->b, glow);
    cairo_fill(cr);
  }
  cairo_restore(cr);

  /* centre: the "spider" */
  cairo_arc(cr, cx, cy, MAX(1.4, R * 0.11), 0, 2 * G_PI);
  cairo_set_source_rgb(cr, 0.96, 0.94, 0.91);
  cairo_fill(cr);

  /* rim: crimson; in danger it flashes crimson/yellow */
  double rim = 1.3;
  if (w->level == 2) {
    gboolean on = fmod(t, 0.5) < 0.25;
    if (on) cairo_set_source_rgb(cr, 1, 0.83, 0.23); else cairo_set_source_rgb(cr, 1, 0.09, 0.27);
    rim = 2.0;
  } else if (w->level == 1) {
    cairo_set_source_rgb(cr, 1, 0.83, 0.23);
  } else {
    cairo_set_source_rgb(cr, 1, 0.09, 0.27);
  }
  cairo_set_line_width(cr, rim);
  cairo_arc(cr, cx, cy, R - rim / 2, 0, 2 * G_PI);
  cairo_stroke(cr);

  /* focus / do not disturb: purple dashed inner ring */
  if (w->focus) {
    static const double dash[] = {2.2, 1.6};
    cairo_set_dash(cr, dash, 2, -t * 4);
    cairo_set_source_rgb(cr, 0.545, 0.208, 1.0);
    cairo_set_line_width(cr, 1.3);
    cairo_arc(cr, cx, cy, R - 3.2, 0, 2 * G_PI);
    cairo_stroke(cr);
    cairo_set_dash(cr, NULL, 0, 0);
  }

  /* unread badge: yellow sticker, top-right, with an ink outline + crimson misprint */
  if (w->badge[0]) {
    double fs = MAX(7.0, R * 0.62);
    cairo_select_font_face(cr, "Bangers", CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL);
    cairo_set_font_size(cr, fs);
    cairo_text_extents_t te;
    cairo_text_extents(cr, w->badge, &te);
    double scale = 1.0 + 0.45 * w->badge_pop;
    double bh = fs * 1.05 * scale, bw = MAX(bh, (te.x_advance + fs * 0.5) * scale);
    double bx = W - bw - 0.5, by = 0.5;
    cairo_rectangle(cr, bx + 1.4, by + 1.4, bw, bh);
    cairo_set_source_rgb(cr, 1, 0.09, 0.27);
    cairo_fill(cr);
    cairo_rectangle(cr, bx, by, bw, bh);
    cairo_set_source_rgb(cr, 1, 0.83, 0.23);
    cairo_fill_preserve(cr);
    cairo_set_source_rgb(cr, 0.02, 0.012, 0.024);
    cairo_set_line_width(cr, 1.1);
    cairo_stroke(cr);
    cairo_set_font_size(cr, fs * scale);
    cairo_text_extents(cr, w->badge, &te);
    cairo_move_to(cr, bx + (bw - te.x_advance) / 2, by + bh / 2 + te.height / 2);
    cairo_show_text(cr, w->badge);
  }
  return FALSE;
}

static gboolean tick(gpointer data) {
  Radar *w = data;
  gint64 now = g_get_monotonic_time();
  double dt = (now - w->last_us) / 1e6;
  w->last_us = now;
  static const double period[3] = {3.6, 2.0, 1.0};   /* seconds per turn */
  w->sweep = fmod(w->sweep + 360.0 * dt / period[CLAMP(w->level, 0, 2)], 360.0);
  if (w->badge_pop > 0) w->badge_pop = MAX(0.0, w->badge_pop - dt * 3.0);
  if (gtk_widget_get_mapped(w->area)) gtk_widget_queue_draw(w->area);
  return G_SOURCE_CONTINUE;
}

/* ---------------------------------------------------------------- feed */
static void apply(Radar *w, const char *line) {
  char **f = g_strsplit(line, "\x1f", 5);
  if (!f[0]) { g_strfreev(f); return; }
  w->level = !strcmp(f[0], "danger") ? 2 : !strcmp(f[0], "alert") ? 1 : 0;
  GtkStyleContext *ctx = gtk_widget_get_style_context(w->ebox);
  gtk_style_context_remove_class(ctx, "calm");
  gtk_style_context_remove_class(ctx, "alert");
  gtk_style_context_remove_class(ctx, "danger");
  gtk_style_context_add_class(ctx, f[0]);
  if (f[1]) {
    char *tip = g_strdelimit(g_strdup(f[1]), "\x1e", '\n');
    gtk_widget_set_tooltip_markup(w->ebox, tip);
    g_free(tip);
  }
  w->nblips = 0;
  if (f[2] && *f[2]) {
    char **bl = g_strsplit(f[2], "\x1d", MAX_BLIPS);
    for (char **e = bl; *e && w->nblips < MAX_BLIPS; ++e) {
      char **p = g_strsplit(*e, "\x1c", 4);
      if (p[0] && p[1]) {
        Blip *b = &w->blips[w->nblips++];
        b->ang = g_ascii_strtod(p[0], NULL);
        b->dist = g_ascii_strtod(p[1], NULL);
        hex(p[2], &b->r, &b->g, &b->b);
        b->pulse = p[2] && p[3] && p[3][0] == '1';
      }
      g_strfreev(p);
    }
    g_strfreev(bl);
  }
  const char *nb = (f[2] && f[3]) ? f[3] : "";
  if (atoi(nb) > atoi(w->badge)) w->badge_pop = 1.0;
  g_strlcpy(w->badge, nb, sizeof w->badge);
  w->focus = f[2] && f[3] && f[4] && f[4][0] == '1';
  g_strfreev(f);
  gtk_widget_queue_draw(w->area);
}

static void start(Radar *w);

static gboolean restart_cb(gpointer data) {
  Radar *w = data;
  w->restart_timer = 0;
  if (w->alive) start(w);
  return G_SOURCE_REMOVE;
}

static void got_line(GObject *src, GAsyncResult *res, gpointer data) {
  Radar *w = data;
  GError *err = NULL;
  char *line = g_data_input_stream_read_line_finish_utf8(G_DATA_INPUT_STREAM(src), res, NULL, &err);
  if (!w->alive) { g_free(line); g_clear_error(&err); radar_unref(w); return; }
  if (line) {
    apply(w, line);
    g_free(line);
    g_data_input_stream_read_line_async(w->stream, G_PRIORITY_DEFAULT, w->cancel, got_line, w);
    return;
  }
  g_clear_error(&err);
  if (w->child) g_subprocess_force_exit(w->child);
  g_clear_object(&w->stream);
  g_clear_object(&w->child);
  if (!w->restart_timer) w->restart_timer = g_timeout_add_seconds(2, restart_cb, w);
  radar_unref(w);
}

static void start(Radar *w) {
  GError *err = NULL;
  char *cmd = g_strconcat("exec ", w->command, NULL);
  w->child = g_subprocess_new(G_SUBPROCESS_FLAGS_STDOUT_PIPE | G_SUBPROCESS_FLAGS_STDERR_SILENCE,
                              &err, "/bin/sh", "-c", cmd, NULL);
  g_free(cmd);
  if (!w->child) {
    g_warning("radar-widget: %s", err->message);
    g_clear_error(&err);
    w->restart_timer = g_timeout_add_seconds(5, restart_cb, w);
    return;
  }
  w->stream = g_data_input_stream_new(g_subprocess_get_stdout_pipe(w->child));
  ++w->refs;
  g_data_input_stream_read_line_async(w->stream, G_PRIORITY_DEFAULT, w->cancel, got_line, w);
}

static void run(const char *cmd) {
  if (!cmd || !*cmd) return;
  const char *argv[] = {"/bin/sh", "-c", cmd, NULL};
  g_spawn_async(NULL, (char **)argv, NULL, G_SPAWN_DEFAULT, NULL, NULL, NULL, NULL);
}

static gboolean on_press(GtkWidget *wd, GdkEventButton *ev, gpointer data) {
  (void)wd;
  Radar *w = data;
  if (ev->type != GDK_BUTTON_PRESS) return FALSE;
  if (ev->button == 1) run(w->click);
  else if (ev->button == 3) run(w->rclick);
  return TRUE;
}

void *wbcffi_init(const wbcffi_init_info *info, const wbcffi_config_entry *e, size_t n) {
  char *command = unquote(option(e, n, "exec", NULL));
  if (!command || !*command) { g_free(command); return NULL; }
  signal(SIGPIPE, SIG_IGN);
  Radar *w = g_new0(Radar, 1);
  w->refs = 1;
  w->alive = TRUE;
  w->command = command;
  w->click = unquote(option(e, n, "on-click", NULL));
  w->rclick = unquote(option(e, n, "on-click-right", NULL));
  const char *sz = option(e, n, "size", "30");
  w->size = CLAMP(atoi(sz), 16, 64);
  w->cancel = g_cancellable_new();
  w->root = GTK_WIDGET(info->get_root_widget(info->obj));

  w->ebox = gtk_event_box_new();
  gtk_widget_set_name(w->ebox, "radar");
  gtk_widget_add_events(w->ebox, GDK_BUTTON_PRESS_MASK);
  g_signal_connect(w->ebox, "button-press-event", G_CALLBACK(on_press), w);
  w->area = gtk_drawing_area_new();
  gtk_widget_set_size_request(w->area, w->size + 6, w->size + 2);
  gtk_widget_set_valign(w->area, GTK_ALIGN_CENTER);
  g_signal_connect(w->area, "draw", G_CALLBACK(on_draw), w);
  gtk_container_add(GTK_CONTAINER(w->ebox), w->area);
  gtk_container_add(GTK_CONTAINER(w->root), w->ebox);
  gtk_widget_set_tooltip_markup(w->ebox, "<b>SPIDER-SENSE</b>\nwarming up…");
  gtk_widget_show_all(w->ebox);
  w->last_us = g_get_monotonic_time();
  int fps = CLAMP(atoi(option(e, n, "fps", "10")), 4, 30);
  w->tick = g_timeout_add(1000 / fps, tick, w);   /* 10 fps default: smooth enough for a sweep, ~1-2 % CPU */
  start(w);
  return w;
}

void wbcffi_deinit(void *instance) {
  Radar *w = instance;
  if (!w) return;
  w->alive = FALSE;
  if (w->tick) g_source_remove(w->tick);
  if (w->restart_timer) g_source_remove(w->restart_timer);
  g_cancellable_cancel(w->cancel);
  if (w->child) g_subprocess_force_exit(w->child);
  radar_unref(w);
}

void wbcffi_update(void *instance) { (void)instance; }
void wbcffi_refresh(void *instance, int signal_number) { (void)instance; (void)signal_number; }
void wbcffi_doaction(void *instance, const char *action) { (void)instance; (void)action; }
