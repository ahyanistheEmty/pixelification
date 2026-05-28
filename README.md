# Pixelification

A terminal tool that rearranges pixels from a source image to approximate a target image using optimal transport via color sorting — then animates each pixel physically sliding to its new position.

No new pixels are created. Every pixel in the output comes from the source image, just rearranged.

## How it works

1. **Sort pixels** by (luminance, hue, saturation) — both source and target
2. **Map by rank** — the *n*th darkest source pixel maps to the *n*th darkest target position
3. **Animate** — each display pixel slides from its source position to its target position via linear interpolation, rendered with a per-pixel scatter (`np.add.at`)

## Usage

```bash
python rearrange_pixels_tui.py
```

A keyboard-navigated terminal interface opens. Use arrow keys to select images, press Enter to run.

```
↑↓  navigate  •  Enter  select  •  1-4  shortcut  •  q  quit
```

An OpenCV window opens with three panels:

| Source | Target | Reconstruction |
|--------|--------|----------------|
| Your image | Layout to approximate | Pixels sliding into place |

Press `ESC` or `q` during the animation to quit.

## Requirements

- Python 3.10+
- OpenCV (`cv2`)
- NumPy
- `prompt_toolkit`

```bash
pip install opencv-python numpy prompt_toolkit
```
