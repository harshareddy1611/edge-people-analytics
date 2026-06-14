# Ad media folders

Each subfolder here is an ad category, matching the categories in
`shared/config.py`'s `AD_CATEGORIES` mapping (plus `default`).

Drop image files (`.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`) into the
matching folder. The ad viewer slideshows through all images in a
folder, advancing every `AD_SLIDE_SECS` seconds (see `shared/config.py`).

Expected folders based on the current `AD_CATEGORIES`:

- `gym/`
- `beauty_salon/`
- `finance/`
- `lifestyle/`
- `gaming/`
- `healthcare/`
- `default/`  — shown when the selected category has no images, or
  when no ad selection has been made yet

You don't need to create every folder up front — categories without
images automatically fall back to `default/`. At minimum, add a few
images to `default/` so the viewer always has something to show.
