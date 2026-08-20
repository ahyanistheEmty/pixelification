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

### ▸ ASCII Art Mode

Turn any image into **terminal ASCII art** — a scrollable character-based rendering using 10 luminance levels with auto-contrast and Floyd-Steinberg dithering.

```
  ┌─────────────────────────────────────────────────────────────┐
  │  @@@@@@%####****+==--::..          Shift+arrows scroll      │
  │  @@@%%%###***+++==--::..           PgUp/PgDn jump          │
  │  @%@%%%####***+++==--::..            10 levels + dither    │
  │  @@@%%%###***+++==--::..                                   │
  └─────────────────────────────────────────────────────────────┘
```

**How it works:**

| Step | What happens |
|------|-------------|
| **Read** | Image loaded via OpenCV, converted to luminance using Rec. 601 `(0.299R + 0.587G + 0.114B)` |
| **Contrast** | Histogram stretched to full 0–255 range for maximum tonal depth |
| **Resize** | Aspect-corrected resize (0.55 char ratio) to fit terminal width |
| **Dither** | Floyd-Steinberg error diffusion distributes quantization error across neighboring pixels |
| **Map** | Each pixel's brightness mapped to one of 10 characters `@%#*+=-:. ` sorted by ink coverage |

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

### ▸ Audio Mode

Rearrange audio between two files. By default it performs **spectral cross-synthesis**
– the source's pitch/timbre are preserved while its spectral structure is reshaped
toward the target. A **time-domain** cut-and-splice mode, pitch shifting, and more are
available via the **Advanced Audio Options** screen or `aud2aud` CLI flags:

```
Default        spectral magnitude remap (source phase)
--time         also/splice segments and reorder them
--pitch 7      pitch shift (+7 semitones)
--randomize    shuffle segments
--dry-wet 0.5  blend with the original
```

Audio I/O is handled by `soundfile`/libsndfile — WAV, FLAC, OGG, AIFF, and **MP3**
with **no FFmpeg** required.

---

## ◈ Installation

### Using uv (Recommended)

Install Pixelification as a global tool:

```bash
uv tool install pixelification
```

Run it from anywhere:

```bash
pixelification
```

---

### Using pip

```bash
pip install pixelification
```

Then run:

```bash
pixelification
```

---

### Using pipx

No installation required:

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

## ◈ Usage — TUI

Launch the interactive terminal UI (no arguments needed):

```bash
pixelification
```

A keyboard-navigated menu opens:

```
  ■ Pixel Rearrangement Tool

  ● Rearrange Images    sort pixels between two images
  ○ Rearrange Videos    sort frames between two videos
  ○ Rearrange Audio     spectral cross-synthesis between two audio clips
  ○ ASCII               convert images to ASCII art
  ○ Quit                exit the application
```

### Keyboard Controls

| Key | Action |
|-----|--------|
| `↑` `↓` | Navigate menu items |
| `Enter` | Select highlighted item |
| `1`–`N` | Jump directly to item *N* |
| `Shift`+`↑` `↓` `←` `→` | Scroll ASCII art (vertical / horizontal) |
| `PgUp` / `PgDn` | Scroll ASCII art by one page |
| `q` / `Esc` | Quit |

### Image Mode

1. Select your source image
2. Select your target image
3. Watch the rearrangement play out in an OpenCV window — three panels: **Source · Target · Reconstruction**
4. Press `ESC` or `q` to quit the animation
5. Click **"Save Result Image"** to export a PNG, or **"Save Animation"** to export the pixel-slide as `anim_<src>_from_<tgt>.mp4`
   (the animation export needs no display — it streams frames straight to a `VideoWriter`)

> Animation exports are also available headlessly from the CLI: `pixelification img2img a.png b.png --anim mocher.mp4`.

### Video Mode

1. Select a source video (or still image — it'll be looped)
2. Select a target video
3. Watch the terminal progress bar as frames are processed
4. Result plays in an OpenCV window — loops until `ESC`/`q` or window close
5. Click **"Save Result Video"** to export

### Audio Mode

1. Select a **source** and a **target** audio file
2. Optionally open **"Advanced Audio Options"** to tune the pipeline
3. Press **"Run Audio Rearrangement"** (default: spectral cross-synthesis)
4. **"Play Result Audio"** previews the temp result with your system player
5. **"Save Result Audio"** writes `morphed_{src}_from_{tgt}.wav`

> See [docs/audio.md](docs/audio.md) for a full explanation of every advanced setting.

### ASCII Art Mode

1. Select an image file
2. Press **"Run ASCII Conversion"** — the art renders instantly in the terminal
3. Use `Shift+arrows` to scroll, `PgUp`/`PgDn` to jump by page
4. **"Copy to Clipboard"** pipes the full result to your system clipboard (`clip.exe`)
5. **"Save Result"** writes a `.txt` file to the current directory

---

## ◈ Usage — CLI

For scripting, batch processing, or headless environments, use the subcommand interface:

```bash
pixelification img2img <source> <target> [options]
pixelification vid2vid <source> <target> [options]
pixelification img2ascii <image> [options]
pixelification aud2aud <source> <target> [options]
```

Output paths default to auto-named files in the current directory (e.g. `reconstructed_src_from_tgt.png`).

### Commands

```
pixelification img2img <source> <target>
  Rearrange pixels from a source image to approximate a target image.
  Also exports the 60-frame pixel-slide as a video with --anim.

  -o, --output FILE    output image path (default: auto-named)
  --show               open an OpenCV window with the result
  --cpu                force CPU-only mode
  --anim [PATH]        also export the pixel-slide animation as .mp4
                       (optional path; auto-names anim_<src>_from_<tgt>.mp4)
  --anim-frames N      animation length in frames (default: 60)
  --anim-fps F         animation frame rate (default: 30)
  --anim-scale S       export resolution scale (default: 1.0 = full res)
  --anim-ease MODE     linear | ease-in-out | ease-out (default: linear)
  --anim-hold N        extra static frames of the final image (default: 12)
  --anim-panels        render Source | Target | Reconstruction panels in the export

pixelification vid2vid <source> <target>
  Rearrange every frame of a source (video or still image) to match
  a target video. Prints a progress bar to stderr.

  -o, --output FILE    output video path (default: auto-named)
  --show               play the result in an OpenCV window
  --cpu                force CPU-only mode

pixelification img2ascii <image>
  Convert an image to ASCII art. Prints to stdout and saves to file.

  -o, --output FILE    output text path (default: auto-named)
  -w, --width CHARS    output width in characters (default: 120)
  --no-dither          disable Floyd-Steinberg dithering

pixelification aud2aud <source> <target>
  Rearrange audio (spectral cross-synthesis by default). Writes a WAV.

  -o, --output FILE    output audio path (default: auto-named)
  --spectral / --no-spectral   toggle spectral frequency remapping
  --time               enable time-domain segment reordering
  --chunk-ms FLOAT     segment length in ms for time reorder (default: 60)
  --crossfade FLOAT    crossfade between segments in ms (default: 0)
  --fft INT / --hop INT         spectral FFT size / hop (default: 2048 / 512)
  --sort-key KEY       energy|amplitude|zcr|centroid|none (default: energy)
  --randomize / --seed INT      shuffle segments / seed
  --reverse            reverse segment order
  --pitch FLOAT        pitch shift in semitones (e.g. -12, +7)
  --phase MODE         source|target|random (default: source)
  --energy             match per-segment loudness to target
  --dry-wet FLOAT      dry/wet mix 0.0-1.0 (default: 0)
  --no-normalize       disable peak normalization

pixelification --version / -v
  Print the installed version.
```

---

## ◈ Requirements

```
Python     ≥ 3.10
OpenCV     cv2
NumPy
prompt_toolkit
soundfile     # audio: WAV/FLAC/OGG/AIFF/MP3 (bundles libsndfile, no FFmpeg)

# Optional — installed automatically on supported platforms:
cupy-cuda13x[ctk]    # NVIDIA CUDA acceleration (Linux / Windows)
python3-tk           # Linux only — for file dialog fallback
                     # sudo apt install python3-tk
```

---

## ◈ Documentation

Full, user-and-developer documentation lives in **[`docs/`](docs/index.md)**:

| Document | Covers |
|---|---|
| [docs/index.md](docs/index.md) | Overview, quick start, table of contents |
| [docs/installation.md](docs/installation.md) | Install, requirements, CUDA, config file |
| [docs/cli.md](docs/cli.md) | Complete CLI reference |
| [docs/tui.md](docs/tui.md) | Interactive terminal UI guide |
| [docs/audio.md](docs/audio.md) | Audio engine, advanced settings, presets |
| [docs/python-api.md](docs/python-api.md) | Code / API reference |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Troubleshooting |

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