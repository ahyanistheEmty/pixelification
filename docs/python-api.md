# Python API Reference

This document describes the modules and functions that make up Pixelification, so you
can script with it or extend it. All code lives under `src/pixelification/`.

| Module | Responsibility |
|---|---|
| `pixelification.audio` | Audio I/O, `AudioSettings`, the STFT/ISTFT engine, `rearrange_audio` |
| `pixelification.runtime` | Runtime config file load/save, settings persistence |
| `pixelification.main` | CLI entry point, image/video/ASCII engines, and the TUI |
| `pixelification.__init__` | (empty) |

---

## `pixelification.audio`

### `read_audio(path) -> (np.ndarray, int)`

Read an audio file, returning `(mono float32 samples, sample rate)`. Multi-channel
audio is averaged to mono. Decodes WAV, FLAC, OGG, AIFF, and MP3 via the bundled
libsndfile.

### `write_audio(path, samples, sr) -> None`

Write float samples to `path` at sample rate `sr` (via `soundfile`).

### `class AudioSettings`

Dataclass holding every tunable in the pipeline. All fields:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `reorder_time` | bool | `False` | slice source into segments and reorder them |
| `remap_spectrum` | bool | `True` | spectral magnitude remapping (STFT) |
| `shape_pitch` | bool | `False` | enable pitch shifting |
| `remap_energy` | bool | `False` | per-segment loudness matching |
| `normalize` | bool | `False` | peak-normalize the output |
| `segment_ms` | float | `60.0` | segment length (ms) for time reorder |
| `crossfade_ms` | float | `0.0` | crossfade between segments (ms) |
| `fft_size` | int | `2048` | FFT size (spectral mode) |
| `hop_length` | int | `512` | STFT hop (spectral mode) |
| `sort_key` | str | `"energy"` | `energy` \| `amplitude` \| `zcr` \| `centroid` \| `none` |
| `randomize` | bool | `False` | shuffle segments randomly |
| `seed` | int | `0` | random seed |
| `reverse` | bool | `False` | reverse segment order |
| `pitch_shift_semitones` | float | `0.0` | pitch shift in semitones |
| `keep_duration` | bool | `True` | time-stretch back after pitch shift |
| `phase_mode` | str | `"source"` | `source` \| `target` \| `random` |
| `dry_wet` | float | `0.0` | 0 = full effect, 1 = original |

Methods:

- `AudioSettings.default() -> AudioSettings` — factory with the classic defaults.
- `AudioSettings.to_dict() -> dict` — serialisable copy.
- `AudioSettings.from_dict(data: dict) -> AudioSettings` — construct, ignoring
  unknown keys and sanitising `sort_key` / `phase_mode`.

### `rearrange_audio(source_path, target_path, output_path, settings=None) -> None`

Run the full pipeline and write `output_path`. `settings=None` uses
`AudioSettings.default()`. Transform order: `reorder_time` → `shape_pitch` →
`remap_spectrum` → `remap_energy` → `dry_wet` → `normalize`.

### STFT internals

- `stft(samples, fft_size=2048, hop_length=512) -> np.ndarray` — complex spectrogram,
  shape `(fft_size//2+1, n_frames)`, Hanning windowed frames.
- `istft(spectrogram, hop_length=512) -> np.ndarray` — inverse overlap-add, returns
  float32 samples.
- `_rearrange_spectrogram(src_mag, tgt_mag) -> np.ndarray` — rank-remap source
  magnitudes onto target magnitude ordering.
- `_rearrange_spectral(samples, target_samples, fft_size, hop_length, phase_mode)`
  — full spectral cross-synthesis with phase selection.
- `_reorder_time(samples, sort_key, segment_ms, sample_rate, crossfade_ms,
  randomize, seed, reverse)` — segment + sort/order + crossfaded reassembly.
- `_shift_pitch(samples, semitones, keep_duration, sample_rate)` — pitch shift via
  resampling.
- `_remap_energy(samples, target, n_segments, sample_rate)` — RMS matching per segment.
- `_peak_normalize(samples)` — scale peak to 0.95.
- `_mix_dry_wet(dry, wet, amount)` — linear dry/wet blend.

---

## `pixelification.runtime`

### `class RuntimeConfig`

Slots dataclass: `host_os: str`, `hardware_acceleration_available: bool`,
`backend: str`, `audio_settings: dict | None`.

### `config_path() -> pathlib.Path`

Path to the JSON config file in the OS config dir
(`%APPDATA%\pixelification` on Windows, `~/.config/pixelification` on Linux,
`~/Library/Application Support/pixelification` on macOS).

### `load_or_create_runtime_config(hardware_acceleration_available: bool) -> RuntimeConfig`

Load the config, or create it with sensible defaults. Persisted `audio_settings` are
carried through. If the stored environment no longer matches, values are reset.

### `save_audio_settings(audio_settings: dict) -> None`

Merge `audio_settings` into the config file and rewrite it.

---

## `pixelification.main`

### Accelerator helpers

- `HAS_CUPY: bool` — whether CuPy loaded **and** a CUDA device was found.
- `FORCE_CPU: bool` — global flag; when `True`, forces NumPy.
- `get_xp() -> module` — returns CuPy when available (and not forced), else NumPy.
- `to_np(arr)` — move a CuPy array back to NumPy.
- `xp_lexsort(keys, xp)` / `xp_scatter_add(a, indices, updates, xp)` — array-module
  agnostic lexsort / scatter-add.

### Constants

- `_IMAGE_EXTS` = `.png .jpg .jpeg .bmp .tiff .gif .webp`
- `_VIDEO_EXTS` = `.mp4 .avi .mov .mkv .webm`
- `_AUDIO_EXTS` = `.wav .flac .ogg .aiff .aif .mp3`
- `ASCII_ART` — the six-line banner; `ASCII_CHARS` — the 10-char luminance ramp.

### Image engine

- `compute_sort_keys(img, xp=np) -> (lum, hue, sat)` — per-pixel sort keys.
- `rearrange_pixels(img_src, img_tgt, xp=None) -> np.ndarray` — sort-map every
  source pixel onto the target's layout (BGR, source dims). Shared by the CLI
  still export, the live preview and the animation generator.
- `_compute_rearrangement(source_path, target_path) -> np.ndarray` — returns the
  rearranged BGR image (target resized to source dims).
- `rearrange(source_path, target_path, state) -> None` — TUI variant; plays the
  60-frame animation in an OpenCV window (driven by `generate_animation_frames`).
- `get_screen_resolution() -> (w, h)` — best-effort screen size.

### Animation engine

- `ease(t: float, mode: str = "linear") -> float` — map a `0..1` progress value
  through a curve; `mode` ∈ `"linear" | "ease-in-out" | "ease-out"`.
- `default_animation_path(src_stem, tgt_stem, suffix=".mp4") -> str` — returns
  `anim_{src_stem}_from_{tgt_stem}{suffix}`.
- `generate_animation_frames(img_src, img_tgt, out_img, *, num_frames=60,
  display_size=None, include_final_hold=12, ease_mode="linear", three_panel=False,
  xp=None) -> Iterator[np.ndarray]` — generate the pixel-slide animation as
  BGR uint8 frames. A generator/stream so full-resolution exports never buffer the
  whole clip in RAM; `display_size=(w, h)` downsamples (used by the live preview,
  `None` = full source size); the last `include_final_hold` frames are static
  copies of `out_img`; `three_panel=True` composes Source · Target · Reconstruction
  panels with labels. Uses the same CUDA/CPU helpers (`xp_scatter_add`, …) as the
  rest of the tool.
- `write_animation(frames, path, *, fps=30.0, codec=None) -> str` — stream BGR
  uint8 frames to a file. `.mp4` → `cv2.VideoWriter` (`mp4v`); `.webm` → `VP90`
  if the build supports it; `.gif` → Pillow (optional, loads all frames).
  Raises a clear error if the writer cannot open.

### Video engine

- `letterbox_pad(img, target_w, target_h) -> np.ndarray` — resize + black-bar pad.
- `_compute_video_rearrangement(source_path, target_path, progress_callback=None) -> str`
  — processes every frame, writes a temp `.mp4` (`mp4v`), returns its path. Source may
  be a still image (looped). Calls `progress_callback(cur, total)` per frame.
- `rearrange_video(source_path, target_path, state) -> None` — TUI variant; writes to a
  temp file, plays the result, honours the `_RUNNING` flag for Ctrl+C.

### ASCII engine

- `image_to_ascii(path: str, width: int = 120, dither: bool = True) -> str`
  — returns multi-line art; auto-contrast, aspect-correct resize, optional
  Floyd-Steinberg dithering.

### File dialogs

- `select_file(title="Select File", file_type="image") -> str | None` — native dialog;
  `file_type` ∈ `"image" | "video" | "audio" | "media"`. Falls back to Tk.

### `class State`

Mutable UI state (a dataclass). Key fields: `screen` (`"main" | "image" | "video" |
"audio" | "audio-settings" | "ascii"`), `source`, `target`, `status`, `status_style`,
`info`, `cursor`, `running`, `done`, `result`, `result_video_path`,
`result_audio_path`, `result_ascii`, `scroll_x/y`, `audio_settings`, and
`settings_edit_key` / `settings_edit_buffer` (inline editing). Menu definitions live
here: `MENU_MAIN`, `MENU_IMAGE`, `MENU_VIDEO`, `MENU_AUDIO`, `MENU_ASCII`, plus the
`menu` property.

### `class PixelTUI(runtime_config)`

The terminal application. Constructor restores persisted `audio_settings`.

- `run()` — builds the prompt_toolkit `Application` and starts the event loop.
- `_dispatch(idx)` — route a cursor selection per screen.
- Mode entry/selection: `_enter_image_mode`, `_enter_video_mode`,
  `_enter_audio_mode`, `_enter_ascii_mode`, `_select_source*`, `_select_target*`.
- Runs: `_run`, `_run_video`, `_run_audio`, `_run_ascii` (each spawns a worker thread).
- Audio settings: `_enter_audio_settings`, `_settings_step`, `_settings_enter`,
  `_commit_setting_edit`, `_cancel_setting_edit`, `_reset_audio_settings`,
  `_persist_audio_settings`.
- Saves: `_save_result`, `_save_result_video`, `_save_result_audio`,
  `_save_result_ascii`, `_save_animation` (regenerates and streams the pixel-slide
  to `anim_{src}_from_{tgt}.mp4` in cwd), `_copy_result_ascii`; preview:
  `_play_result_audio`.
- Rendering: `_build_text` (per-screen text), `_build_layout`, `_invalidate`,
  `_refresh_info` (shows dimensions/sample rate in the status area).
- Cleanup: `_quit` (removes temp result files, exits).

### `main()` — CLI entry

Argparse wiring for `--version`/`-v`, subcommands `img2img`, `vid2vid`,
`img2ascii`, `aud2aud`, `help`. With no subcommand it launches `PixelTUI`.

### `_audio_settings_from_args(args) -> AudioSettings`

Builds `AudioSettings` from parsed CLI flags (used by `aud2aud`).

---

## Scripting example

```python
import numpy as np
from pixelification.audio import AudioSettings, rearrange_audio

s = AudioSettings.default()            # classic spectral
s.reorder_time = True                  # add time-domain splicing
s.randomize = True
s.seed = 7
s.dry_wet = 0.3

rearrange_audio("vocal.wav", "pad.flac", "out.wav", settings=s)
```

### Animation scripting example

```python
import cv2
import numpy as np
from pixelification.main import generate_animation_frames, write_animation

src = cv2.imread("city.png", cv2.IMREAD_COLOR)
tgt = cv2.imread("ocean.png", cv2.IMREAD_COLOR)

frames = generate_animation_frames(
    src, tgt, out_img=None,          # out_img=None computes the final reconstruction
    num_frames=60,
)
write_animation(frames, "morph.mp4", fps=30)
```
