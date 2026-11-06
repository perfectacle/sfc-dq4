"""Night colours of the environment palettes, following FC DQ4's night palettes.

FC turns a map to night by picking another colour set (0E:$BBE6, map type * 2 + night). Over every map type the day
colours change by kind (dq4block.palette with $62ED = 0 against 80):

  greys 00, 10        -> teal 0C, 1C          greens 1A, 2A, 1B -> darker teal 0A, 0C, 0B
  white 30            -> pale blue 21          cream road 38, 37 -> olive 28/18, 27
  blues 12, 21, 02    -> black or dark blue    warm 15, 17, 27, 25 -> the same hue one step darker 05, 07, 17, 15

The port's colours are DQ5's brighter ones, so each colour takes the change of its kind in HSV rather than the NES
colour: walls and grass go teal like FC, while floors and furniture keep their hue and only darken a little.
Water goes to a dark blue instead of FC's black so the waves still show.
"""

import colorsys

# Saturation below this is a grey. The port's stone greys are warm (saturation up to about 0.25), and FC turns them
# teal like its neutral greys; a lower bound left the castle walls grey.
GREY = 0.3


def night_rgb(rgb):
    """Night 8-bit (r, g, b) of a day 8-bit colour."""
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    hue = h * 360
    if 40 <= hue < 70 and s > 0.08:
        v, s = v * 0.62, min(1.0, s * 1.6 + 0.15)
    elif s < GREY and v > 0.8:
        h, s, v = 0.56, 0.5, v * 0.8
    elif s < GREY:
        h, s, v = 0.52, 0.85, min(1.0, v * 0.9)
    elif 70 <= hue < 170:
        h, v, s = (hue + (180 - hue) * 0.75) / 360, v * 0.5, min(1.0, s * 1.05)
    elif 170 <= hue < 260:
        v *= 0.45
    else:
        v *= 0.68
    return tuple(int(round(c * 255)) for c in colorsys.hsv_to_rgb(h, s, v))


def _sfc(rgb):
    """The colour as the SFC shows it: 5 bits per channel, widened back like the palettes (v << 3 | v >> 2)."""
    return [(c >> 3) << 3 | c >> 5 for c in rgb]


def night_flat(flat):
    """Flat 768-entry palette like palette_variant's with BG lines 1-7 turned to night. Colour 0 of each line
    (transparent) and lines 0 and 8 up stay."""
    out = list(flat)
    for index in range(16, 128):
        if index & 15:
            out[index * 3:index * 3 + 3] = _sfc(night_rgb(tuple(flat[index * 3:index * 3 + 3])))
    return out
