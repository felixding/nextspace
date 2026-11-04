# Original title references

These fixed metrics and lossless 1× glyph images come from the original Window
Maker width/shortening code and Xft rendering. Native compositor output is never
used to generate them. The manifest records the original source hashes, font
bytes, Fontconfig options, library versions and every reference file hash.
The generated C retains the original authors' license notices.

`title_layout.py` and `title_appearance.py` use these references without an X
server. They retain the original shortening, exact 100% pixel comparisons,
Fontconfig preference cases and all five native densities. A changed source,
font selection or reference file requires an explicit baseline review.

For reference maintenance only, use a Debian 13 environment with the original
GNUstep Helvetica fonts, DejaVu fonts, Xft development files and Xvfb:

```sh
python3 Tests/Wayland/generate_title_reference.py \
  --repo . --output /tmp/nextspace-original-title-reference
```

The output directory must be new. Compare it with the checked-in manifest and
images before replacing this baseline. Xvfb is optional reference-generation
tooling and is not needed by native CI or the desktop packages.
