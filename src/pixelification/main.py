"""
Pixel Rearrangement Tool — Keyboard-Navigated Terminal UI

Rearrange image pixels or video frames via colour-sort optimal transport.
OpenCV window shows the result (animation for images, playback for video).
"""

import argparse
import asyncio
import cv2
import numpy as np
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator
from importlib.metadata import version, PackageNotFoundError

from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, Window, FormattedTextControl
from prompt_toolkit.styles import Style
from pixelification.runtime import RuntimeConfig, load_or_create_runtime_config, save_audio_settings
from pixelification.audio import rearrange_audio, AudioSettings
try:
    import soundfile as sf
    HAS_SOUNDFILE = True
except ImportError:
    HAS_SOUNDFILE = False

# ── GPU & Accelerator Support ────────────────────────────────────────

FORCE_CPU = False
_RUNNING = True

def _sigint_handler(signum, frame):
    global _RUNNING
    _RUNNING = False

try:
    import cupy as cp
    import cupyx as cpx
except ImportError:
    cp = None
    cpx = None
    HAS_CUPY = False
    CUPY_STATUS_TEXT = "No (CuPy not installed)"
else:
    def _probe_cupy() -> tuple[bool, str]:
        try:
            device_count = cp.cuda.runtime.getDeviceCount()
            if device_count > 0:
                return True, f"Yes (CuPy, {device_count} CUDA device{'s' if device_count != 1 else ''})"
            return False, "No (CuPy sees 0 CUDA devices)"
        except Exception:
            return False, "No (CuPy runtime unavailable)"

    HAS_CUPY, CUPY_STATUS_TEXT = _probe_cupy()

def get_xp():
    global FORCE_CPU
    if FORCE_CPU:
        return np
    if HAS_CUPY and cp is not None:
        return cp
    return np

def to_np(arr):
    if arr is None: return None
    if HAS_CUPY and cp is not None and isinstance(arr, cp.ndarray):
        return arr.get()
    return np.asanyarray(arr)

def xp_lexsort(keys, xp):
    if xp is np:
        return np.lexsort(keys)
    if HAS_CUPY and xp is cp:
        return cp.lexsort(cp.stack(keys))
    return xp.lexsort(keys)

def xp_scatter_add(a, indices, updates, xp):
    if xp is np:
        np.add.at(a, indices, updates)
        return a
    if HAS_CUPY and xp is cp and cpx is not None:
        a_cp = cp.asanyarray(a)
        updates_cp = cp.asanyarray(updates)
        if isinstance(indices, (tuple, list)):
            shape = a_cp.shape
            w = shape[1]
            idx_y = cp.asanyarray(indices[0])
            idx_x = cp.asanyarray(indices[1])
            flat_idx = idx_y * w + idx_x
            if a_cp.ndim == 3:
                cpx.scatter_add(a_cp.reshape(-1, shape[2]), flat_idx, updates_cp)
            else:
                cpx.scatter_add(a_cp.ravel(), flat_idx, updates_cp)
        else:
            cpx.scatter_add(a_cp, cp.asanyarray(indices), updates_cp)
        return a_cp
    return a

# ── Styling ──────────────────────────────────────────────────────────

STYLE = Style([
    ("title",         "bold #00d787"),
    ("mode-label",    "bold #5f87ff"),
    ("path-label",    "bold #5f87ff"),
    ("path-value",    "#87afff"),
    ("path-empty",    "#585858 italic"),
    ("divider",       "#3a3a3a"),
    ("menu-item",     "bold #ffffff"),
    ("menu-desc",     "#6c6c6c"),
    ("menu-cursor",   "bold #000000 bg:#00d787"),
    ("status",        "#5faf5f"),
    ("status-info",   "#878787 italic"),
    ("status-error",  "#ff5f5f"),
    ("status-warn",   "#ffaf5f"),
    ("help",          "#585858 italic"),
])

ASCII_ART = [
    "██████╗ ██╗██╗  ██╗███████╗██╗     ██╗███████╗██╗ ██████╗ █████╗ ████████╗██╗ ██████╗ ███╗   ██╗",
    "██╔══██╗██║╚██╗██╔╝██╔════╝██║     ██║██╔════╝██║██╔════╝██╔══██╗╚══██╔══╝██║██╔═══██╗████╗  ██║",
    "██████╔╝██║ ╚███╔╝ █████╗  ██║     ██║█████╗  ██║██║     ███████║   ██║   ██║██║   ██║██╔██╗ ██║",
    "██╔═══╝ ██║ ██╔██╗ ██╔══╝  ██║     ██║██╔══╝  ██║██║     ██╔══██║   ██║   ██║██║   ██║██║╚██╗██║",
    "██║     ██║██╔╝ ██╗███████╗███████╗██║██║     ██║╚██████╗██║  ██║   ██║   ██║╚██████╔╝██║ ╚████║",
    "╚═╝     ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝╚═╝     ╚═╝ ╚═════╝╚═╝  ╚═╝   ╚═╝   ╚═╝ ╚═════╝ ╚═╝  ╚═══╝",
]

_IMAGE_EXTS = frozenset({'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.gif', '.webp'})
_VIDEO_EXTS = frozenset({'.mp4', '.avi', '.mov', '.mkv', '.webm'})
_AUDIO_EXTS = frozenset({'.wav', '.flac', '.ogg', '.aiff', '.aif', '.mp3'})


# ── Native File Dialog ───────────────────────────────────────────────

def _powershell_open_file(title: str, file_type: str = "image") -> str | None:
    if file_type == "video":
        filt = ("Video Files (*.mp4;*.avi;*.mov;*.mkv;*.webm)|"
                "*.mp4;*.avi;*.mov;*.mkv;*.webm|All Files (*.*)|*.*")
    elif file_type == "audio":
        filt = ("Audio Files (*.wav;*.flac;*.ogg;*.aiff;*.aif;*.mp3)|"
                "*.wav;*.flac;*.ogg;*.aiff;*.aif;*.mp3|All Files (*.*)|*.*")
    elif file_type == "media":
        filt = ("Media Files (*.mp4;*.avi;*.mov;*.mkv;*.webm;*.png;*.jpg;*.jpeg;*.bmp;*.tiff;*.gif;*.webm)|"
                "*.mp4;*.avi;*.mov;*.mkv;*.webm;*.png;*.jpg;*.jpeg;*.bmp;*.tiff;*.gif;*.webm|"
                "All Files (*.*)|*.*")
    else:
        filt = ("Image Files (*.png;*.jpg;*.jpeg;*.bmp;*.tiff;*.gif;*.webp)|"
                "*.png;*.jpg;*.jpeg;*.bmp;*.tiff;*.gif;*.webp|All Files (*.*)|*.*")
    script = (
        'Add-Type -AssemblyName System.Windows.Forms\n'
        '$f = New-Object System.Windows.Forms.OpenFileDialog\n'
        f'$f.Filter = "{filt}"\n'
        '$f.FilterIndex = 1\n'
        '$f.RestoreDirectory = $true\n'
        'if ($f.ShowDialog() -eq "OK") { $f.FileName }\n'
    )
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".ps1", delete=False, encoding="utf-8",
        ) as f:
            f.write(script)
            tmp = f.name
        r = subprocess.run(
            ["powershell", "-NoProfile", "-File", tmp],
            capture_output=True, text=True, timeout=60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
        )
        out = r.stdout.strip()
        return out if out else None
    except Exception:
        return None
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except Exception:
                pass


def _tkinter_open_file(title: str, file_type: str = "image") -> str | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        if file_type == "video":
            filetypes = [
                ("Video files", "*.mp4 *.avi *.mov *.mkv *.webm"),
                ("All files",   "*.*"),
            ]
        elif file_type == "audio":
            filetypes = [
                ("Audio files", "*.wav *.flac *.ogg *.aiff *.aif *.mp3"),
                ("All files",   "*.*"),
            ]
        elif file_type == "media":
            filetypes = [
                ("Media files", "*.mp4 *.avi *.mov *.mkv *.webm *.png *.jpg *.jpeg *.bmp *.tiff *.gif *.webp"),
                ("All files",   "*.*"),
            ]
        else:
            filetypes = [
                ("Image files", "*.png *.jpg *.jpeg *.bmp *.tiff *.gif *.webp"),
                ("All files",   "*.*"),
            ]
        path = filedialog.askopenfilename(
            parent=root, title=title, filetypes=filetypes,
        )
        root.destroy()
        return path if path else None
    except Exception:
        return None


def select_file(title: str = "Select File", file_type: str = "image") -> str | None:
    if os.name == "nt":
        path = _powershell_open_file(title, file_type)
        if path:
            return path
    path = _tkinter_open_file(title, file_type)
    return path if path else None


# ── Application State ────────────────────────────────────────────────

@dataclass
class State:
    screen: str = "main"        # "main" | "image" | "video" | "audio" | "ascii"
    source: str = ""
    target: str = ""
    status: str = "Ready"
    status_style: str = "status"
    info: str = ""
    cursor: int = 0
    running: bool = False
    done: bool = False
    result: np.ndarray | None = None
    result_video_path: str = ""
    result_audio_path: str = ""
    using_accelerator: bool = HAS_CUPY
    acceleration_status: str = CUPY_STATUS_TEXT
    result_ascii: str = ""
    scroll_x: int = 0
    scroll_y: int = 0
    audio_settings: AudioSettings = field(default_factory=AudioSettings.default)
    settings_edit_key: str | None = None
    settings_edit_buffer: str = ""

    MENU_MAIN = [
        ("Rearrange Images", "sort pixels between two images"),
        ("Rearrange Videos", "sort frames between two videos"),
        ("Rearrange Audio", "spectral cross-synthesis between two audio clips"),
        ("ASCII", "convert images to ASCII art"),
        ("Quit", "exit the application"),
    ]

    MENU_IMAGE = [
        ("Select Source Image",   "choose the image whose pixels will be rearranged"),
        ("Select Target Image",   "choose the image whose layout will be approximated"),
        ("Run Rearrangement",     "execute the sort-based pixel-matching algorithm"),
        ("Save Result Image",     "save the reconstructed image to disk"),
        ("Save Animation",        "export the pixel-slide animation to an mp4 file"),
        ("Back to Main Menu",     "return to mode selection"),
        ("Quit",                  "exit the application"),
    ]

    MENU_VIDEO = [
        ("Select Source Video",   "choose the source video file"),
        ("Select Target Video",   "choose the target video file"),
        ("Run Video Rearrangement", "rearrange all frames to match target"),
        ("Save Result Video",     "save the rearranged video to disk"),
        ("Back to Main Menu",     "return to mode selection"),
        ("Quit",                  "exit the application"),
    ]

    MENU_AUDIO = [
        ("Select Source Audio",   "choose the source audio file"),
        ("Select Target Audio",   "choose the target audio file"),
        ("Advanced Audio Options", "tune what the rearrangement may change"),
        ("Run Audio Rearrangement", "rearrange audio per the current settings"),
        ("Play Result Audio",     "preview the morphed audio with system player"),
        ("Save Result Audio",     "save the morphed audio to disk"),
        ("Back to Main Menu",     "return to mode selection"),
        ("Quit",                  "exit the application"),
    ]

    MENU_ASCII = [
        ("Select Image",          "choose an image to convert"),
        ("Run ASCII Conversion",  "convert the selected image to ASCII art"),
        ("Copy to Clipboard",     "copy the ASCII art to the system clipboard"),
        ("Save Result",           "save the ASCII art to a .txt file"),
        ("Back to Main Menu",     "return to mode selection"),
        ("Quit",                  "exit the application"),
    ]

    @property
    def menu(self):
        return {"main": self.MENU_MAIN, "image": self.MENU_IMAGE, "video": self.MENU_VIDEO, "audio": self.MENU_AUDIO, "ascii": self.MENU_ASCII}[self.screen]


# ── Audio Advanced Settings ───────────────────────────────────────────

# rows: (settings_key, label, kind, extra)
#   kind "bool"         -> extra ()
#   kind "choice"       -> extra (options,)
#   kind "float"/"int"  -> extra (step, lo, hi)

AUDIO_SETTINGS_ROWS = [
    # ── what may change ──
    ("reorder_time",         "Reorder time segments",     "bool"),
    ("remap_spectrum",       "Remap frequency spectrum",  "bool"),
    ("shape_pitch",          "Shift pitch",               "bool"),
    ("remap_energy",         "Remap loudness / energy",   "bool"),
    ("normalize",            "Normalize output",          "bool"),
    # ── segmentation / dsp ──
    ("segment_ms",           "Segment size (ms)",         "float", (10.0, 20.0, 2000.0)),
    ("crossfade_ms",         "Crossfade (ms)",            "float", (1.0, 0.0, 100.0)),
    ("fft_size",             "FFT size",                  "int",   (64, 32, 16384)),
    ("hop_length",           "Hop length",                "int",   (32, 16, 8192)),
    # ── sorting / variation ──
    ("sort_key",             "Sort key",                  "choice", ["energy", "amplitude", "zcr", "centroid", "none"]),
    ("randomize",            "Randomize order",           "bool"),
    ("seed",                 "Random seed",               "int",   (1, 0, 9999)),
    ("reverse",              "Reverse order",             "bool"),
    # ── pitch ──
    ("pitch_shift_semitones","Pitch shift (semitones)",   "float", (0.5, -24.0, 24.0)),
    ("keep_duration",        "Keep duration after pitch", "bool"),
    # ── spectral phase ──
    ("phase_mode",           "Spectral phase",            "choice", ["source", "target", "random"]),
    # ── output ──
    ("dry_wet",              "Dry/wet mix",               "float", (0.05, 0.0, 1.0)),
]

AUDIO_SETTINGS_RESET = len(AUDIO_SETTINGS_ROWS)  # final row = reset to defaults


# ── Rearrangement Engine ─────────────────────────────────────────────

def compute_sort_keys(img, xp=np):
    h, w = img.shape[:2]
    flat = img.reshape(-1, 3).astype(np.float32)
    lum = 0.299 * flat[:, 2] + 0.587 * flat[:, 1] + 0.114 * flat[:, 0]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV_FULL).reshape(-1, 3).astype(np.float32)
    if xp is not np:
        return xp.array(lum), xp.array(hsv[:, 0]), xp.array(hsv[:, 1])
    return lum, hsv[:, 0], hsv[:, 1]


def rearrange_pixels(img_src: np.ndarray, img_tgt: np.ndarray, xp=None) -> np.ndarray:
    """Sort-map every source pixel onto the target's layout (BGR, source dims).

    Shared by the CLI still export, the live TUI preview and the animation
    generator, so every path produces identical results.
    """
    if xp is None:
        xp = get_xp()
    h, w = img_src.shape[:2]
    if img_tgt.shape[:2] != (h, w):
        img_tgt = cv2.resize(img_tgt, (w, h))

    s_l, s_h, s_s = compute_sort_keys(img_src, xp)
    t_l, t_h, t_s = compute_sort_keys(img_tgt, xp)
    s_order = xp_lexsort((s_s, s_h, s_l), xp)
    t_order = xp_lexsort((t_s, t_h, t_l), xp)

    out_flat = xp.empty_like(xp.array(img_src.reshape(-1, 3)), dtype=xp.uint8)
    out_flat[t_order] = xp.array(img_src.reshape(-1, 3))[s_order]
    return to_np(out_flat.reshape(h, w, 3))


def _compute_rearrangement(source_path: str, target_path: str) -> np.ndarray:
    img_src = cv2.imread(source_path, cv2.IMREAD_COLOR)
    img_tgt = cv2.imread(target_path, cv2.IMREAD_COLOR)
    if img_src is None:
        raise FileNotFoundError(f"Cannot read source: {source_path}")
    if img_tgt is None:
        raise FileNotFoundError(f"Cannot read target: {target_path}")

    return rearrange_pixels(img_src, img_tgt, get_xp())


# ── Animation Engine ────────────────────────────────────────────────

EASE_MODES = ("linear", "ease-in-out", "ease-out")


def ease(t: float, mode: str = "linear") -> float:
    """Map a 0..1 progress value through an easing curve."""
    if mode == "ease-in-out":
        return t * t * (3 - 2 * t)  # smoothstep
    if mode == "ease-out":
        return 1 - (1 - t) ** 2
    return t


def default_animation_path(src_stem: str, tgt_stem: str, suffix: str = ".mp4") -> str:
    if not suffix.startswith("."):
        suffix = "." + suffix
    return f"anim_{src_stem}_from_{tgt_stem}{suffix}"


def generate_animation_frames(
    img_src: np.ndarray,
    img_tgt: np.ndarray,
    out_img: np.ndarray,
    *,
    num_frames: int = 60,
    display_size: tuple[int, int] | None = None,  # (w, h) or None = full res
    include_final_hold: int = 12,  # extra static frames of the final image
    ease_mode: str = "linear",     # "linear" | "ease-in-out" | "ease-out"
    three_panel: bool = False,     # Source | Target | Reconstruction
    xp=None,
) -> Iterator[np.ndarray]:
    """Yield the pixel-slide animation as BGR uint8 frames (headless).

    A generator that streams one frame at a time so a full-resolution export
    never materialises the whole animation in RAM. Default resolution is the
    full source size; ``display_size`` downscales (used by the live preview).
    The final ``include_final_hold`` frames are static copies of ``out_img``.
    """
    if xp is None:
        xp = get_xp()
    if ease_mode not in EASE_MODES:
        raise ValueError(f"ease_mode must be one of {EASE_MODES}, got {ease_mode!r}")
    if num_frames < 1:
        raise ValueError("num_frames must be >= 1")
    if include_final_hold < 0:
        raise ValueError("include_final_hold must be >= 0")

    h, w = img_src.shape[:2]
    if img_tgt.shape[:2] != (h, w):
        img_tgt = cv2.resize(img_tgt, (w, h))
    if out_img is None:
        out_img = rearrange_pixels(img_src, img_tgt, xp)
    elif out_img.shape[:2] != (h, w):
        out_img = cv2.resize(out_img, (w, h))

    if display_size is not None:
        iw, ih = int(display_size[0]), int(display_size[1])
    else:
        iw, ih = w, h
    iw, ih = max(iw, 1), max(ih, 1)

    src_rs = cv2.resize(img_src, (iw, ih), interpolation=cv2.INTER_LANCZOS4)
    out_rs = cv2.resize(out_img, (iw, ih), interpolation=cv2.INTER_LANCZOS4)

    total = h * w
    s_l, s_h, s_s = compute_sort_keys(img_src, xp)
    t_l, t_h, t_s = compute_sort_keys(img_tgt, xp)
    s_order = xp_lexsort((s_s, s_h, s_l), xp)
    t_order = xp_lexsort((t_s, t_h, t_l), xp)
    forward = xp.empty(total, dtype=xp.int32)
    forward[s_order] = t_order

    scx = iw / w
    scy = ih / h

    s_idx_x = (np.arange(iw, dtype=np.float32) * w / iw).clip(0, w - 1).round().astype(np.int32)
    s_idx_y = (np.arange(ih, dtype=np.float32) * h / ih).clip(0, h - 1).round().astype(np.int32)
    gx, gy = np.meshgrid(s_idx_x, s_idx_y)
    src_lin = gy * w + gx
    if xp is not np:
        src_lin = xp.array(src_lin)

    tgt_lin = forward[src_lin]
    tgt_dx = (tgt_lin % w).astype(xp.float32) * scx
    tgt_dy = (tgt_lin // w).astype(xp.float32) * scy
    src_dx = xp.array(gx.astype(np.float32) * scx)
    src_dy = xp.array(gy.astype(np.float32) * scy)
    colors = xp.array(src_rs.reshape(-1, 3).astype(np.float32))

    if three_panel:
        tgt_rs = cv2.resize(img_tgt, (iw, ih), interpolation=cv2.INTER_LANCZOS4)
        label_h = 22
        canvas_w = iw * 3
        canvas_h = ih + label_h
        font = cv2.FONT_HERSHEY_SIMPLEX

        def compose(recon: np.ndarray) -> np.ndarray:
            canvas = np.full((canvas_h, canvas_w, 3), 32, dtype=np.uint8)
            canvas[label_h:, 0:iw] = src_rs
            canvas[label_h:, iw:2 * iw] = tgt_rs
            canvas[label_h:, 2 * iw:3 * iw] = recon
            for label, xo in [("Source", 0), ("Target", iw), ("Reconstruction", 2 * iw)]:
                cv2.rectangle(canvas, (xo, 0), (xo + iw, label_h), (0, 0, 0), -1)
                cv2.putText(canvas, label, (xo + 6, 16), font, 0.45, (200, 200, 200), 1)
            return canvas
    else:
        def compose(recon: np.ndarray) -> np.ndarray:
            return recon

    for fi in range(num_frames):
        t = ease((fi + 1) / num_frames, ease_mode)

        curr_x = xp.clip((1 - t) * src_dx.ravel() + t * tgt_dx.ravel(), 0, iw - 1)
        curr_y = xp.clip((1 - t) * src_dy.ravel() + t * tgt_dy.ravel(), 0, ih - 1)
        rx = xp.round(curr_x).astype(xp.int32)
        ry = xp.round(curr_y).astype(xp.int32)

        accum = xp.zeros((ih, iw, 3), dtype=xp.float32)
        cnt = xp.zeros((ih, iw), dtype=xp.float32)
        accum = xp_scatter_add(accum, (ry, rx), colors, xp)
        cnt = xp_scatter_add(cnt, (ry, rx), 1.0, xp)

        mask = cnt > 0
        accum[mask] /= cnt[mask, None]

        res_frame = to_np(accum).astype(np.uint8)
        yield compose(res_frame)

    for _ in range(include_final_hold):
        yield compose(out_rs)


def _write_gif(frames, path: str, fps: float) -> str:
    try:
        from PIL import Image
    except ImportError:
        raise RuntimeError("GIF export needs Pillow — install it with `uv pip install pillow`")
    duration = max(1, int(round(1000.0 / fps)))
    imgs = []
    for frame in frames:
        imgs.append(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
    if not imgs:
        raise ValueError("write_animation got an empty frame iterable")
    imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=duration, loop=0)
    return path


def write_animation(
    frames,
    path: str,
    *,
    fps: float = 30.0,
    codec: str | None = None,
) -> str:
    """Stream an iterable of BGR uint8 frames into an animation file.

    .mp4  → ``cv2.VideoWriter`` with ``mp4v`` (no extra dependencies).
    .webm → ``cv2.VideoWriter`` with ``VP90`` (only if the OpenCV/ffmpeg
            build supports it; raises a clear error otherwise).
    .gif  → Pillow (optional dependency; loads all frames into memory).
    """
    path = str(path)
    suffix = Path(path).suffix.lower()

    if suffix == ".gif":
        return _write_gif(frames, path, fps=fps)

    if suffix == ".webm":
        codec = codec or "VP90"
    else:
        codec = codec or "mp4v"
    if len(codec) != 4:
        raise ValueError(f"codec must be a 4-char tag, got {codec!r}")

    first = None
    for frame in frames:
        first = frame
        break
    if first is None:
        raise ValueError("write_animation got an empty frame iterable")

    h, w = first.shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*codec)
    writer = cv2.VideoWriter(path, fourcc, float(fps), (w, h))
    if not writer.isOpened():
        raise RuntimeError(
            f"could not open video writer for {path!r} (codec {codec!r}); "
            "use .mp4 (mp4v) or install ffmpeg with VP9 support"
        )

    writer.write(first)
    for frame in frames:
        if frame.shape[:2] != (h, w):
            frame = cv2.resize(frame, (w, h))
        writer.write(frame)
    writer.release()
    return path


def get_screen_resolution():
    try:
        import ctypes
        sw = ctypes.windll.user32.GetSystemMetrics(0)
        sh = ctypes.windll.user32.GetSystemMetrics(1)
        if sw > 0 and sh > 0:
            return sw, sh
    except Exception:
        pass

    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        root.destroy()
        if sw > 0 and sh > 0:
            return sw, sh
    except Exception:
        pass

    return 1920, 1080


def rearrange(source_path: str, target_path: str, state: State) -> None:
    try:
        img_src = cv2.imread(source_path, cv2.IMREAD_COLOR)
        img_tgt = cv2.imread(target_path, cv2.IMREAD_COLOR)

        if img_src is None:
            state.status = f"Can't read source: {Path(source_path).name}"
            state.status_style = "status-error"; return
        if img_tgt is None:
            state.status = f"Can't read target: {Path(target_path).name}"
            state.status_style = "status-error"; return

        h, w = img_src.shape[:2]
        img_tgt = cv2.resize(img_tgt, (w, h))

        xp = get_xp()
        out_img = rearrange_pixels(img_src, img_tgt, xp)

        sw, sh = get_screen_resolution()
        canvas = np.full((sh, sw, 3), 32, dtype=np.uint8)

        label_h = 22
        pw = sw // 3
        ph = sh - label_h
        sc = min(pw / w, ph / h)
        iw, ih = max(int(w * sc), 1), max(int(h * sc), 1)

        src_s = cv2.resize(img_src, (iw, ih), interpolation=cv2.INTER_LANCZOS4)
        tgt_s = cv2.resize(img_tgt, (iw, ih), interpolation=cv2.INTER_LANCZOS4)

        cx = (pw - iw) // 2
        cy = label_h + (ph - ih) // 2
        canvas[cy:cy+ih, cx:cx+iw] = src_s
        canvas[cy:cy+ih, pw+cx:pw+cx+iw] = tgt_s

        rec_x = 2 * pw + cx
        rec_region = canvas[cy:cy+ih, rec_x:rec_x+iw]

        font = cv2.FONT_HERSHEY_SIMPLEX
        for label, xo in [("Source", 0), ("Target", pw), ("Reconstruction", 2 * pw)]:
            cv2.rectangle(canvas, (xo, 0), (xo + pw, label_h), (0, 0, 0), -1)
            cv2.putText(canvas, label, (xo + 6, 16), font, 0.45, (200, 200, 200), 1)

        wn = "Pixel Rearrangement  (ESC/q  anytime  to  quit)"
        cv2.namedWindow(wn, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(wn, sw, sh)
        cv2.imshow(wn, canvas)
        cv2.waitKey(300)

        for res_frame in generate_animation_frames(
            img_src, img_tgt, out_img,
            num_frames=60,
            display_size=(iw, ih),
            include_final_hold=0,
            ease_mode="linear",
            xp=xp,
        ):
            rec_region[:] = res_frame
            cv2.imshow(wn, canvas)
            if cv2.waitKey(25) & 0xFF in (27, ord("q")):
                break

        rec_region[:] = cv2.resize(out_img, (iw, ih))
        cv2.imshow(wn, canvas)

        state.result = out_img
        state.done = True
        state.running = False

        while True:
            key = cv2.waitKey(100) & 0xFF
            if key in (27, ord("q")):
                break

        cv2.destroyAllWindows()

    except Exception as e:
        import traceback
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb = traceback.extract_tb(exc_traceback)
        # Find the last frame that is in our own file
        our_frame = next((f for f in reversed(tb) if "main.py" in f.filename), tb[-1])
        line = our_frame.lineno
        msg = str(e)
        if "cupy" in msg.lower():
            global FORCE_CPU
            FORCE_CPU = True
            state.status = f"CuPy Error (L{line}): falling back to CPU..."
            state.using_accelerator = False
            state.acceleration_status = "No (CuPy failed during compute; using CPU)"
        else:
            state.status = f"Error (L{line}): {e}"
        state.status_style = "status-error"
    finally:
        state.running = False
        state.done = True


def letterbox_pad(img, target_w, target_h):
    h, w = img.shape[:2]
    if w == target_w and h == target_h:
        return img
    scale = min(target_w / w, target_h / h)
    new_w = max(int(w * scale), 1)
    new_h = max(int(h * scale), 1)
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
    canvas = np.zeros((target_h, target_w, 3), dtype=np.uint8)
    x_off = (target_w - new_w) // 2
    y_off = (target_h - new_h) // 2
    canvas[y_off:y_off+new_h, x_off:x_off+new_w] = resized
    return canvas


def _compute_video_rearrangement(
    source_path: str,
    target_path: str,
    progress_callback=None,
) -> str:
    src_is_img = Path(source_path).suffix.lower() in _IMAGE_EXTS

    if src_is_img:
        img_src = cv2.imread(source_path, cv2.IMREAD_COLOR)
        if img_src is None:
            raise FileNotFoundError(f"Cannot read source image: {source_path}")
        h_src, w_src = img_src.shape[:2]
        cap_tgt = cv2.VideoCapture(target_path)
        if not cap_tgt.isOpened():
            raise FileNotFoundError(f"Cannot open target video: {target_path}")
        total_tgt = int(cap_tgt.get(cv2.CAP_PROP_FRAME_COUNT))
        total = total_tgt
        if total == 0:
            raise ValueError("Target video has no frames")
        fps = cap_tgt.get(cv2.CAP_PROP_FPS)
    else:
        cap_src = cv2.VideoCapture(source_path)
        cap_tgt = cv2.VideoCapture(target_path)
        if not cap_src.isOpened():
            raise FileNotFoundError(f"Cannot open source video: {source_path}")
        if not cap_tgt.isOpened():
            raise FileNotFoundError(f"Cannot open target video: {target_path}")
        total_src = int(cap_src.get(cv2.CAP_PROP_FRAME_COUNT))
        total_tgt = int(cap_tgt.get(cv2.CAP_PROP_FRAME_COUNT))
        total = min(total_src, total_tgt)
        if total == 0:
            raise ValueError("One or both videos have no frames")
        fps = cap_src.get(cv2.CAP_PROP_FPS)
        h_src = int(cap_src.get(cv2.CAP_PROP_FRAME_WIDTH))
        w_src = int(cap_src.get(cv2.CAP_PROP_FRAME_HEIGHT))

    w_tgt = int(cap_tgt.get(cv2.CAP_PROP_FRAME_WIDTH))
    h_tgt = int(cap_tgt.get(cv2.CAP_PROP_FRAME_HEIGHT))

    if w_src == 0 or h_src == 0:
        raise ValueError(f"source is not a valid video file (0x0 dimensions)")
    if w_tgt == 0 or h_tgt == 0:
        raise ValueError(f"target is not a valid video file (0x0 dimensions)")

    ar_src = w_src / h_src
    ar_tgt = w_tgt / h_tgt
    ar_diff = abs(ar_src - ar_tgt) > 0.01

    if ar_diff:
        if ar_src >= ar_tgt:
            out_w, out_h = w_src, h_src
            pad_src, pad_tgt = False, True
        else:
            out_w, out_h = w_tgt, h_tgt
            pad_src, pad_tgt = True, False
    else:
        out_w, out_h = w_src, h_src
        pad_src, pad_tgt = False, False

    fd, tmp_path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(tmp_path, fourcc, fps, (out_w, out_h))

    xp = get_xp()

    for i in range(total):
        if not _RUNNING:
            raise KeyboardInterrupt()

        if src_is_img:
            src_frame = img_src.copy()
        else:
            ret_src, src_frame = cap_src.read()
            if not ret_src:
                break

        ret_tgt, tgt_frame = cap_tgt.read()
        if not ret_tgt:
            break

        if pad_src:
            src_frame = letterbox_pad(src_frame, out_w, out_h)
        if pad_tgt:
            tgt_frame = letterbox_pad(tgt_frame, out_w, out_h)
        if not pad_src and not pad_tgt and tgt_frame.shape[:2] != src_frame.shape[:2]:
            tgt_frame = cv2.resize(tgt_frame, (out_w, out_h))

        s_l, s_h, s_s = compute_sort_keys(src_frame, xp)
        t_l, t_h, t_s = compute_sort_keys(tgt_frame, xp)
        s_order = xp_lexsort((s_s, s_h, s_l), xp)
        t_order = xp_lexsort((t_s, t_h, t_l), xp)

        src_flat = xp.array(src_frame.reshape(-1, 3))
        out_flat = xp.empty_like(src_flat, dtype=xp.uint8)
        out_flat[t_order] = src_flat[s_order]
        out_frame = out_flat.reshape(out_h, out_w, 3)

        out_frame = to_np(out_frame)

        writer.write(out_frame)

        if progress_callback:
            progress_callback(i + 1, total)

    if not src_is_img:
        cap_src.release()
    cap_tgt.release()
    writer.release()

    return tmp_path


def rearrange_video(source_path: str, target_path: str, state: State) -> None:
    try:
        src_is_img = Path(source_path).suffix.lower() in _IMAGE_EXTS

        if src_is_img:
            img_src = cv2.imread(source_path, cv2.IMREAD_COLOR)
            if img_src is None:
                state.status = f"Can't read source image: {Path(source_path).name}"
                state.status_style = "status-error"
                return
            h_src, w_src = img_src.shape[:2]
            cap_tgt = cv2.VideoCapture(target_path)
            if not cap_tgt.isOpened():
                state.status = f"Can't open target video: {Path(target_path).name}"
                state.status_style = "status-error"
                return
            total_tgt = int(cap_tgt.get(cv2.CAP_PROP_FRAME_COUNT))
            total = total_tgt
            if total == 0:
                state.status = "Target video has no frames"
                state.status_style = "status-error"
                return
            fps = cap_tgt.get(cv2.CAP_PROP_FPS)
        else:
            cap_src = cv2.VideoCapture(source_path)
            cap_tgt = cv2.VideoCapture(target_path)
            if not cap_src.isOpened():
                state.status = f"Can't open source video: {Path(source_path).name}"
                state.status_style = "status-error"
                return
            if not cap_tgt.isOpened():
                state.status = f"Can't open target video: {Path(target_path).name}"
                state.status_style = "status-error"
                return
            total_src = int(cap_src.get(cv2.CAP_PROP_FRAME_COUNT))
            total_tgt = int(cap_tgt.get(cv2.CAP_PROP_FRAME_COUNT))
            total = min(total_src, total_tgt)
            if total == 0:
                state.status = "One or both videos have no frames"
                state.status_style = "status-error"
                return
            fps = cap_src.get(cv2.CAP_PROP_FPS)
            h_src = int(cap_src.get(cv2.CAP_PROP_FRAME_WIDTH))
            w_src = int(cap_src.get(cv2.CAP_PROP_FRAME_HEIGHT))

        w_tgt = int(cap_tgt.get(cv2.CAP_PROP_FRAME_WIDTH))
        h_tgt = int(cap_tgt.get(cv2.CAP_PROP_FRAME_HEIGHT))

        ar_src = w_src / h_src
        ar_tgt = w_tgt / h_tgt
        ar_diff = abs(ar_src - ar_tgt) > 0.01

        if ar_diff:
            if ar_src >= ar_tgt:
                out_w, out_h = w_src, h_src
                pad_src, pad_tgt = False, True
            else:
                out_w, out_h = w_tgt, h_tgt
                pad_src, pad_tgt = True, False
        else:
            out_w, out_h = w_src, h_src
            pad_src, pad_tgt = False, False

        fd, tmp_path = tempfile.mkstemp(suffix=".mp4")
        os.close(fd)

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(tmp_path, fourcc, fps, (out_w, out_h))

        state.status = f"Video: processing 0/{total} frames"
        state.status_style = "status-warn"

        xp = get_xp()

        for i in range(total):
            if src_is_img:
                src_frame = img_src.copy()
            else:
                ret_src, src_frame = cap_src.read()
                if not ret_src:
                    break

            ret_tgt, tgt_frame = cap_tgt.read()
            if not ret_tgt:
                break

            if pad_src:
                src_frame = letterbox_pad(src_frame, out_w, out_h)
            if pad_tgt:
                tgt_frame = letterbox_pad(tgt_frame, out_w, out_h)
            if not pad_src and not pad_tgt and tgt_frame.shape[:2] != src_frame.shape[:2]:
                tgt_frame = cv2.resize(tgt_frame, (out_w, out_h))

            s_l, s_h, s_s = compute_sort_keys(src_frame, xp)
            t_l, t_h, t_s = compute_sort_keys(tgt_frame, xp)
            s_order = xp_lexsort((s_s, s_h, s_l), xp)
            t_order = xp_lexsort((t_s, t_h, t_l), xp)

            src_flat = xp.array(src_frame.reshape(-1, 3))
            out_flat = xp.empty_like(src_flat, dtype=xp.uint8)
            out_flat[t_order] = src_flat[s_order]
            out_frame = out_flat.reshape(out_h, out_w, 3)
            
            out_frame = to_np(out_frame)

            writer.write(out_frame)

            pct = (i + 1) / total * 100
            bar_len = 20
            filled = int(bar_len * (i + 1) / total)
            bar = "\u2588" * filled + "\u2591" * (bar_len - filled)
            state.status = f"Video: [{bar}] {pct:.1f}% ({i+1}/{total})"

        if not src_is_img:
            cap_src.release()
        cap_tgt.release()
        writer.release()

        state.result_video_path = tmp_path
        state.done = True

        state.status = "Video complete. Playing result..."
        state.status_style = "status"
        cv2.waitKey(500)

        cap = cv2.VideoCapture(tmp_path)
        wn = "Video Rearrangement Result  (ESC/q  anytime  to  quit)"
        cv2.namedWindow(wn, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(wn, 1280, 720)

        while cv2.getWindowProperty(wn, cv2.WND_PROP_VISIBLE) >= 1:
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            cv2.imshow(wn, frame)
            key = cv2.waitKey(30) & 0xFF
            if key in (27, ord("q")):
                break

        cap.release()
        cv2.destroyAllWindows()

    except Exception as e:
        import traceback
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb = traceback.extract_tb(exc_traceback)
        # Find the last frame that is in our own file
        our_frame = next((f for f in reversed(tb) if "main.py" in f.filename), tb[-1])
        line = our_frame.lineno
        msg = str(e)
        if "cupy" in msg.lower():
            global FORCE_CPU
            FORCE_CPU = True
            state.status = f"CuPy Error (L{line}): falling back to CPU..."
            state.using_accelerator = False
            state.acceleration_status = "No (CuPy failed during compute; using CPU)"
        else:
            state.status = f"Error (L{line}): {e}"
        state.status_style = "status-error"
        if state.result_video_path and os.path.exists(state.result_video_path):
            try: os.unlink(state.result_video_path)
            except: pass
            state.result_video_path = ""
    finally:
        state.running = False
        state.done = True


# ── ASCII Art Engine ─────────────────────────────────────────────────

ASCII_CHARS = "@%#*+=-:. "


def _auto_contrast(img: np.ndarray) -> np.ndarray:
    lo, hi = int(img.min()), int(img.max())
    if hi - lo < 1:
        return img
    return ((img.astype(np.float32) - lo) / (hi - lo) * 255).clip(0, 255).astype(np.uint8)


def _floyd_steinberg(gray: np.ndarray, levels: int) -> np.ndarray:
    h, w = gray.shape
    out = gray.astype(np.float32).copy()
    step = 255.0 / (levels - 1)
    for y in range(h):
        for x in range(w):
            old = out[y, x]
            quantized = round(old / step) * step
            out[y, x] = quantized
            err = old - quantized
            if x + 1 < w:
                out[y, x + 1] += err * 7 / 16
            if y + 1 < h:
                if x > 0:
                    out[y + 1, x - 1] += err * 3 / 16
                out[y + 1, x] += err * 5 / 16
                if x + 1 < w:
                    out[y + 1, x + 1] += err * 1 / 16
    return out.clip(0, 255).astype(np.uint8)


def image_to_ascii(path: str, width: int = 120, dither: bool = True) -> str:
    bgr = cv2.imread(path, cv2.IMREAD_COLOR)
    if bgr is None:
        return ""

    gray = (0.299 * bgr[:, :, 2] + 0.587 * bgr[:, :, 1] + 0.114 * bgr[:, :, 0]).astype(np.uint8)

    gray = _auto_contrast(gray)

    h, w = gray.shape[:2]
    aspect = h / w
    height = max(int(width * aspect * 0.55), 1)
    resized = cv2.resize(gray, (width, height), interpolation=cv2.INTER_LANCZOS4)

    ramp = ASCII_CHARS
    ramp_len = len(ramp)

    if dither:
        resized = _floyd_steinberg(resized, ramp_len)

    idx = (resized.astype(np.float32) / 255 * (ramp_len - 1)).round().astype(np.int32)
    idx = np.clip(idx, 0, ramp_len - 1)

    lines = []
    for row in idx:
        lines.append("".join(ramp[i] for i in row))
    return "\n".join(lines)


# ── CLI Handlers ─────────────────────────────────────────────────────

def _progress_bar(current, total, bar_len=20):
    filled = int(bar_len * current / total)
    bar = "\u2588" * filled + "\u2591" * (bar_len - filled)
    print(f"\r  [{bar}] {current}/{total} ({100*current/total:.0f}%)", end="", file=sys.stderr)
    if current == total:
        print(file=sys.stderr)


def _cli_img2img(args):
    try:
        if args.cpu:
            global FORCE_CPU; FORCE_CPU = True

        src_ext = Path(args.source).suffix.lower()
        tgt_ext = Path(args.target).suffix.lower()
        if src_ext not in _IMAGE_EXTS:
            print(f"Error: source must be an image ({', '.join(sorted(_IMAGE_EXTS))})", file=sys.stderr)
            sys.exit(1)
        if tgt_ext not in _IMAGE_EXTS:
            print(f"Error: target must be an image ({', '.join(sorted(_IMAGE_EXTS))})", file=sys.stderr)
            sys.exit(1)

        out_path = args.output
        if not out_path:
            src_stem = Path(args.source).stem
            tgt_stem = Path(args.target).stem
            out_path = f"reconstructed_{src_stem}_from_{tgt_stem}.png"

        result = _compute_rearrangement(args.source, args.target)
        cv2.imwrite(out_path, result)
        print(out_path)

        if args.anim:
            src_stem = Path(args.source).stem
            tgt_stem = Path(args.target).stem
            if args.anim is True:
                anim_path = default_animation_path(src_stem, tgt_stem)
            else:
                anim_path = str(args.anim)
                if not Path(anim_path).suffix:
                    anim_path += ".mp4"

            img_src = cv2.imread(args.source, cv2.IMREAD_COLOR)
            img_tgt = cv2.imread(args.target, cv2.IMREAD_COLOR)
            if img_src is None or img_tgt is None:
                print("Error: could not reload images for animation", file=sys.stderr)
                sys.exit(1)

            scale = args.anim_scale if (args.anim_scale and args.anim_scale > 0) else 1.0
            display_size = None
            if scale != 1.0:
                h, w = img_src.shape[:2]
                display_size = (max(1, int(w * scale)), max(1, int(h * scale)))

            frames = generate_animation_frames(
                img_src, img_tgt, result,
                num_frames=args.anim_frames,
                display_size=display_size,
                include_final_hold=args.anim_hold,
                ease_mode=args.anim_ease,
                three_panel=args.anim_panels,
            )
            write_animation(frames, anim_path, fps=args.anim_fps)
            print(anim_path)

        if args.show:
            img_src = cv2.imread(args.source, cv2.IMREAD_COLOR)
            img_tgt = cv2.imread(args.target, cv2.IMREAD_COLOR)
            h, w = img_src.shape[:2]
            img_tgt = cv2.resize(img_tgt, (w, h))
            sw, sh = get_screen_resolution()
            canvas = np.full((sh, sw, 3), 32, dtype=np.uint8)
            label_h = 22
            pw = sw // 3
            ph = sh - label_h
            sc = min(pw / w, ph / h)
            iw, ih = max(int(w * sc), 1), max(int(h * sc), 1)
            src_s = cv2.resize(img_src, (iw, ih), interpolation=cv2.INTER_LANCZOS4)
            tgt_s = cv2.resize(img_tgt, (iw, ih), interpolation=cv2.INTER_LANCZOS4)
            cx = (pw - iw) // 2
            cy = label_h + (ph - ih) // 2
            canvas[cy:cy+ih, cx:cx+iw] = src_s
            canvas[cy:cy+ih, pw+cx:pw+cx+iw] = tgt_s
            rec_x = 2 * pw + cx
            rec_region = canvas[cy:cy+ih, rec_x:rec_x+iw]
            font = cv2.FONT_HERSHEY_SIMPLEX
            for label, xo in [("Source", 0), ("Target", pw), ("Reconstruction", 2 * pw)]:
                cv2.rectangle(canvas, (xo, 0), (xo + pw, label_h), (0, 0, 0), -1)
                cv2.putText(canvas, label, (xo + 6, 16), font, 0.45, (200, 200, 200), 1)
            wn = "Pixel Rearrangement  (ESC/q  anytime  to  quit)"
            cv2.namedWindow(wn, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(wn, sw, sh)
            rec_region[:] = cv2.resize(result, (iw, ih))
            cv2.imshow(wn, canvas)
            while True:
                key = cv2.waitKey(100) & 0xFF
                if key in (27, ord("q")):
                    break
            cv2.destroyAllWindows()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _cli_vid2vid(args):
    try:
        if args.cpu:
            global FORCE_CPU; FORCE_CPU = True

        src_ext = Path(args.source).suffix.lower()
        tgt_ext = Path(args.target).suffix.lower()
        if src_ext not in _IMAGE_EXTS and src_ext not in _VIDEO_EXTS:
            print(f"Error: source must be an image or video ({', '.join(sorted(_IMAGE_EXTS | _VIDEO_EXTS))})", file=sys.stderr)
            sys.exit(1)
        if tgt_ext not in _VIDEO_EXTS:
            print(f"Error: target must be a video ({', '.join(sorted(_VIDEO_EXTS))})", file=sys.stderr)
            sys.exit(1)

        def progress(cur, total):
            _progress_bar(cur, total)

        result_path = _compute_video_rearrangement(args.source, args.target, progress)

        out_path = args.output
        if not out_path:
            src_stem = Path(args.source).stem
            tgt_stem = Path(args.target).stem
            out_path = f"rearranged_{src_stem}_from_{tgt_stem}.mp4"

        shutil.copy2(result_path, out_path)
        print(out_path)

        try:
            os.unlink(result_path)
        except Exception:
            pass

        if args.show:
            cap = cv2.VideoCapture(out_path)
            wn = "Video Rearrangement Result  (ESC/q  anytime  to  quit)"
            cv2.namedWindow(wn, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(wn, 1280, 720)
            while cv2.getWindowProperty(wn, cv2.WND_PROP_VISIBLE) >= 1:
                ret, frame = cap.read()
                if not ret:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                cv2.imshow(wn, frame)
                key = cv2.waitKey(30) & 0xFF
                if key in (27, ord("q")):
                    break
            cap.release()
            cv2.destroyAllWindows()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _cli_img2ascii(args):
    try:
        ext = Path(args.image).suffix.lower()
        if ext not in _IMAGE_EXTS:
            print(f"Error: input must be an image ({', '.join(sorted(_IMAGE_EXTS))})", file=sys.stderr)
            sys.exit(1)

        ascii_str = image_to_ascii(args.image, args.width, not args.no_dither)
        if not ascii_str:
            print("Error: could not read image", file=sys.stderr)
            sys.exit(1)

        print(ascii_str)

        out_path = args.output
        if not out_path:
            stem = Path(args.image).stem
            out_path = f"{stem}_ascii.txt"
        Path(out_path).write_text(ascii_str, encoding="utf-8")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _cli_aud2aud(args):
    try:
        if args.cpu:
            global FORCE_CPU; FORCE_CPU = True

        src_ext = Path(args.source).suffix.lower()
        tgt_ext = Path(args.target).suffix.lower()
        if src_ext not in _AUDIO_EXTS:
            print(f"Error: source must be an audio file ({', '.join(sorted(_AUDIO_EXTS))})", file=sys.stderr)
            sys.exit(1)
        if tgt_ext not in _AUDIO_EXTS:
            print(f"Error: target must be an audio file ({', '.join(sorted(_AUDIO_EXTS))})", file=sys.stderr)
            sys.exit(1)

        out_path = args.output
        if not out_path:
            src_stem = Path(args.source).stem
            tgt_stem = Path(args.target).stem
            out_path = f"morphed_{src_stem}_from_{tgt_stem}.wav"

        settings = _audio_settings_from_args(args)
        rearrange_audio(args.source, args.target, out_path, settings=settings)
        print(out_path)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _audio_settings_from_args(args):
    d = AudioSettings.default().to_dict()
    if getattr(args, "spectral", False):
        d["remap_spectrum"] = True
    if getattr(args, "no_spectral", False):
        d["remap_spectrum"] = False
    if getattr(args, "time", False):
        d["reorder_time"] = True
    if getattr(args, "no_time", False):
        d["reorder_time"] = False
    if getattr(args, "energy", False):
        d["remap_energy"] = True
    if getattr(args, "no_normalize", False):
        d["normalize"] = False
    if getattr(args, "randomize", False):
        d["randomize"] = True
    if getattr(args, "reverse", False):
        d["reverse"] = True
    if getattr(args, "no_keep_duration", False):
        d["keep_duration"] = False
    if getattr(args, "pitch", None) is not None:
        d["shape_pitch"] = True
        d["pitch_shift_semitones"] = args.pitch
    mapping = {
        "segment_ms": "chunk_ms",
        "crossfade_ms": "crossfade",
        "fft_size": "fft",
        "hop_length": "hop",
        "sort_key": "sort_key",
        "seed": "seed",
        "phase_mode": "phase",
        "dry_wet": "dry_wet",
    }
    for key, aname in mapping.items():
        if getattr(args, aname, None) is not None:
            d[key] = getattr(args, aname)
    return AudioSettings.from_dict(d)


# ── TUI Application ──────────────────────────────────────────────────

class PixelTUI:
    def __init__(self, runtime_config: RuntimeConfig):
        self.runtime_config = runtime_config
        self.state = State(using_accelerator=runtime_config.hardware_acceleration_available)
        self.state.acceleration_status = CUPY_STATUS_TEXT
        if getattr(runtime_config, "audio_settings", None):
            self.state.audio_settings = AudioSettings.from_dict(runtime_config.audio_settings)

        self.kb = KeyBindings()
        self._register_bindings()

        self._app: Application | None = None

    # ── Key Bindings ─────────────────────────────────────────────

    def _register_bindings(self):
        kb = self.kb

        @kb.add("up")
        def _(event):
            if self.state.running or self.state.settings_edit_key is not None:
                return
            if self.state.screen == "audio-settings":
                n = len(AUDIO_SETTINGS_ROWS) + 1
                self.state.cursor = (self.state.cursor - 1) % n
                self._invalidate()
                return
            n = len(self.state.menu)
            self.state.cursor = (self.state.cursor - 1) % n
            self._invalidate()

        @kb.add("down")
        def _(event):
            if self.state.running or self.state.settings_edit_key is not None:
                return
            if self.state.screen == "audio-settings":
                n = len(AUDIO_SETTINGS_ROWS) + 1
                self.state.cursor = (self.state.cursor + 1) % n
                self._invalidate()
                return
            n = len(self.state.menu)
            self.state.cursor = (self.state.cursor + 1) % n
            self._invalidate()

        @kb.add("enter")
        def _(event):
            if not self.state.running:
                if self.state.screen == "audio-settings":
                    if self.state.settings_edit_key is not None:
                        self._commit_setting_edit()
                    else:
                        self._settings_enter(self.state.cursor)
                    return
                self._dispatch(self.state.cursor)

        @kb.add("left")
        def _(event):
            if not self.state.running and self.state.settings_edit_key is None:
                if self.state.screen == "audio-settings":
                    self._settings_step(self.state.cursor, -1)

        @kb.add("right")
        def _(event):
            if not self.state.running and self.state.settings_edit_key is None:
                if self.state.screen == "audio-settings":
                    self._settings_step(self.state.cursor, 1)

        for key, idx in [("1", 0), ("2", 1), ("3", 2), ("4", 3), ("5", 4), ("6", 5), ("7", 6)]:
            @kb.add(key)
            def _(event, idx=idx):
                if self.state.running or self.state.screen == "audio-settings":
                    return
                n = len(self.state.menu)
                if idx < n:
                    self.state.cursor = idx
                    self._dispatch(idx)

        for key in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "-", "."):
            @kb.add(key)
            def _(event, key=key):
                if self.state.running or self.state.settings_edit_key is None:
                    return
                self.state.settings_edit_buffer += key
                self._invalidate()

        @kb.add("backspace")
        def _(event):
            if self.state.settings_edit_key is not None:
                self.state.settings_edit_buffer = self.state.settings_edit_buffer[:-1]
                self._invalidate()

        @kb.add("s-up")
        def _(event):
            if self.state.screen == "ascii" and self.state.result_ascii and not self.state.running:
                self.state.scroll_y = max(0, self.state.scroll_y - 1)
                self._invalidate()

        @kb.add("s-down")
        def _(event):
            if self.state.screen == "ascii" and self.state.result_ascii and not self.state.running:
                self.state.scroll_y += 1
                self._invalidate()

        @kb.add("s-left")
        def _(event):
            if self.state.screen == "ascii" and self.state.result_ascii and not self.state.running:
                self.state.scroll_x = max(0, self.state.scroll_x - 4)
                self._invalidate()

        @kb.add("s-right")
        def _(event):
            if self.state.screen == "ascii" and self.state.result_ascii and not self.state.running:
                self.state.scroll_x += 4
                self._invalidate()

        @kb.add("pageup")
        def _(event):
            if self.state.screen == "ascii" and self.state.result_ascii and not self.state.running:
                jump = (self._app.output.get_size().rows - 12 if self._app else 20)
                self.state.scroll_y = max(0, self.state.scroll_y - jump)
                self._invalidate()

        @kb.add("pagedown")
        def _(event):
            if self.state.screen == "ascii" and self.state.result_ascii and not self.state.running:
                jump = (self._app.output.get_size().rows - 12 if self._app else 20)
                self.state.scroll_y += jump
                self._invalidate()

        @kb.add("q")
        def _(event):
            if not self.state.running and self.state.settings_edit_key is None:
                self._quit()

        @kb.add("escape")
        def _(event):
            if self.state.settings_edit_key is not None:
                self._cancel_setting_edit()
            elif self.state.screen == "audio-settings" and not self.state.running:
                self._back_audio_settings()
            elif not self.state.running:
                self._quit()

        @kb.add("c-c")
        def _(event):
            self._quit()

    # ── Dispatch ─────────────────────────────────────────────────

    def _dispatch(self, idx: int):
        s = self.state.screen
        if s == "main":
            {0: self._enter_image_mode,
             1: self._enter_video_mode,
             2: self._enter_audio_mode,
             3: self._enter_ascii_mode,
             4: self._quit}[idx]()
        elif s == "image":
            {0: self._select_source,
             1: self._select_target,
             2: self._run,
             3: self._save_result,
             4: self._save_animation,
             5: self._back_to_main,
             6: self._quit}[idx]()
        elif s == "video":
            {0: self._select_source_video,
             1: self._select_target_video,
             2: self._run_video,
             3: self._save_result_video,
             4: self._back_to_main,
             5: self._quit}[idx]()
        elif s == "audio":
            {0: self._select_source_audio,
             1: self._select_target_audio,
             2: self._enter_audio_settings,
             3: self._run_audio,
             4: self._play_result_audio,
             5: self._save_result_audio,
             6: self._back_to_main,
             7: self._quit}[idx]()
        elif s == "ascii":
            {0: self._select_source_ascii,
             1: self._run_ascii,
             2: self._copy_result_ascii,
             3: self._save_result_ascii,
             4: self._back_to_main,
             5: self._quit}[idx]()

    # ── Actions ──────────────────────────────────────────────────

    def _enter_image_mode(self):
        self.state.screen = "image"
        self.state.cursor = 0
        self.state.status = "Select source and target images"
        self.state.status_style = "status-info"
        self._refresh_info()
        self._invalidate()

    def _enter_video_mode(self):
        self.state.screen = "video"
        self.state.cursor = 0
        self.state.status = "Select source and target videos"
        self.state.status_style = "status-info"
        self._refresh_info()
        self._invalidate()

    def _enter_audio_mode(self):
        self.state.screen = "audio"
        self.state.cursor = 0
        self.state.status = "Select source and target audio files"
        self.state.status_style = "status-info"
        self._refresh_info()
        self._invalidate()

    def _enter_audio_settings(self):
        self.state.screen = "audio-settings"
        self.state.cursor = 0
        self.state.settings_edit_key = None
        self.state.settings_edit_buffer = ""
        self.state.status = "Adjust the audio pipeline: enter to edit, arrows to step"
        self.state.status_style = "status-info"
        self._invalidate()

    def _back_audio_settings(self):
        self.state.screen = "audio"
        self.state.cursor = 2
        self.state.status = "Advanced options updated"
        self.state.status_style = "status"
        self._invalidate()

    def _settings_get(self, key):
        return getattr(self.state.audio_settings, key)

    def _settings_set(self, key, value):
        setattr(self.state.audio_settings, key, value)
        self._persist_audio_settings()
        self._invalidate()

    def _persist_audio_settings(self):
        try:
            save_audio_settings(self.state.audio_settings.to_dict())
        except Exception:
            pass

    def _settings_row(self, idx):
        """Return the row descriptor for a settings index, or None for reset."""
        if 0 <= idx < len(AUDIO_SETTINGS_ROWS):
            return AUDIO_SETTINGS_ROWS[idx]
        return None

    def _settings_step(self, idx, direction):
        row = self._settings_row(idx)
        if row is None:
            return
        key, label, kind, *extra = row
        if kind == "bool":
            self._settings_set(key, not self._settings_get(key))
            return
        if kind == "choice":
            opts = extra[0]
            cur = self._settings_get(key)
            if cur in opts:
                new = opts[(opts.index(cur) + (1 if direction > 0 else -1)) % len(opts)]
            else:
                new = opts[0]
            self._settings_set(key, new)
            return
        step, lo, hi = extra[0]
        cur = self._settings_get(key)
        value = (float(cur) if kind == "float" else int(cur)) + direction * step
        value = min(max(value, lo), hi)
        self._settings_set(key, int(value) if kind == "int" else round(value, 4))

    def _settings_enter(self, idx):
        row = self._settings_row(idx)
        if row is None:
            self._reset_audio_settings()
            return
        key, label, kind, *extra = row
        if kind == "bool":
            self._settings_set(key, not self._settings_get(key))
        elif kind == "choice":
            self._settings_step(idx, 1)
        else:
            self.state.settings_edit_key = key
            self.state.settings_edit_buffer = str(self._settings_get(key))
            self._invalidate()

    def _commit_setting_edit(self):
        key = self.state.settings_edit_key
        row = None
        for r in AUDIO_SETTINGS_ROWS:
            if r[0] == key:
                row = r
                break
        if row is not None:
            kind = row[2]
            extra = row[3:]
            buf = self.state.settings_edit_buffer.strip()
            try:
                if kind == "int":
                    value = int(float(buf)) if buf else 0
                else:
                    value = float(buf) if buf else 0.0
                if extra:
                    step, lo, hi = extra[0]
                    value = min(max(value, lo), hi)
                value = int(value) if kind == "int" else round(value, 4)
                self._settings_set(key, value)
            except ValueError:
                pass
        self.state.settings_edit_key = None
        self.state.settings_edit_buffer = ""
        self._invalidate()

    def _cancel_setting_edit(self):
        self.state.settings_edit_key = None
        self.state.settings_edit_buffer = ""
        self._invalidate()

    def _reset_audio_settings(self):
        self.state.audio_settings = AudioSettings.default()
        self._persist_audio_settings()
        self.state.status = "Advanced options reset to defaults"
        self.state.status_style = "status"
        self._invalidate()

    def _back_to_main(self):
        self.state.screen = "main"
        self.state.cursor = 0
        self.state.status = "Ready"
        self.state.status_style = "status"
        self._invalidate()

    def _select_source(self):
        path = select_file("Select Source Image", "image")
        if path:
            self.state.source = path
            self._refresh_info()
            self.state.status = f"Source: {Path(path).name}"
            self.state.status_style = "status"
        else:
            self.state.status = "Selection cancelled"
            self.state.status_style = "status-info"
        self._invalidate()

    def _select_target(self):
        path = select_file("Select Target Image", "image")
        if path:
            self.state.target = path
            self._refresh_info()
            self.state.status = f"Target: {Path(path).name}"
            self.state.status_style = "status"
        else:
            self.state.status = "Selection cancelled"
            self.state.status_style = "status-info"
        self._invalidate()

    def _select_source_video(self):
        path = select_file("Select Source Image or Video", "media")
        if path:
            self.state.source = path
            self._refresh_info()
            self.state.status = f"Source: {Path(path).name}"
            self.state.status_style = "status"
        else:
            self.state.status = "Selection cancelled"
            self.state.status_style = "status-info"
        self._invalidate()

    def _select_target_video(self):
        path = select_file("Select Target Video", "video")
        if path:
            self.state.target = path
            self._refresh_info()
            self.state.status = f"Target: {Path(path).name}"
            self.state.status_style = "status"
        else:
            self.state.status = "Selection cancelled"
            self.state.status_style = "status-info"
        self._invalidate()

    def _select_source_audio(self):
        path = select_file("Select Source Audio", "audio")
        if path:
            self.state.source = path
            self._refresh_info()
            self.state.status = f"Source: {Path(path).name}"
            self.state.status_style = "status"
        else:
            self.state.status = "Selection cancelled"
            self.state.status_style = "status-info"
        self._invalidate()

    def _select_target_audio(self):
        path = select_file("Select Target Audio", "audio")
        if path:
            self.state.target = path
            self._refresh_info()
            self.state.status = f"Target: {Path(path).name}"
            self.state.status_style = "status"
        else:
            self.state.status = "Selection cancelled"
            self.state.status_style = "status-info"
        self._invalidate()

    def _run(self):
        if not self.state.source:
            self.state.status = "Select a source image first!"
            self.state.status_style = "status-error"; self._invalidate(); return
        if not self.state.target:
            self.state.status = "Select a target image first!"
            self.state.status_style = "status-error"; self._invalidate(); return

        self.state.running = True
        self.state.done = False
        self.state.result = None
        self.state.status = "Rearrangement running in OpenCV window\u2026"
        self.state.status_style = "status-warn"
        self._invalidate()

        t = threading.Thread(
            target=rearrange,
            args=(self.state.source, self.state.target, self.state),
            daemon=True,
        )
        t.start()

        async def waiter():
            while t.is_alive():
                await asyncio.sleep(0.5)
                self._invalidate()
            self._invalidate()

        if self._app:
            asyncio.create_task(waiter())

    def _run_video(self):
        if not self.state.source:
            self.state.status = "Select a source video first!"
            self.state.status_style = "status-error"; self._invalidate(); return
        if not self.state.target:
            self.state.status = "Select a target video first!"
            self.state.status_style = "status-error"; self._invalidate(); return

        if self.state.result_video_path and os.path.exists(self.state.result_video_path):
            try: os.unlink(self.state.result_video_path)
            except: pass
        self.state.result_video_path = ""

        self.state.running = True
        self.state.done = False
        self.state.result = None
        self.state.status = "Video rearrangement running\u2026"
        self.state.status_style = "status-warn"
        self._invalidate()

        t = threading.Thread(
            target=rearrange_video,
            args=(self.state.source, self.state.target, self.state),
            daemon=True,
        )
        t.start()

        async def waiter():
            while t.is_alive():
                await asyncio.sleep(0.5)
                self._invalidate()
            self._invalidate()

        if self._app:
            asyncio.create_task(waiter())

    def _run_audio(self):
        if not self.state.source:
            self.state.status = "Select a source audio file first!"
            self.state.status_style = "status-error"; self._invalidate(); return
        if not self.state.target:
            self.state.status = "Select a target audio file first!"
            self.state.status_style = "status-error"; self._invalidate(); return

        self.state.running = True
        self.state.done = False
        self.state.result_audio_path = ""
        self.state.status = "Audio rearrangement running\u2026"
        self.state.status_style = "status-warn"
        self._invalidate()

        out_path = tempfile.mktemp(suffix=".wav")

        def work():
            try:
                rearrange_audio(
                    self.state.source, self.state.target, out_path,
                    settings=self.state.audio_settings,
                )
                self.state.result_audio_path = out_path
                self.state.done = True
                self.state.status = "Audio rearrangement complete!"
                self.state.status_style = "status"
            except Exception as e:
                self.state.status = f"Error: {e}"
                self.state.status_style = "status-error"
                if os.path.exists(out_path):
                    try: os.unlink(out_path)
                    except: pass
            self.state.running = False
            self._invalidate()

        t = threading.Thread(target=work, daemon=True)
        t.start()

        async def waiter():
            while t.is_alive():
                await asyncio.sleep(0.5)
                self._invalidate()
            self._invalidate()

        if self._app:
            asyncio.create_task(waiter())

    def _save_result_audio(self):
        if not self.state.result_audio_path or not os.path.exists(self.state.result_audio_path):
            self.state.status = "No result to save \u2014 run rearrangement first!"
            self.state.status_style = "status-error"
            self._invalidate()
            return

        src_stem = Path(self.state.source).stem
        tgt_stem = Path(self.state.target).stem
        out_name = f"morphed_{src_stem}_from_{tgt_stem}.wav"
        out_path = Path.cwd() / out_name
        shutil.copy2(self.state.result_audio_path, str(out_path))
        self.state.status = f"Saved to {out_path}"
        self.state.status_style = "status"
        self._invalidate()

    def _play_result_audio(self):
        if not self.state.result_audio_path or not os.path.exists(self.state.result_audio_path):
            self.state.status = "No result to play \u2014 run rearrangement first!"
            self.state.status_style = "status-error"
            self._invalidate()
            return

        try:
            if os.name == "nt":
                os.startfile(self.state.result_audio_path)
            else:
                subprocess.Popen(["xdg-open", self.state.result_audio_path])
            self.state.status = "Playing result audio\u2026"
            self.state.status_style = "status"
        except Exception as e:
            self.state.status = f"Play error: {e}"
            self.state.status_style = "status-error"
        self._invalidate()

    def _enter_ascii_mode(self):
        self.state.screen = "ascii"
        self.state.cursor = 0
        self.state.scroll_x = 0
        self.state.scroll_y = 0
        self.state.status = "Select an image to convert to ASCII art"
        self.state.status_style = "status-info"
        self._invalidate()

    def _select_source_ascii(self):
        path = select_file("Select Image for ASCII", "image")
        if path:
            self.state.source = path
            self.state.status = f"Image: {Path(path).name}"
            self.state.status_style = "status"
        else:
            self.state.status = "Selection cancelled"
            self.state.status_style = "status-info"
        self._invalidate()

    def _run_ascii(self):
        if not self.state.source:
            self.state.status = "Select an image first!"
            self.state.status_style = "status-error"
            self._invalidate()
            return

        self.state.status = "Converting to ASCII art\u2026"
        self.state.status_style = "status-warn"
        self._invalidate()

        self.state.scroll_x = 0
        self.state.scroll_y = 0
        width = min(120, max(40, self._app.output.get_size().columns - 4 if self._app else 120))

        try:
            result = image_to_ascii(self.state.source, width)
            if not result:
                self.state.status = "Failed to read image"
                self.state.status_style = "status-error"
            else:
                self.state.result_ascii = result
                self.state.done = True
                self.state.status = f"ASCII art generated ({len(result.split(chr(10)))} rows \u00d7 {width} cols)"
                self.state.status_style = "status"
        except Exception as e:
            self.state.status = f"Error: {e}"
            self.state.status_style = "status-error"
        self._invalidate()

    def _save_result_ascii(self):
        if not self.state.result_ascii:
            self.state.status = "No result to save \u2014 run conversion first!"
            self.state.status_style = "status-error"
            self._invalidate()
            return

        src_stem = Path(self.state.source).stem
        out_name = f"{src_stem}_ascii.txt"
        out_path = Path.cwd() / out_name
        try:
            out_path.write_text(self.state.result_ascii, encoding="utf-8")
            self.state.status = f"Saved to {out_path}"
            self.state.status_style = "status"
        except Exception as e:
            self.state.status = f"Save error: {e}"
            self.state.status_style = "status-error"
        self._invalidate()

    def _copy_result_ascii(self):
        if not self.state.result_ascii:
            self.state.status = "No result to copy \u2014 run conversion first!"
            self.state.status_style = "status-error"
            self._invalidate()
            return
        try:
            import subprocess
            subprocess.run(
                ["clip"], text=True, input=self.state.result_ascii,
                creationflags=0x08000000,
            )
            size = len(self.state.result_ascii)
            self.state.status = f"Copied {size} characters to clipboard"
            self.state.status_style = "status"
        except Exception as e:
            self.state.status = f"Clipboard error: {e}"
            self.state.status_style = "status-error"
        self._invalidate()

    def _refresh_info(self):
        s = self.state
        parts = []
        for path in (s.source, s.target):
            if not path:
                continue
            try:
                if s.screen == "image":
                    img = cv2.imread(path, cv2.IMREAD_COLOR)
                    if img is not None:
                        h, w = img.shape[:2]
                        kb = Path(path).stat().st_size / 1024
                        parts.append(f"{Path(path).name}  {w}\u00d7{h}  ({kb:.0f} KB)")
                elif s.screen == "audio":
                    if HAS_SOUNDFILE:
                        info = sf.info(path)
                        dur = info.duration
                        sr = info.samplerate
                        ch = info.channels
                        kb = Path(path).stat().st_size / 1024
                        parts.append(f"{Path(path).name}  {sr}Hz  {ch}ch  {dur:.1f}s  ({kb:.0f} KB)")
                    else:
                        kb = Path(path).stat().st_size / 1024
                        parts.append(f"{Path(path).name}  ({kb:.0f} KB)")
                else:
                    ext = Path(path).suffix.lower()
                    if ext in _IMAGE_EXTS:
                        img = cv2.imread(path, cv2.IMREAD_COLOR)
                        if img is not None:
                            h, w = img.shape[:2]
                            kb = Path(path).stat().st_size / 1024
                            parts.append(f"{Path(path).name}  {w}\u00d7{h}  ({kb:.0f} KB)")
                    else:
                        cap = cv2.VideoCapture(path)
                        if cap.isOpened():
                            total_f = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                            vfps = cap.get(cv2.CAP_PROP_FPS)
                            dur = total_f / vfps if vfps > 0 else 0
                            vw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                            vh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                            cap.release()
                            parts.append(f"{Path(path).name}  {vw}\u00d7{vh}  {total_f}f  {dur:.1f}s")
            except Exception:
                parts.append(Path(path).name)
        if s.source and s.target:
            parts.append("Ready!")
        s.info = "  |  ".join(parts) if parts else ""

    def _save_result(self):
        if self.state.result is None:
            self.state.status = "No result to save \u2014 run rearrangement first!"
            self.state.status_style = "status-error"
            self._invalidate()
            return

        src_stem = Path(self.state.source).stem
        tgt_stem = Path(self.state.target).stem
        out_name = f"reconstructed_{src_stem}_from_{tgt_stem}.png"
        out_path = Path.cwd() / out_name
        cv2.imwrite(str(out_path), self.state.result)
        self.state.status = f"Saved to {out_path}"
        self.state.status_style = "status"
        self._invalidate()

    def _save_animation(self):
        if not self.state.source or not self.state.target:
            self.state.status = "Select source and target images first!"
            self.state.status_style = "status-error"; self._invalidate(); return
        if self.state.result is None or not self.state.done:
            self.state.status = "No result to save \u2014 run rearrangement first!"
            self.state.status_style = "status-error"; self._invalidate(); return

        src_stem = Path(self.state.source).stem
        tgt_stem = Path(self.state.target).stem
        out_path = Path.cwd() / default_animation_path(src_stem, tgt_stem)

        self.state.running = True
        self.state.status = "Saving animation\u2026"
        self.state.status_style = "status-warn"
        self._invalidate()

        def work():
            try:
                img_src = cv2.imread(self.state.source, cv2.IMREAD_COLOR)
                img_tgt = cv2.imread(self.state.target, cv2.IMREAD_COLOR)
                if img_src is None or img_tgt is None:
                    raise IOError("could not reload source/target images")
                frames = generate_animation_frames(
                    img_src, img_tgt, self.state.result,
                    num_frames=60,
                    include_final_hold=12,
                    ease_mode="linear",
                )
                write_animation(frames, str(out_path), fps=30.0)
                self.state.status = f"Saved animation to {out_path}"
                self.state.status_style = "status"
            except Exception as e:
                self.state.status = f"Animation error: {e}"
                self.state.status_style = "status-error"
            self.state.running = False
            self._invalidate()

        t = threading.Thread(target=work, daemon=True)
        t.start()

        async def waiter():
            while t.is_alive():
                await asyncio.sleep(0.5)
                self._invalidate()
            self._invalidate()

        if self._app:
            asyncio.create_task(waiter())

    def _save_result_video(self):
        src_stem = Path(self.state.source).stem
        tgt_stem = Path(self.state.target).stem
        out_name = f"rearranged_{src_stem}_from_{tgt_stem}.mp4"
        out_path = Path.cwd() / out_name
        if self.state.result_video_path and os.path.exists(self.state.result_video_path):
            shutil.copy2(self.state.result_video_path, str(out_path))
            self.state.status = f"Saved to {out_path}"
            self.state.status_style = "status"
        else:
            self.state.status = "No result to save \u2014 run rearrangement first!"
            self.state.status_style = "status-error"
        self._invalidate()

    def _quit(self):
        cv2.destroyAllWindows()
        for p in (self.state.result_video_path, self.state.result_audio_path):
            if p and os.path.exists(p):
                try: os.unlink(p)
                except: pass
        if self._app:
            self._app.exit()
        sys.exit(0)

    # ── UI Rendering ─────────────────────────────────────────────

    def _build_text(self):
        s = self.state
        F: list[tuple[str, str]] = []

        def push(style, text):
            if text:
                F.append((style, text))

        accel_text = s.acceleration_status

        if s.screen == "main":
            for line in ASCII_ART:
                push("bold #00d787", "    " + line + "\n")
            push("", "\n")

            for i, (label, desc) in enumerate(s.menu):
                cursor = "\u25cf" if i == s.cursor else "\u25cb"
                sel = i == s.cursor
                st = "bold #000000 bg:#00d787" if sel else "bold #ffffff"
                push(st, f"  {cursor} {label}  ")
                push("", "  ")
                push("#6c6c6c", f"{desc}\n")

            push("", "\n")
            push("#3a3a3a", "  " + "\u2501" * 55)
            push("", "\n  ")

            c = {"status": "#5faf5f", "status-error": "#ff5f5f",
                 "status-warn": "#ffaf5f", "status-info": "#878787 italic"}
            push(c.get(s.status_style, "#878787 italic"), s.status)
            push("", "\n")
            n = len(s.menu)
            push("#585858 italic", f"\u2191\u2193  navigate  \u2022  Enter  select  \u2022  1-{n}  shortcut  \u2022  q  quit")
            push("#585858 italic", "\n")
            push("#585858 italic", f"  Hardware acceleration: {accel_text}")
            push("", "\n")
        elif s.screen == "ascii":
            push("bold #00d787", "  \u25a0 Pixel Rearrangement Tool")
            push("bold #5f87ff", "  \u2014  [ ASCII Art Mode ]")
            push("", "\n")
            push("#3a3a3a", "  " + "\u2501" * 55)
            push("", "\n")
            push("bold #5f87ff", "\n  Image:  ")
            push("#87afff" if s.source else "#585858 italic",
                 s.source if s.source else "\u2014 not selected \u2014")
            push("", "\n\n")

            if s.result_ascii:
                all_lines = s.result_ascii.split("\n")
                total_rows = len(all_lines)
                total_cols = max(len(l) for l in all_lines) if all_lines else 0

                vp_rows = max(3, (self._app.output.get_size().rows - 18
                                  if self._app else 10))
                vp_cols = (self._app.output.get_size().columns - 5
                           if self._app else 76)

                s.scroll_y = max(0, min(s.scroll_y, total_rows - vp_rows))
                s.scroll_x = max(0, min(s.scroll_x, total_cols - vp_cols))

                scroll_ind_y = (" \u2191" if s.scroll_y > 0 else "  ") + \
                               (" \u2193" if s.scroll_y + vp_rows < total_rows else "  ")
                scroll_ind_x = ("\u2190" if s.scroll_x > 0 else " ") + \
                               ("\u2192" if s.scroll_x + vp_cols < total_cols else " ")
                info = f"{total_rows}\u00d7{total_cols} {scroll_ind_y} {scroll_ind_x}"
                push("#6c6c6c", f"  {info}\n")
                push("", "  " + "\u2500" * min(vp_cols, total_cols) + "\n")
                for line in all_lines[s.scroll_y:s.scroll_y + vp_rows]:
                    slice = line[s.scroll_x:s.scroll_x + vp_cols]
                    push("", "  " + slice + "\n")
                push("", "  " + "\u2500" * min(vp_cols, total_cols) + "\n")
                push("#585858 italic", "  Shift+arrows scroll  \u2022  PgUp/PgDn jump\n")
            elif s.done:
                push("status-warn", "  Conversion produced no output.\n")

            push("#3a3a3a", "  " + "\u2500" * 55)
            push("", "\n")

            for i, (label, desc) in enumerate(s.menu):
                cursor = "\u25cf" if i == s.cursor else "\u25cb"
                sel = i == s.cursor
                is_run = i == 1
                is_copy = i == 2
                is_save = i == 3
                disabled = (is_run and not s.source) or (is_copy and not s.done) or (is_save and not s.done)
                st = ("bold #000000 bg:#00d787" if sel else
                      "#585858 italic" if disabled else
                      "bold #ffffff")
                push(st, f"  {cursor} {label}  ")
                push("", "  ")
                push("#3a3a3a" if disabled else "#6c6c6c", f"{desc}\n")

            push("", "\n")
            push("#3a3a3a", "  " + "\u2500" * 55)
            push("", "\n  ")

            c = {"status": "#5faf5f", "status-error": "#ff5f5f",
                 "status-warn": "#ffaf5f", "status-info": "#878787 italic"}
            push(c.get(s.status_style, "#878787 italic"), s.status)
            push("", "\n")

            n = len(s.menu)
            help_extra = "  \u2022  Shift+arrows  \u2022  PgUp/Dn jump" if s.result_ascii else ""
            push("#585858 italic", f"\u2191\u2193  navigate  \u2022  Enter  select  \u2022  1-{n}  shortcut{help_extra}  \u2022  q  quit")
            push("#585858 italic", "\n")
        elif s.screen == "audio-settings":
            push("bold #00d787", "  \u25a0 Pixel Rearrangement Tool")
            push("bold #5f87ff", "  \u2014  [ Audio \u00b7 Advanced Options ]")
            push("", "\n")
            push("#3a3a3a", "  " + "\u2501" * 55)
            push("", "\n")

            section_starts = {
                0: "What the rearrangement may change",
                5: "Segmentation / DSP",
                9: "Sorting / variation",
                13: "Pitch",
                15: "Spectral phase",
                16: "Output",
            }

            editing = s.settings_edit_key
            n_rows = len(AUDIO_SETTINGS_ROWS) + 1
            for i in range(n_rows):
                sel = i == s.cursor
                if i < len(AUDIO_SETTINGS_ROWS):
                    row = AUDIO_SETTINGS_ROWS[i]
                    if i in section_starts:
                        push("", "\n")
                        push("bold #00d787", f"  \u25a0 {section_starts[i]}")
                        push("", "\n")
                    key, label, kind, *extra = row
                    cur = s.audio_settings.__dict__.get(key)
                    if kind == "bool":
                        value_txt = "on" if cur else "off"
                    elif kind == "choice":
                        value_txt = str(cur)
                    elif kind == "int":
                        value_txt = str(cur)
                    else:
                        value_txt = ("%.3f" % cur).rstrip("0").rstrip(".")
                    if key == editing:
                        value_txt = "> " + s.settings_edit_buffer + " \u2588"
                        carat = "\u25ce"
                    else:
                        carat = "\u25cf" if sel else "\u25cb"
                    st = ("bold #000000 bg:#00d787" if sel else
                          "bold #88ffd0" if key == editing else
                          ("bold #5fafff" if kind in ("int", "float", "choice") else "bold #ffffff"))
                    push(st, f"  {carat} {label}")
                    push("", "   ")
                    push("bold #ffffff", value_txt)
                    push("", "\n")
                else:
                    carat = "\u25cf" if sel else "\u25cb"
                    st = ("bold #000000 bg:#ff5f5f" if sel else "bold #ff5f5f")
                    push(st, f"  {carat} Reset to default settings")
                    push("", "\n")

            push("", "\n")
            push("#3a3a3a", "  " + "\u2500" * 55)
            push("", "\n  ")

            c = {"status": "#5faf5f", "status-error": "#ff5f5f",
                 "status-warn": "#ffaf5f", "status-info": "#878787 italic"}
            push(c.get(s.status_style, "#878787 italic"), s.status)
            push("", "\n")

            if editing:
                hint = "type value  \u2022  Enter commit  \u2022  Esc cancel"
            else:
                hint = "\u2191\u2193  move  \u2022  Enter toggle/edit  \u2022  \u2190\u2192  step  \u2022  Esc back"
            push("#585858 italic", "  " + hint)
            push("#585858 italic", "\n")
        else:
            mode_label = {"image": "Image Mode", "video": "Video Mode", "audio": "Audio Mode"}[s.screen]
            push("bold #00d787", f"  \u25a0 Pixel Rearrangement Tool")
            push("bold #5f87ff", f"  \u2014  [ {mode_label} ]")
            push("", "\n")
            push("#3a3a3a", "  " + "\u2501" * 55)
            push("", "\n")
            push("bold #5f87ff", "\n  Source:  ")
            push("#87afff" if s.source else "#585858 italic",
                 s.source if s.source else "\u2014 not selected \u2014")

            push("bold #5f87ff", "\n  Target:  ")
            push("#87afff" if s.target else "#585858 italic",
                 s.target if s.target else "\u2014 not selected \u2014")

            if s.info:
                push("", "\n  ")
                push("#878787 italic", s.info)

            push("", "\n\n")
            push("#3a3a3a", "  " + "\u2500" * 55)
            push("", "\n")

            for i, (label, desc) in enumerate(s.menu):
                cursor = "\u25cf" if i == s.cursor else "\u25cb"
                sel = i == s.cursor
                is_play = s.screen == "audio" and i == 4
                is_save = (s.screen in ("image", "video") and i == 3) or (s.screen == "audio" and i == 5)
                is_anim = s.screen == "image" and i == 4
                disabled = (is_play or is_save or is_anim) and not s.done
                st = ("bold #000000 bg:#00d787" if sel else
                      "#585858 italic" if disabled else
                      "bold #ffffff")
                push(st, f"  {cursor} {label}  ")
                push("", "  ")
                push("#3a3a3a" if disabled else "#6c6c6c", f"{desc}\n")

            push("", "\n")
            push("#3a3a3a", "  " + "\u2500" * 55)
            push("", "\n  ")

            c = {"status": "#5faf5f", "status-error": "#ff5f5f",
                 "status-warn": "#ffaf5f", "status-info": "#878787 italic"}
            push(c.get(s.status_style, "#878787 italic"), s.status)
            push("", "\n")

            n = len(s.menu)
            push("#585858 italic", f"\u2191\u2193  navigate  \u2022  Enter  select  \u2022  1-{n}  shortcut  \u2022  q  quit")
            push("#585858 italic", "\n")
            push("#585858 italic", f"  Hardware acceleration: {accel_text}")
            push("", "\n")

        return F

    def _build_layout(self):
        control = FormattedTextControl(
            text=self._build_text,
            show_cursor=False,
        )
        return Layout(Window(content=control, dont_extend_height=False))

    def _invalidate(self):
        try:
            if self._app:
                self._app.invalidate()
        except Exception:
            pass

    # ── Run ──────────────────────────────────────────────────────

    def run(self):
        self._app = Application(
            layout=self._build_layout(),
            key_bindings=self.kb,
            style=STYLE,
            mouse_support=False,
            full_screen=True,
        )
        try:
            self._app.run()
        except KeyboardInterrupt:
            self._quit()


def main():
    parser = argparse.ArgumentParser(
        prog="pixelification",
        description="Rearrange image pixels via colour-sort optimal transport.",
    )
    parser.add_argument("--version", "-v", action="store_true", help="print version")

    _orig_error = parser.error
    def _parser_error(msg):
        if "invalid choice" in msg:
            _orig_error(
                "missing subcommand.\n\n"
                "  Usage: pixelification <command> [arguments]\n\n"
                "  Commands:\n"
                "    img2img   <source> <target>   Rearrange pixels between two images\n"
                "    vid2vid   <source> <target>   Rearrange frames between two videos\n"
                "    img2ascii <image>             Convert an image to ASCII art\n"
                "    aud2aud   <source> <target>   Rearrange audio (spectral cross-synthesis by default)\n"
                "    help                          Show this help message"
            )
        _orig_error(msg)
    parser.error = _parser_error

    sub = parser.add_subparsers(dest="command", metavar="")

    p_img2img = sub.add_parser("img2img", help="rearrange pixels between two images")
    p_img2img.add_argument("source", help="source image path")
    p_img2img.add_argument("target", help="target image path")
    p_img2img.add_argument("-o", "--output", help="output image path (default: auto-named)")
    p_img2img.add_argument("--show", action="store_true", help="show the result in an OpenCV window")
    p_img2img.add_argument("--cpu", action="store_true", help="force CPU mode")
    p_img2img.add_argument("--anim", nargs="?", const=True, default=None, metavar="PATH",
                           help="also export the pixel-slide animation (optional path; default: anim_<src>_from_<tgt>.mp4)")
    p_img2img.add_argument("--anim-frames", type=int, default=60,
                           help="animation frame count (default: 60)")
    p_img2img.add_argument("--anim-fps", type=float, default=30.0,
                           help="animation frames per second (default: 30)")
    p_img2img.add_argument("--anim-scale", type=float, default=1.0,
                           help="export resolution scale relative to source (default: 1.0 = full resolution)")
    p_img2img.add_argument("--anim-ease", choices=["linear", "ease-in-out", "ease-out"],
                           default="linear", help="motion easing (default: linear)")
    p_img2img.add_argument("--anim-hold", type=int, default=12,
                           help="extra static frames of final image at the end (default: 12)")
    p_img2img.add_argument("--anim-panels", action="store_true",
                           help="render Source | Target | Reconstruction panels in the export")

    p_vid2vid = sub.add_parser("vid2vid", help="rearrange frames between two videos (or image->video)")
    p_vid2vid.add_argument("source", help="source video or image path")
    p_vid2vid.add_argument("target", help="target video path")
    p_vid2vid.add_argument("-o", "--output", help="output video path (default: auto-named)")
    p_vid2vid.add_argument("--show", action="store_true", help="play the result in an OpenCV window")
    p_vid2vid.add_argument("--cpu", action="store_true", help="force CPU mode")

    p_ascii = sub.add_parser("img2ascii", help="convert an image to ASCII art")
    p_ascii.add_argument("image", help="source image path")
    p_ascii.add_argument("-o", "--output", help="output text path (default: auto-named)")
    p_ascii.add_argument("-w", "--width", type=int, default=120, help="ASCII output width in characters (default: 120)")
    p_ascii.add_argument("--no-dither", action="store_true", help="disable Floyd-Steinberg dithering")

    p_aud2aud = sub.add_parser("aud2aud", help="rearrange audio (spectral cross-synthesis by default)")
    p_aud2aud.add_argument("source", help="source audio path")
    p_aud2aud.add_argument("target", help="target audio path")
    p_aud2aud.add_argument("-o", "--output", help="output audio path (default: auto-named)")
    p_aud2aud.add_argument("--cpu", action="store_true", help="force CPU mode")
    p_aud2aud.add_argument("--spectral", action="store_true",
                          help="enable spectral magnitude remapping (STFT, on by default)")
    p_aud2aud.add_argument("--no-spectral", action="store_true",
                          help="disable spectral frequency remapping")
    p_aud2aud.add_argument("--time", action="store_true",
                          help="enable time-domain segment reordering")
    p_aud2aud.add_argument("--no-time", action="store_true",
                          help="disable time-domain segment reordering")
    p_aud2aud.add_argument("--chunk-ms", type=float,
                          help="segment length in ms for time reorder (default: 60)")
    p_aud2aud.add_argument("--crossfade", type=float,
                          help="crossfade length in ms between segments (default: 0 = hard cuts)")
    p_aud2aud.add_argument("--fft", type=int, help="FFT size for spectral mode (default: 2048)")
    p_aud2aud.add_argument("--hop", type=int, help="hop length for spectral mode (default: 512)")
    p_aud2aud.add_argument("--sort-key", choices=["energy", "amplitude", "zcr", "centroid", "none"],
                          help="per-segment sort key (default: energy)")
    p_aud2aud.add_argument("--randomize", action="store_true",
                          help="randomly shuffle segments instead of sorting")
    p_aud2aud.add_argument("--seed", type=int, help="random seed (default: 0)")
    p_aud2aud.add_argument("--reverse", action="store_true", help="reverse the segment order")
    p_aud2aud.add_argument("--pitch", type=float,
                          help="pitch shift in semitones, e.g. -12 or +7")
    p_aud2aud.add_argument("--no-keep-duration", action="store_true",
                          help="let pitch shifting also change the duration")
    p_aud2aud.add_argument("--phase", choices=["source", "target", "random"],
                          help="spectral phase source (default: source)")
    p_aud2aud.add_argument("--energy", action="store_true",
                          help="match per-segment loudness to the target")
    p_aud2aud.add_argument("--dry-wet", type=float, choices=[round(x / 20.0, 2) for x in range(0, 21)],
                          help="dry/wet mix 0.0-1.0 (default: 0 = full effect)")
    p_aud2aud.add_argument("--no-normalize", action="store_true",
                          help="disable output peak normalization")

    p_help = sub.add_parser("help", help="show this help message and exit")

    args = parser.parse_args()

    if args.version:
        try:
            print(f"pixelification {version('pixelification')}")
        except PackageNotFoundError:
            print("pixelification (local development)")
        return

    if not args.command:
        runtime_config = load_or_create_runtime_config(HAS_CUPY)
        PixelTUI(runtime_config).run()
        return

    handlers = {
        "img2img": _cli_img2img,
        "vid2vid": _cli_vid2vid,
        "img2ascii": _cli_img2ascii,
        "aud2aud": _cli_aud2aud,
        "help": lambda _: parser.print_help(),
    }
    signal.signal(signal.SIGINT, _sigint_handler)

    try:
        handlers[args.command](args)
    except KeyboardInterrupt:
        print(file=sys.stderr)
        print("Interrupted.", file=sys.stderr)
        os._exit(1)


# ── Entry Point ──────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
