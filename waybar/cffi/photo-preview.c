/* Waybar CFFI photo widget with a native GTK hover preview.
 * ABI: https://github.com/Alexays/Waybar/blob/0.15.0/resources/custom_modules/cffi_example/waybar_cffi_module.h
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

/* ABI 1 supplies string configuration values without JSON quoting. */
const size_t wbcffi_version = 1;

typedef struct {
  unsigned refs;
  gboolean alive, hovered;
  GtkWidget *root, *hover_widget, *image, *preview, *preview_image, *caption;
  GSubprocess *child;
  guint timer, hover_timer;
  gboolean tooltip_requested;
  int size, preview_width, preview_height, hover_delay;
  char *command, *path;
} Photos;

static void photos_unref(Photos *p) {
  if (--p->refs) return;
  g_clear_object(&p->child);
  g_clear_object(&p->preview);
  g_free(p->command);
  g_free(p->path);
  g_free(p);
}

static const char *option(const wbcffi_config_entry *entries, size_t len,
                          const char *key, const char *fallback) {
  for (size_t i = 0; i < len; ++i)
    if (strcmp(entries[i].key, key) == 0) return entries[i].value;
  return fallback;
}

static int number(const wbcffi_config_entry *entries, size_t len,
                  const char *key, int fallback, int maximum) {
  const char *value = option(entries, len, key, NULL);
  if (!value) return fallback;
  gint64 parsed = g_ascii_strtoll(value, NULL, 10);
  return parsed > 0 && parsed <= maximum ? (int)parsed : fallback;
}

static cairo_surface_t *circle_surface(GdkPixbuf *pixels, int size, int scale) {
  int diameter = size * scale;
  cairo_surface_t *surface = cairo_image_surface_create(CAIRO_FORMAT_ARGB32,
                                                        diameter, diameter);
  cairo_t *cr = cairo_create(surface);
  cairo_set_antialias(cr, CAIRO_ANTIALIAS_BEST);
  cairo_arc(cr, diameter / 2.0, diameter / 2.0, diameter / 2.0, 0, 2 * G_PI);
  cairo_clip(cr);
  /* Fill the circle with a centered crop, preserving the photo's proportions. */
  gdk_cairo_set_source_pixbuf(cr, pixels,
      (diameter - gdk_pixbuf_get_width(pixels)) / 2.0,
      (diameter - gdk_pixbuf_get_height(pixels)) / 2.0);
  cairo_paint(cr);
  cairo_destroy(cr);
  cairo_surface_set_device_scale(surface, scale, scale);
  return surface;
}

static gboolean set_photo(GtkWidget *image, const char *path, int width, int height,
                           gboolean circular) {
  GError *error = NULL;
  int scale = gtk_widget_get_scale_factor(image);
  int load_width = width * scale, load_height = height * scale;
  if (circular) {
    int original_width = 0, original_height = 0;
    gdk_pixbuf_get_file_info(path, &original_width, &original_height);
    /* Scale the shorter side to the diameter so the crop has no empty bands. */
    if (original_width >= original_height) load_width = -1;
    else load_height = -1;
  }
  GdkPixbuf *pixels = gdk_pixbuf_new_from_file_at_scale(
      path, load_width, load_height, TRUE, &error);
  if (!pixels) {
    g_warning("photo-preview: %s", error ? error->message : "cannot load image");
    g_clear_error(&error);
    return FALSE;
  }
  cairo_surface_t *surface = circular ? circle_surface(pixels, width, scale)
      : gdk_cairo_surface_create_from_pixbuf(pixels, scale, NULL);
  gtk_image_set_from_surface(GTK_IMAGE(image), surface);
  cairo_surface_destroy(surface);
  g_object_unref(pixels);
  return TRUE;
}

static gboolean show_preview(gpointer data) {
  Photos *p = data;
  p->hover_timer = 0;
  if (!p->alive || !p->hovered || !p->path) return G_SOURCE_REMOVE;
  /* Ask GTK to display the widget through its native tooltip window. This
   * follows the same hover placement and animation used by calendar tooltips. */
  p->tooltip_requested = TRUE;
  gtk_widget_trigger_tooltip_query(p->root);
  return G_SOURCE_REMOVE;
}

static gboolean query_tooltip(GtkWidget *widget, gint x, gint y,
                              gboolean keyboard, GtkTooltip *tooltip,
                              gpointer data) {
  (void)widget; (void)x; (void)y; (void)keyboard;
  Photos *p = data;
  if (!p->alive || !p->hovered || !p->tooltip_requested || !p->path) return FALSE;
  gtk_tooltip_set_custom(tooltip, p->preview);
  gtk_widget_show_all(p->preview);
  return TRUE;
}

static gboolean pointer_enter(GtkWidget *widget, GdkEventCrossing *event, gpointer data) {
  (void)widget;
  Photos *p = data;
  if (event->detail == GDK_NOTIFY_INFERIOR) return FALSE;
  p->hovered = TRUE;
  if (!p->hover_timer && !p->tooltip_requested)
    p->hover_timer = g_timeout_add(p->hover_delay, show_preview, p);
  return FALSE;
}

static gboolean pointer_motion(GtkWidget *widget, GdkEventMotion *event, gpointer data) {
  (void)widget; (void)event;
  Photos *p = data;
  if (!p->alive) return FALSE;
  p->hovered = TRUE;
  if (!p->hover_timer && !p->tooltip_requested)
    p->hover_timer = g_timeout_add(p->hover_delay, show_preview, p);
  return FALSE;
}

static gboolean pointer_leave(GtkWidget *widget, GdkEventCrossing *event, gpointer data) {
  (void)widget;
  Photos *p = data;
  if (event->detail == GDK_NOTIFY_INFERIOR) return FALSE;
  p->hovered = FALSE;
  if (p->hover_timer) g_source_remove(p->hover_timer);
  p->hover_timer = 0;
  p->tooltip_requested = FALSE;
  return FALSE;
}

static void fetched(GObject *source, GAsyncResult *result, gpointer data) {
  Photos *p = data;
  char *output = NULL;
  GError *error = NULL;
  gboolean ok = g_subprocess_communicate_utf8_finish(
      G_SUBPROCESS(source), result, &output, NULL, &error);
  if (p->alive && ok && g_subprocess_get_successful(G_SUBPROCESS(source)) && output) {
    /* The existing shuffle script returns the image path on its first line. */
    char *newline = strchr(output, '\n');
    if (newline) *newline = '\0';
    if (*output && g_strcmp0(output, p->path) != 0 &&
        set_photo(p->image, output, p->size, p->size, TRUE)) {
      if (set_photo(p->preview_image, output, p->preview_width, p->preview_height, FALSE)) {
        char *name = g_filename_display_basename(output);
        gtk_label_set_text(GTK_LABEL(p->caption), name);
        g_free(name);
        g_free(p->path);
        p->path = g_strdup(output);
    if (p->hovered && !p->hover_timer) show_preview(p);
      }
    }
  } else if (p->alive) {
    g_warning("photo-preview: shuffle command failed%s%s",
              error ? ": " : "", error ? error->message : "");
  }
  g_clear_error(&error);
  g_free(output);
  g_clear_object(&p->child);
  photos_unref(p);
}

static gboolean fetch(gpointer data) {
  Photos *p = data;
  if (!p->alive) return G_SOURCE_REMOVE;
  if (p->child) return G_SOURCE_CONTINUE;
  GError *error = NULL;
  /* exec ensures deinit terminates the helper rather than just its shell. */
  char *command = g_strconcat("exec ", p->command, NULL);
  p->child = g_subprocess_new(G_SUBPROCESS_FLAGS_STDOUT_PIPE |
                            G_SUBPROCESS_FLAGS_STDERR_SILENCE,
                            &error, "/bin/sh", "-c", command, NULL);
  g_free(command);
  if (!p->child) {
    g_warning("photo-preview: %s", error->message);
    g_clear_error(&error);
    return G_SOURCE_CONTINUE;
  }
  ++p->refs;
  g_subprocess_communicate_utf8_async(p->child, NULL, NULL, fetched, p);
  return G_SOURCE_CONTINUE;
}

void *wbcffi_init(const wbcffi_init_info *info, const wbcffi_config_entry *entries,
                  size_t len) {
  const char *command = option(entries, len, "exec", NULL);
  if (!command || !*command) return NULL;
  Photos *p = g_new0(Photos, 1);
  p->refs = 1;
  p->alive = TRUE;
  p->command = g_strdup(command);
  p->size = number(entries, len, "size", 28, 256);
  p->preview_width = number(entries, len, "preview-width", 320, 1600);
  p->preview_height = number(entries, len, "preview-height", 240, 1200);
  p->hover_delay = number(entries, len, "hover-delay", 100, 5000);
  p->root = GTK_WIDGET(info->get_root_widget(info->obj));

  GtkWidget *box = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 0);
  gtk_widget_set_name(box, "image");
  gtk_style_context_add_class(gtk_widget_get_style_context(box), "photos");
  p->image = gtk_image_new();
  gtk_widget_set_size_request(p->image, p->size, p->size);
  gtk_box_pack_start(GTK_BOX(box), p->image, FALSE, FALSE, 0);
  gtk_container_add(GTK_CONTAINER(p->root), box);
  p->hover_widget = box;

  p->preview = gtk_box_new(GTK_ORIENTATION_VERTICAL, 8);
  g_object_ref_sink(p->preview);
  gtk_widget_set_name(p->preview, "photo-preview");
  gtk_container_set_border_width(GTK_CONTAINER(p->preview), 8);
  p->preview_image = gtk_image_new();
  p->caption = gtk_label_new(NULL);
  gtk_label_set_ellipsize(GTK_LABEL(p->caption), PANGO_ELLIPSIZE_MIDDLE);
  gtk_label_set_max_width_chars(GTK_LABEL(p->caption), 36);
  gtk_box_pack_start(GTK_BOX(p->preview), p->preview_image, FALSE, FALSE, 0);
  gtk_box_pack_start(GTK_BOX(p->preview), p->caption, FALSE, FALSE, 0);
  /* The preview remains unparented until GTK reparents it into the native
   * tooltip window from query-tooltip. */
  gtk_widget_show_all(p->preview);
  /* Keep the preview readable even in themes that reset all widget colors. */
  GtkCssProvider *css = gtk_css_provider_new();
  gtk_css_provider_load_from_data(css,
      "#photo-preview { background: rgba(24,24,30,0.97); color: #f5f5f5;"
      " border: 1px solid rgba(180,180,200,0.35); border-radius: 12px; }"
      "#photo-preview label { color: #f5f5f5; font-size: 12px; }", -1, NULL);
  gtk_style_context_add_provider(gtk_widget_get_style_context(p->preview),
      GTK_STYLE_PROVIDER(css), GTK_STYLE_PROVIDER_PRIORITY_APPLICATION + 1);
  gtk_style_context_add_provider(gtk_widget_get_style_context(p->caption),
      GTK_STYLE_PROVIDER(css), GTK_STYLE_PROVIDER_PRIORITY_APPLICATION + 1);
  g_object_unref(css);
  gtk_widget_set_has_tooltip(p->root, TRUE);
  g_signal_connect(p->root, "query-tooltip", G_CALLBACK(query_tooltip), p);
  gtk_widget_add_events(p->root, GDK_ENTER_NOTIFY_MASK | GDK_LEAVE_NOTIFY_MASK |
                        GDK_POINTER_MOTION_MASK);
  gtk_widget_add_events(p->hover_widget, GDK_ENTER_NOTIFY_MASK | GDK_LEAVE_NOTIFY_MASK |
                        GDK_POINTER_MOTION_MASK);
  g_signal_connect(p->root, "enter-notify-event", G_CALLBACK(pointer_enter), p);
  g_signal_connect(p->root, "leave-notify-event", G_CALLBACK(pointer_leave), p);
  g_signal_connect(p->hover_widget, "enter-notify-event", G_CALLBACK(pointer_enter), p);
  g_signal_connect(p->hover_widget, "leave-notify-event", G_CALLBACK(pointer_leave), p);
  g_signal_connect(p->root, "motion-notify-event", G_CALLBACK(pointer_motion), p);
  g_signal_connect(p->hover_widget, "motion-notify-event", G_CALLBACK(pointer_motion), p);
  gtk_widget_show_all(box);
  p->timer = g_timeout_add_seconds(number(entries, len, "interval", 5, 3600), fetch, p);
  fetch(p);
  return p;
}

void wbcffi_deinit(void *instance) {
  Photos *p = instance;
  if (!p) return;
  p->alive = FALSE;
  if (p->timer) g_source_remove(p->timer);
  if (p->hover_timer) g_source_remove(p->hover_timer);
  g_signal_handlers_disconnect_by_data(p->root, p);
  gtk_widget_set_has_tooltip(p->root, FALSE);
  if (p->child) g_subprocess_force_exit(p->child);
  photos_unref(p);
}

/* Export every hook: Waybar versions differ in handling omitted hooks. */
void wbcffi_update(void *instance) { (void)instance; }
void wbcffi_refresh(void *instance, int signal_number) {
  (void)signal_number;
  fetch(instance);
}
void wbcffi_doaction(void *instance, const char *action) {
  (void)instance; (void)action;
}
