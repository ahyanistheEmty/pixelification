"""
Pixel Rearrangement Tool — Keyboard-Navigated Terminal UI

Select images via a native file dialog, then watch the pixel rearrangement
animate row-by-row in an OpenCV window. No new pixels are created; only
existing pixels from the source image are reordered to match the target.

Usage:
    python rearrange_pixels_tui.py
"""

import asyncio
import cv2
import numpy as np
import os
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, Window, FormattedTextControl
from prompt_toolkit.styles import Style


# ── Styling ──────────────────────────────────────────────────────────

STYLE = Style([
    ("title",         "bold #00d787"),
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


# ── Native File Dialog ───────────────────────────────────────────────

def _powershell_open_file(title: str) -> str | None:
    """Open the native Windows file dialog via a temp PowerShell script.
    Avoids command-line quoting issues with -Command."""
    script = """Add-Type -AssemblyName System.Windows.Forms
$f = New-Object System.Windows.Forms.OpenFileDialog
$f.Filter = "Image Files (*.png;*.jpg;*.jpeg;*.bmp;*.tiff;*.gif;*.webp)|*.png;*.jpg;*.jpeg;*.bmp;*.tiff;*.gif;*.webp|All Files (*.*)|*.*"
$f.FilterIndex = 1
$f.RestoreDirectory = $true
if ($f.ShowDialog() -eq "OK") { $f.FileName }
"""
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


def _tkinter_open_file(title: str) -> str | None:
    """Fallback: open file dialog via tkinter."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askopenfilename(
            parent=root, title=title,
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.bmp *.tiff *.gif *.webp"),
                ("All files",   "*.*"),
            ],
        )
        root.destroy()
        return path if path else None
    except Exception:
        return None


def select_file(title: str = "Select Image") -> str | None:
    """Open a native file-selection dialog.  Uses PowerShell on Windows,
    tkinter elsewhere.  Returns the selected path or *None* if cancelled."""
    if os.name == "nt":
        path = _powershell_open_file(title)
        if path:
            return path
    path = _tkinter_open_file(title)
    return path if path else None


# ── Application State ────────────────────────────────────────────────

@dataclass
class State:
    source: str = ""
    target: str = ""
    status: str = "Ready"
    status_style: str = "status"
    info: str = ""
    cursor: int = 0               # 0-3  →  source / target / run / quit
    running: bool = False
    done: bool = False

    MENU = [
        ("Select Source Image",   "choose the image whose pixels will be rearranged"),
        ("Select Target Image",   "choose the image whose layout will be approximated"),
        ("Run Rearrangement",     "execute the sort-based pixel-matching algorithm"),
        ("Quit",                  "exit the application"),
    ]


# ── Rearrangement Engine ─────────────────────────────────────────────

def compute_sort_keys(img):
    h, w = img.shape[:2]
    flat = img.reshape(-1, 3).astype(np.float32)
    lum = 0.299 * flat[:, 2] + 0.587 * flat[:, 1] + 0.114 * flat[:, 0]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV_FULL).reshape(-1, 3).astype(np.float32)
    return lum, hsv[:, 0], hsv[:, 1]


def rearrange(source_path: str, target_path: str, state: State) -> None:
    """Run the pixel-rearrangement algorithm and show the OpenCV window.
    Called from a background thread."""
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

        # ── optimal transport via colour sorting ──
        s_l, s_h, s_s = compute_sort_keys(img_src)
        t_l, t_h, t_s = compute_sort_keys(img_tgt)
        s_order = np.lexsort((s_s, s_h, s_l))
        t_order = np.lexsort((t_s, t_h, t_l))

        out = np.empty_like(img_src.reshape(-1, 3), dtype=np.uint8)
        out[t_order] = img_src.reshape(-1, 3)[s_order]
        out_img = out.reshape(h, w, 3)

        # ── Display setup (full-screen aware) ──
        try:
            import ctypes
            sw = ctypes.windll.user32.GetSystemMetrics(0)
            sh = ctypes.windll.user32.GetSystemMetrics(1)
        except Exception:
            sw, sh = 1920, 1080
        pw = sw * 85 // 100 // 3                     # panel width
        ph = sh * 85 // 100                          # panel height
        sc = min(pw / w, ph / h)                   # as large as possible, no crop
        iw, ih = max(int(w * sc), 1), max(int(h * sc), 1)

        src_s = cv2.resize(img_src, (iw, ih), interpolation=cv2.INTER_LANCZOS4)
        tgt_s = cv2.resize(img_tgt, (iw, ih), interpolation=cv2.INTER_LANCZOS4)

        # Layout: 3 panels, content centered (void space fills the rest)
        label_h = 22
        canvas = np.full((ph + label_h, pw * 3, 3), 32, dtype=np.uint8)

        src_x = (pw - iw) // 2
        src_y = label_h + (ph - ih) // 2
        canvas[src_y:src_y+ih, src_x:src_x+iw] = src_s

        tgt_x = pw + (pw - iw) // 2
        tgt_y = src_y
        canvas[tgt_y:tgt_y+ih, tgt_x:tgt_x+iw] = tgt_s

        rec_x = pw * 2 + (pw - iw) // 2
        rec_y = src_y
        rec_region = canvas[rec_y:rec_y+ih, rec_x:rec_x+iw]

        font = cv2.FONT_HERSHEY_SIMPLEX
        for label, xo in [("Source", 0), ("Target", pw), ("Reconstruction", 2 * pw)]:
            cv2.rectangle(canvas, (xo, 0), (xo + pw, label_h), (0, 0, 0), -1)
            cv2.putText(canvas, label, (xo + 6, 16), font, 0.45, (200, 200, 200), 1)

        wn = "Pixel Rearrangement  (ESC/q  anytime  to  quit)"
        cv2.namedWindow(wn, cv2.WINDOW_NORMAL)
        cv2.setWindowProperty(wn, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        cv2.imshow(wn, canvas)
        cv2.waitKey(300)

        # ── True pixel-sliding animation ──
        total = h * w
        forward = np.empty(total, dtype=np.int32)
        forward[s_order] = t_order

        scx = iw / w
        scy = ih / h

        s_idx_x = (np.arange(iw, dtype=np.float32) * w / iw).clip(0, w - 1).round().astype(np.int32)
        s_idx_y = (np.arange(ih, dtype=np.float32) * h / ih).clip(0, h - 1).round().astype(np.int32)
        gx, gy = np.meshgrid(s_idx_x, s_idx_y)
        src_lin = gy * w + gx

        tgt_lin = forward[src_lin]
        tgt_dx = (tgt_lin % w).astype(np.float32) * scx
        tgt_dy = (tgt_lin // w).astype(np.float32) * scy

        src_dx = gx.astype(np.float32) * scx
        src_dy = gy.astype(np.float32) * scy

        colors = src_s.reshape(-1, 3).astype(np.float32)

        num_frames = 60
        for fi in range(num_frames):
            t = (fi + 1) / num_frames

            curr_x = np.clip((1 - t) * src_dx.ravel() + t * tgt_dx.ravel(), 0, iw - 1)
            curr_y = np.clip((1 - t) * src_dy.ravel() + t * tgt_dy.ravel(), 0, ih - 1)
            rx = np.round(curr_x).astype(np.int32)
            ry = np.round(curr_y).astype(np.int32)

            accum = np.zeros((ih, iw, 3), dtype=np.float32)
            cnt = np.zeros((ih, iw), dtype=np.float32)
            np.add.at(accum, (ry, rx), colors)
            np.add.at(cnt, (ry, rx), 1.0)
            mask = cnt > 0
            accum[mask] /= cnt[mask, None]

            rec_region[:] = accum.astype(np.uint8)
            cv2.imshow(wn, canvas)
            if cv2.waitKey(25) & 0xFF in (27, ord("q")):
                break
        else:
            rec_region[:] = cv2.resize(
                img_src.reshape(-1, 3)[s_order][t_order.argsort()].reshape(h, w, 3),
                (iw, ih),
            )
            cv2.imshow(wn, canvas)

        cv2.waitKey(0)
        cv2.destroyAllWindows()

        state.status = "Rearrangement finished!"
        state.status_style = "status"

    except Exception as e:
        state.status = f"Error: {e}"
        state.status_style = "status-error"
    finally:
        state.running = False
        state.done = True


# ── TUI Application ──────────────────────────────────────────────────

class PixelTUI:
    def __init__(self):
        self.state = State()

        self.kb = KeyBindings()
        self._register_bindings()

        self._app: Application | None = None

    # ── Key Bindings ─────────────────────────────────────────────

    def _register_bindings(self):
        kb = self.kb

        @kb.add("up")
        def _(event):
            if not self.state.running:
                self.state.cursor = (self.state.cursor - 1) % 4
                self._invalidate()

        @kb.add("down")
        def _(event):
            if not self.state.running:
                self.state.cursor = (self.state.cursor + 1) % 4
                self._invalidate()

        @kb.add("enter")
        def _(event):
            if not self.state.running:
                self._dispatch(self.state.cursor)

        for key, idx in [("1", 0), ("2", 1), ("3", 2), ("4", 3)]:
            @kb.add(key)
            def _(event, idx=idx):
                if not self.state.running:
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
        {0: self._select_source,
         1: self._select_target,
         2: self._run,
         3: self._quit}[idx]()

    # ── Actions ──────────────────────────────────────────────────

    def _select_source(self):
        path = select_file("Select Source Image (pixels to rearrange)")
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
        path = select_file("Select Target Image (layout to approximate)")
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
        self.state.status = "Rearrangement running in OpenCV window…"
        self.state.status_style = "status-warn"
        self._invalidate()

        t = threading.Thread(
            target=rearrange,
            args=(self.state.source, self.state.target, self.state),
            daemon=True,
        )
        t.start()

        # Poll thread completion in the background
        async def waiter():
            while t.is_alive():
                await asyncio.sleep(0.5)
                self._invalidate()
            self._invalidate()

        if self._app:
            asyncio.create_task(waiter())

    def _refresh_info(self):
        parts = []
        for path in (self.state.source, self.state.target):
            if not path:
                continue
            try:
                img = cv2.imread(path, cv2.IMREAD_COLOR)
                if img is not None:
                    h, w = img.shape[:2]
                    kb = Path(path).stat().st_size / 1024
                    parts.append(f"{Path(path).name}  {w}×{h}  ({kb:.0f} KB)")
            except Exception:
                parts.append(Path(path).name)
        if self.state.source and self.state.target:
            parts.append("Ready!")
        self.state.info = "  |  ".join(parts) if parts else ""

    def _quit(self):
        cv2.destroyAllWindows()
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

        # Header
        push("bold #00d787", "  ■ Pixel Rearrangement Tool")
        push("", "\n")
        push("#3a3a3a", "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        push("", "\n")

        # Source / Target paths
        push("bold #5f87ff", "\n  Source:  ")
        push("#87afff" if s.source else "#585858 italic",
             s.source if s.source else "— not selected —")

        push("bold #5f87ff", "\n  Target:  ")
        push("#87afff" if s.target else "#585858 italic",
             s.target if s.target else "— not selected —")

        # Info line
        if s.info:
            push("", "\n  ")
            push("#878787 italic", s.info)

        # Menu divider
        push("", "\n\n")
        push("#3a3a3a", "  ───────────────────────────────────────────────────────────")
        push("", "\n")

        # Menu items
        for i, (label, desc) in enumerate(State.MENU):
            cursor = "●" if i == s.cursor else "○"
            sel = i == s.cursor
            push("bold #000000 bg:#00d787" if sel else "bold #ffffff",
                 f"  {cursor} {label}  ")
            push("", "  ")
            push("#6c6c6c", f"{desc}\n")

        # Status divider
        push("", "\n")
        push("#3a3a3a", "  ───────────────────────────────────────────────────────────")
        push("", "\n  ")

        # Status line
        c = {"status": "#5faf5f", "status-error": "#ff5f5f",
             "status-warn": "#ffaf5f", "status-info": "#878787 italic"}
        push(c.get(s.status_style, "#878787 italic"), s.status)
        push("", "\n")

        # Help
        push("#585858 italic", "↑↓  navigate  •  Enter  select  •  1-4  shortcut  •  q  quit")
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


# ── Entry Point ──────────────────────────────────────────────────────

if __name__ == "__main__":
    PixelTUI().run()
