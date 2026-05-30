"""
Pixel Rearrangement Tool — Keyboard-Navigated Terminal UI

Rearrange image pixels or video frames via colour-sort optimal transport.
OpenCV window shows the result (animation for images, playback for video).
"""

import asyncio
import cv2
import numpy as np
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from importlib.metadata import version, PackageNotFoundError

from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, Window, FormattedTextControl
from prompt_toolkit.styles import Style
from pixelification.runtime import RuntimeConfig, load_or_create_runtime_config

# ── GPU & Accelerator Support ────────────────────────────────────────

FORCE_CPU = False

try:
    import cupy as cp
except ImportError:
    cp = None
    HAS_CUPY = False
else:
    def _probe_cupy() -> bool:
        try:
            if cp.cuda.runtime.getDeviceCount() <= 0:
                return False
            test = cp.zeros((16,), dtype=cp.float32)
            test = test * test + 1
            cp.cuda.Stream.null.synchronize()
            _ = float(test.sum().get())
            return True
        except Exception:
            return False

    HAS_CUPY = _probe_cupy()

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
    if HAS_CUPY and xp is cp:
        a_cp = cp.asanyarray(a)
        updates_cp = cp.asanyarray(updates)
        if isinstance(indices, (tuple, list)):
            shape = a_cp.shape
            w = shape[1]
            idx_y = cp.asanyarray(indices[0])
            idx_x = cp.asanyarray(indices[1])
            flat_idx = idx_y * w + idx_x
            if a_cp.ndim == 3:
                cp.scatter_add(a_cp.reshape(-1, shape[2]), flat_idx, updates_cp)
            else:
                cp.scatter_add(a_cp.ravel(), flat_idx, updates_cp)
        else:
            cp.scatter_add(a_cp, cp.asanyarray(indices), updates_cp)
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

_IMAGE_EXTS = frozenset({'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.gif', '.webp'})


# ── Native File Dialog ───────────────────────────────────────────────

def _powershell_open_file(title: str, file_type: str = "image") -> str | None:
    if file_type == "video":
        filt = ("Video Files (*.mp4;*.avi;*.mov;*.mkv;*.webm)|"
                "*.mp4;*.avi;*.mov;*.mkv;*.webm|All Files (*.*)|*.*")
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
    screen: str = "main"        # "main" | "image" | "video"
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
    using_accelerator: bool = HAS_CUPY

    MENU_MAIN = [
        ("Rearrange Images", "sort pixels between two images"),
        ("Rearrange Videos", "sort frames between two videos"),
        ("Quit", "exit the application"),
    ]

    MENU_IMAGE = [
        ("Select Source Image",   "choose the image whose pixels will be rearranged"),
        ("Select Target Image",   "choose the image whose layout will be approximated"),
        ("Run Rearrangement",     "execute the sort-based pixel-matching algorithm"),
        ("Save Result Image",     "save the reconstructed image to disk"),
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

    @property
    def menu(self):
        return {"main": self.MENU_MAIN, "image": self.MENU_IMAGE, "video": self.MENU_VIDEO}[self.screen]


# ── Rearrangement Engine ─────────────────────────────────────────────

def compute_sort_keys(img, xp=np):
    h, w = img.shape[:2]
    flat = img.reshape(-1, 3).astype(np.float32)
    lum = 0.299 * flat[:, 2] + 0.587 * flat[:, 1] + 0.114 * flat[:, 0]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV_FULL).reshape(-1, 3).astype(np.float32)
    if xp is not np:
        return xp.array(lum), xp.array(hsv[:, 0]), xp.array(hsv[:, 1])
    return lum, hsv[:, 0], hsv[:, 1]


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
        s_l, s_h, s_s = compute_sort_keys(img_src, xp)
        t_l, t_h, t_s = compute_sort_keys(img_tgt, xp)
        s_order = xp_lexsort((s_s, s_h, s_l), xp)
        t_order = xp_lexsort((t_s, t_h, t_l), xp)

        out_flat = xp.empty_like(xp.array(img_src.reshape(-1, 3)), dtype=xp.uint8)
        out_flat[t_order] = xp.array(img_src.reshape(-1, 3))[s_order]
        out_img = out_flat.reshape(h, w, 3)
        out_img = to_np(out_img)

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

        total = h * w
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

        colors = xp.array(src_s.reshape(-1, 3).astype(np.float32))

        num_frames = 60
        for fi in range(num_frames):
            t = (fi + 1) / num_frames

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


# ── TUI Application ──────────────────────────────────────────────────

class PixelTUI:
    def __init__(self, runtime_config: RuntimeConfig):
        self.runtime_config = runtime_config
        self.state = State(using_accelerator=runtime_config.hardware_acceleration_available)

        self.kb = KeyBindings()
        self._register_bindings()

        self._app: Application | None = None

    # ── Key Bindings ─────────────────────────────────────────────

    def _register_bindings(self):
        kb = self.kb

        @kb.add("up")
        def _(event):
            if not self.state.running:
                n = len(self.state.menu)
                self.state.cursor = (self.state.cursor - 1) % n
                self._invalidate()

        @kb.add("down")
        def _(event):
            if not self.state.running:
                n = len(self.state.menu)
                self.state.cursor = (self.state.cursor + 1) % n
                self._invalidate()

        @kb.add("enter")
        def _(event):
            if not self.state.running:
                self._dispatch(self.state.cursor)

        for key, idx in [("1", 0), ("2", 1), ("3", 2), ("4", 3), ("5", 4), ("6", 5)]:
            @kb.add(key)
            def _(event, idx=idx):
                if not self.state.running:
                    n = len(self.state.menu)
                    if idx < n:
                        self.state.cursor = idx
                        self._dispatch(idx)

        @kb.add("escape")
        @kb.add("q")
        def _(event):
            if not self.state.running:
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
             2: self._quit}[idx]()
        elif s == "image":
            {0: self._select_source,
             1: self._select_target,
             2: self._run,
             3: self._save_result,
             4: self._back_to_main,
             5: self._quit}[idx]()
        elif s == "video":
            {0: self._select_source_video,
             1: self._select_target_video,
             2: self._run_video,
             3: self._save_result_video,
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
        if self.state.result_video_path and os.path.exists(self.state.result_video_path):
            try: os.unlink(self.state.result_video_path)
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

        accel_text = "Yes (CuPy)" if s.using_accelerator else "No (CPU)"
        accel_style = "bold #ffaf5f" if s.using_accelerator else "bold #ff5f5f"

        if s.screen == "main":
            push("bold #00d787", "  \u25a0 Pixel Rearrangement Tool")
            push(accel_style, f"  Hardware acceleration: {accel_text}")
            push("", "\n\n")

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
            push("", "\n")
        else:
            mode_label = "Image Mode" if s.screen == "image" else "Video Mode"
            push("bold #00d787", f"  \u25a0 Pixel Rearrangement Tool")
            push("bold #5f87ff", f"  \u2014  [ {mode_label} ]")
            push(accel_style, f"\n  Hardware acceleration: {accel_text}")
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
                is_save = (s.screen == "image" and i == 3) or (s.screen == "video" and i == 3)
                disabled = is_save and not s.done
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
    if "--version" in sys.argv or "-v" in sys.argv:
        try:
            print(f"pixelification {version('pixelification')}")
        except PackageNotFoundError:
            print("pixelification (local development)")
        return
    runtime_config = load_or_create_runtime_config(HAS_CUPY)
    PixelTUI(runtime_config).run()


# ── Entry Point ──────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
