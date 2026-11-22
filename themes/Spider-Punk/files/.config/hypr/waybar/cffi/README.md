# Photo hover preview

`photo-preview.so` is a Waybar CFFI widget. It displays the existing shuffle
script's current photo as a circular, centered crop and a native GTK tooltip
with the full rectangular image and filename. Original photo files are unchanged.
The preview opens after 100 milliseconds on hover using the same tooltip behavior
as other Waybar widgets and closes when the pointer leaves. Clicking the thumbnail
opens the photo in the separate small viewer window.

Settings live in `UserModules` under `cffi/photos`:

- `size`: thumbnail size (28 pixels).
- `preview-width`, `preview-height`: maximum preview dimensions (400 × 300).
- `hover-delay`: milliseconds before showing the preview (100).
- `exec` contains `--delay 30`: seconds between shuffled photos.
- `interval`: seconds between checks for new photos (5).
- `on-click`: opens a floating photo window at the image's size, scaled down to
  fit the screen when necessary. Press Escape or the close button to dismiss it.

Rebuild after changing the C source:

```sh
sh ~/.config/hypr/waybar/cffi/build-photo-preview.sh
```

Requires a C compiler and GTK 3 development packages. The widget uses
[Waybar's CFFI ABI](https://github.com/Alexays/Waybar/blob/0.15.0/resources/custom_modules/cffi_example/waybar_cffi_module.h)
and GTK's native tooltip API.
No system Waybar files are modified.
