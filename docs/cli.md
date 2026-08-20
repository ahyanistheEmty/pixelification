# CLI Reference

The CLI is built with `argparse`. Running `pixelification` with **no subcommand** opens
the [interactive TUI](tui.md) instead.

```
Usage: pixelification <command> [arguments]

Commands:
  img2img   <source> <target>   Rearrange pixels between two images
  vid2vid   <source> <target>   Rearrange frames between two videos
  img2ascii <image>             Convert an image to ASCII art
  aud2aud   <source> <target>   Rearrange audio (spectral cross-synthesis by default)
  help                          Show this help message
```

Use `pixelification help` or `pixelification --help` at any time.

## Global flags

| Flag | Description |
|---|---|
| `-v`, `--version` | Print the installed version and exit. |

Exit behavior: successful runs exit `0` and print the output path to stdout.
Errors print `Error: <message>` to stderr and exit `1`. `Ctrl+C` (`SIGINT`) prints
`Interrupted.` and exits immediately.

---

## `img2img` — rearrange image pixels

```
pixelification img2img <source> <target> [options]
```

Takes every pixel of `source` and moves it to approximate the layout of `target`.
The result is written as an image (the source's dimensions).

| Argument | Description |
|---|---|
| `source` | input image |
| `target` | image whose layout will be approximated |

| Flag | Default | Description |
|---|---|---|
| `-o, --output FILE` | auto | output path; auto-names `reconstructed_{src}_from_{tgt}.png` |
| `--show` | off | open an OpenCV window (Source · Target · Reconstruction) after saving |
| `--cpu` | off | force CPU-only (ignore CuPy) |
| `--anim [PATH]` | off | also export the pixel-slide animation; `PATH` is optional and auto-names `anim_{src}_from_{tgt}.mp4` |
| `--anim-frames N` | `60` | animation length in frames |
| `--anim-fps F` | `30` | animation frame rate (frames/second) |
| `--anim-scale S` | `1.0` | export resolution scale relative to the source (`1.0` = full resolution; `0.5` = half) |
| `--anim-ease MODE` | `linear` | motion easing: `linear` \| `ease-in-out` \| `ease-out` |
| `--anim-hold N` | `12` | extra static frames of the final image appended at the end |
| `--anim-panels` | off | render Source · Target · Reconstruction panels side by side in the export |

**Supported extensions:** `.png .jpg .jpeg .bmp .tiff .gif .webp`

Animation export is fully headless — it streams frames straight into a
`cv2.VideoWriter` (`mp4v`) and never opens a window. `.webm` is attempted with the
`VP90` codec when supported; `.gif` needs the optional `Pillow` dependency. If the
writer cannot open (e.g. missing codec), an explicit error is raised.

Example:

```bash
pixelification img2img city.png ocean.png --show
# writes reconstructed_city_from_ocean.png

pixelification img2img city.png ocean.png --anim cityslide.mp4 --anim-frames 90 \
    --anim-ease ease-in-out --anim-hold 15 --anim-panels
# also writes cityslide.mp4 (90 eased frames + 15-frame hold, three panels)

---

## `vid2vid` — rearrange video frames

```
pixelification vid2vid <source> <target> [options]
```

Rearranges every frame of `source` to match the corresponding frame of `target`.
When the aspect ratios differ, the narrower input is **letterboxed** with black bars.
A per-frame progress bar prints to stderr.

| Argument | Description |
|---|---|
| `source` | a video **or a still image** (a still image is looped for every target frame) |
| `target` | the target video (must have frames) |

| Flag | Default | Description |
|---|---|---|
| `-o, --output FILE` | auto | output path; auto-names `rearranged_{src}_from_{tgt}.mp4` |
| `--show` | off | play the result in an OpenCV window after saving |
| `--cpu` | off | force CPU-only |

**Supported extensions:** source — images above **or** `.mp4 .avi .mov .mkv .webm`;
target — video extensions only.

Behavior details:

- Frame count = `min(source frames, target frames)`. With a still-image source,
  the frame count equals the target's.
- Output uses the `mp4v` codec at the target/source FPS.
- Output dimensions: the larger of the two aspect ratios, with the other input padded.

Example:

```bash
pixelification vid2vid clip.mp4 dream.mp4 -o result.mp4
```

---

## `img2ascii` — convert an image to ASCII art

```
pixelification img2ascii <image> [options]
```

Prints the ASCII art to **stdout** and saves it to a file. Uses 10 luminance levels
(`@%#*+=-:. `) with auto-contrast, aspect correction, and optional Floyd-Steinberg
dithering.

| Argument | Description |
|---|---|
| `image` | input image |

| Flag | Default | Description |
|---|---|---|
| `-o, --output FILE` | auto | output path; auto-names `{stem}_ascii.txt` |
| `-w, --width CHARS` | `120` | output width in characters |
| `--no-dither` | off | disable Floyd-Steinberg dithering |

Example:

```bash
pixelification img2ascii photo.jpg --width 100 > art.txt
```

---

## `aud2aud` — rearrange audio

```
pixelification aud2aud <source> <target> [options]
```

Default behaviour is **spectral cross-synthesis**: the source is converted to a
spectrogram, its magnitudes are rank-remapped onto the target's, and the result is
resynthesised — source pitch/materials are preserved while the tonal structure
approximates the target. The output is a WAV file.

| Argument | Description |
|---|---|
| `source` | source audio |
| `target` | target audio |

| Flag | Default | Description |
|---|---|---|
| `-o, --output FILE` | auto | output path; auto-names `morphed_{src}_from_{tgt}.wav` |
| `--cpu` | off | force CPU-only (no-op for audio) |
| `--spectral` | on | enable spectral magnitude remapping (STFT) |
| `--no-spectral` | off | disable spectral frequency remapping |
| `--time` | off | enable time-domain segment reordering |
| `--no-time` | on | disable time-domain segment reordering |
| `--chunk-ms FLOAT` | `60` | segment length (ms) for time reorder |
| `--crossfade FLOAT` | `0` | crossfade length (ms) between segments (`0` = hard cuts) |
| `--fft INT` | `2048` | FFT size for spectral mode |
| `--hop INT` | `512` | hop length for spectral mode |
| `--sort-key {energy,amplitude,zcr,centroid,none}` | `energy` | per-segment sort key for time reorder |
| `--randomize` | off | shuffle segments randomly instead of sorting |
| `--seed INT` | `0` | random seed |
| `--reverse` | off | reverse the segment order |
| `--pitch FLOAT` | — | pitch shift in semitones (e.g. `-12`, `+7`) |
| `--no-keep-duration` | off | let pitch shifting also change duration |
| `--phase {source,target,random}` | `source` | phase source for spectral mode |
| `--energy` | off | match per-segment loudness to the target |
| `--dry-wet FLOAT` | `0` | dry/wet mix, `0.0`–`1.0` (steps of `0.05`; `0` = full effect) |
| `--no-normalize` | off | disable output peak normalization |

> These flags mirror the TUI **Advanced Audio Options** screen one-for-one.
> See [audio.md](audio.md) for the full explanation of each setting and suggested
> presets.

**Supported extensions:** `.wav .flac .ogg .aiff .aif .mp3`

Examples:

```bash
# Default: spectral cross-synthesis
pixelification aud2aud vocal.wav pad.flac

# Pure time-domain: cut vocal.wav into segments and reorder by energy to match pad.flac
pixelification aud2aud vocal.wav pad.flac --time --no-spectral

# Reorder + spectral + pitch up a fifth
pixelification aud2aud vocal.wav pad.flac --time --pitch 7

# Spectral with target phase and 50% dry/wet blend
pixelification aud2aud vocal.wav pad.flac --phase target --dry-wet 0.5
```
