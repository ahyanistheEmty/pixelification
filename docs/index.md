# Pixelification — Documentation

**Pixel Rearrangement Tool** — a keyboard-navigated terminal UI and CLI that rearranges
pixels, video frames, and audio segments between a **source** and a **target** using
colour-sort / spectral optimal transport.

> *No pixels created. No pixels destroyed. Only rearranged.*

This folder is the complete reference for using and extending Pixelification.

---

## Quick Start

```bash
# Install (one of)
uv tool install pixelification
pip install pixelification
pipx run pixelification

# Launch the interactive terminal UI
pixelification

# Or use the command line directly
pixelification img2img  photo.png  painting.png
pixelification img2img  photo.png  painting.png --anim  slide.mp4   # + pixel-slide video
pixelification vid2vid  clip.mp4   dream.mp4
pixelification img2ascii photo.jpg --width 100
pixelification aud2aud  vocal.wav  pad.flac
```

See [installation.md](installation.md) for full install options.

---

## Table of Contents

| Document | What it covers |
|---|---|
| [installation.md](installation.md) | Installing, requirements, optional CUDA, runtime config file |
| [cli.md](cli.md) | Complete CLI reference for every subcommand and flag |
| [tui.md](tui.md) | The interactive terminal UI — modes, keyboard controls, file dialogs |
| [audio.md](audio.md) | Audio rearrangement — defaults, the advanced settings, TUI ↔ CLI mapping |
| [python-api.md](python-api.md) | Code documentation: functions, classes, and internals |
| [troubleshooting.md](troubleshooting.md) | Common problems and their fixes |

---

## Feature Summary

| Feature | Where |
|---|---|
| Rearrange image pixels → image | TUI **Image Mode** · `pixelification img2img` |
| Export the pixel-slide animation → `.mp4` | TUI **Image Mode → Save Animation** · `img2img --anim` (headless) |
| Rearrange video frames → video | TUI **Video Mode** · `pixelification vid2vid` |
| Rearrange audio segments / spectra | TUI **Audio Mode** · `pixelification aud2aud` |
| Image → ASCII art | TUI **ASCII Mode** · `pixelification img2ascii` |
| Advanced audio controls | TUI **Advanced Audio Options** screen · CLI flags |
| NVIDIA GPU acceleration (CuPy) | optional `[cuda]` extra, automatic detection |
| MP3 / FLAC / OGG / WAV / AIFF | bundled libsndfile — no FFmpeg required |
