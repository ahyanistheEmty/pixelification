<div align="center">

```
██████╗ ██╗██╗  ██╗███████╗██╗     ██╗███████╗██╗ ██████╗ █████╗ ████████╗██╗ ██████╗ ███╗   ██╗
██╔══██╗██║╚██╗██╔╝██╔════╝██║     ██║██╔════╝██║██╔════╝██╔══██╗╚══██╔══╝██║██╔═══██╗████╗  ██║
██████╔╝██║ ╚███╔╝ █████╗  ██║     ██║█████╗  ██║██║     ███████║   ██║   ██║██║   ██║██╔██╗ ██║
██╔═══╝ ██║ ██╔██╗ ██╔══╝  ██║     ██║██╔══╝  ██║██║     ██╔══██║   ██║   ██║██║   ██║██║╚██╗██║
██║     ██║██╔╝ ██╗███████╗███████╗██║██║     ██║╚██████╗██║  ██║   ██║   ██║╚██████╔╝██║ ╚████║
╚═╝     ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝╚═╝     ╚═╝ ╚═════╝╚═╝  ╚═╝   ╚═╝   ╚═╝ ╚═════╝ ╚═╝  ╚═══╝
```

**No pixels created. No pixels destroyed. Only rearranged.**

[![Python](https://img.shields.io/badge/Python-3.10+-1a1a2e?style=for-the-badge&logo=python&logoColor=e94560)](https://python.org)
[![PyPI](https://img.shields.io/badge/PyPI-pixelification-1a1a2e?style=for-the-badge&logo=pypi&logoColor=e94560)](https://pypi.org/project/pixelification)
[![CUDA](https://img.shields.io/badge/CUDA-13-1a1a2e?style=for-the-badge&logo=nvidia&logoColor=76b900)](https://developer.nvidia.com/cuda-toolkit)
[![License](https://img.shields.io/badge/License-MIT-1a1a2e?style=for-the-badge)](LICENSE)

</div>

---

## ◈ What Is This?

**Pixelification** is a terminal tool built on a single elegant constraint:

> *Every pixel in the output must come from the source. Nothing is invented.*

It uses **optimal transport via colour sorting** to rearrange pixels — either between two images or across video frames — creating hypnotic, mathematically-grounded transformations. Think of it as a pixel teleporter: your source image's pixels physically migrate to approximate the structure of a target.

---

## ◈ Modes

### ▸ Image Mode

Rearrange pixels from a **source image** to approximate the layout of a **target image**, then watch a 60-frame pixel-sliding animation.

```
┌──────────────────────────────────────────────────────────────────────┐
│                                                                        │
│   SOURCE            TARGET            RECONSTRUCTION                  │
│   ┌──────┐          ┌──────┐          ┌──────┐                       │
│   │ 🌆   │          │ 🌊   │          │ ✦ ✦  │  ← pixels sliding    │
│   │      │ ──────▶  │      │ ──────▶  │  ✦   │    into place        │
│   │      │          │      │          │ ✦  ✦ │                       │
│   └──────┘          └──────┘          └──────┘                       │
│                                                                        │
└──────────────────────────────────────────────────────────────────────┘
```

**How it works — in three steps:**

```
  1  ╔═══════════════════╗    2  ╔═══════════════════╗    3  ╔════════════════════╗
     ║   SORT BY COLOUR  ║       ║   MAP BY RANK     ║       ║   ANIMATE          ║
     ║                   ║       ║                   ║       ║                    ║
     ║  lum → hue → sat  ║  ──▶  ║  rank i (source)  ║  ──▶  ║  60-frame lerp     ║
     ║                   ║       ║  → position of    ║       ║  all pixels move   ║
     ║  darkest  = 0     ║       ║  rank i (target)  ║       ║  simultaneously    ║
     ║  lightest = N-1   ║       ║                   ║       ║                    ║
     ╚═══════════════════╝       ╚═══════════════════╝       ╚════════════════════╝
```

| Step | What happens |
|------|-------------|
| **Sort** | Every pixel in both images is ranked by luminance, then hue, then saturation |
| **Map** | Source pixel with rank *i* teleports to where target pixel with rank *i* lives |
| **Animate** | Each pixel slides from origin to destination over 60 frames via linear interpolation |

> When multiple pixels land on the same display cell, their colours are averaged — a natural blending effect.

---

### ▸ Video Mode

Rearrange every frame of a **source video** (or a still image looped as a video) to match the frames of a **target video**.

```
  Frame 0  ──[sort]──┬──[rank-map]──▶  Output Frame 0 ──┐
  Frame 1  ──[sort]──┼──[rank-map]──▶  Output Frame 1   ├──▶  video file
    ...              │                      ...          │
  Frame N  ──[sort]──┴──[rank-map]──▶  Output Frame N ──┘
```

**Key differences from Image Mode:**

| Feature | Image Mode | Video Mode |
|---------|-----------|-----------|
| Animation | 60-frame pixel-slide | None — direct sort + write |
| Aspect ratio handling | N/A | Black bars to preserve content |
| Still image as source | ✗ | ✓ looped for every target frame |
| Progress feedback | Visual window | Terminal progress bar |

```
Status: Video: [████████████░░░░░░] 62.0% (124/200)
```

---

## ◈ Installation

### From PyPI

```bash
pip install pixelification
```

Then run:

```bash
pixelification
```

Or skip the install entirely:

```bash
pipx run pixelification
```

---

## ◈ Hardware Support

| Platform | Acceleration | Notes |
|----------|-------------|-------|
| **NVIDIA GPU** | ✅ CUDA 13 | Full GPU acceleration via `cupy-cuda13x[ctk]` |
| **Intel CPU/GPU** | ⚡ CPU (NumPy) | Automatic fallback, no extra packages needed |

> On first launch, Pixelification writes a small runtime config to your OS config directory with the detected hardware-acceleration flag. It just works.

---

## ◈ Usage

A keyboard-navigated terminal UI opens immediately:

```
  ■ Pixel Rearrangement Tool

  ● Rearrange Images    sort pixels between two images
  ○ Rearrange Videos    sort frames between two videos
  ○ Quit                exit the application
```

### Keyboard Controls

| Key | Action |
|-----|--------|
| `↑` `↓` | Navigate menu items |
| `Enter` | Select highlighted item |
| `1`–`N` | Jump directly to item *N* |
| `q` / `Esc` | Quit |

### Image Mode

1. Select your source image
2. Select your target image
3. Watch the rearrangement play out in an OpenCV window — three panels: **Source · Target · Reconstruction**
4. Press `ESC` or `q` to quit the animation
5. Click **"Save Result Image"** to export a PNG

### Video Mode

1. Select a source video (or still image — it'll be looped)
2. Select a target video
3. Watch the terminal progress bar as frames are processed
4. Result plays in an OpenCV window — loops until `ESC`/`q` or window close
5. Click **"Save Result Video"** to export

---

## ◈ Requirements

```
Python     ≥ 3.10
OpenCV     cv2
NumPy
prompt_toolkit

# Optional — installed automatically on supported platforms:
cupy-cuda13x[ctk]    # NVIDIA CUDA acceleration (Linux / Windows)
python3-tk           # Linux only — for file dialog fallback
                     # sudo apt install python3-tk
```

---

## ◈ Rust Component

The codebase also includes **Aster Browser** — a Rust-based Win32 application.

> ⚠️ Windows only.

```bash
cargo build --release
```

---

## ◈ The Algorithm (Deep Dive)

For the curious: this is **discrete optimal transport** solved via sorting. The classical OT problem asks *"how do I move mass from distribution A to distribution B at minimum cost?"* When cost = squared distance and both distributions have the same total mass, the solution on a 1D sorted line is simply to pair the *i*th element of one with the *i*th element of the other.

Pixelification extends this to colour space: pixels are projected onto a 1D ordering by `(luminance, hue, saturation)`, making the sort a tractable proxy for true 2D optimal transport. The result is perceptually coherent pixel migration — similar tones find similar homes.

```
flowchart LR
    A[Source Image] --> C[lexsort\nlum → hue → sat]
    B[Target Image] --> D[lexsort\nlum → hue → sat]
    C --> E[s_order]
    D --> F[t_order]
    E --> G[forward mapping\nforward at s_order = t_order]
    F --> G
    G --> H[per-pixel position lerp]
    H --> I[scatter render\nnp.add.at]
    I --> J[60-frame animation]
```

---

<div align="center">

*Every pixel has a story. This tool just reassigns the ending.*

</div>