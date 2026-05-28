"""
Pixel Rearrangement Algorithm
Reorders pixels of the source image to best approximate the target image.
Uses optimal transport matching via color sorting (O(n log n)).

Usage:
    python rearrange_pixels.py <source_image> <target_image>

Only rearranges existing pixels — no new colors are generated.
"""

import cv2
import numpy as np
import sys
from pathlib import Path


def compute_sort_keys(img):
    """Compute (luminance, hue, saturation) for every pixel in the image."""
    h, w = img.shape[:2]
    flat = img.reshape(-1, 3).astype(np.float32)

    # Perceptual luminance from BGR
    lum = 0.299 * flat[:, 2] + 0.587 * flat[:, 1] + 0.114 * flat[:, 0]

    # Hue and saturation via full-range HSV
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV_FULL).reshape(-1, 3).astype(np.float32)
    hue = hsv[:, 0]
    sat = hsv[:, 1]

    return lum, hue, sat


def main():
    if len(sys.argv) != 3:
        print(f"Usage: python {Path(__file__).name} <source_image> <target_image>")
        sys.exit(1)

    src_path, tgt_path = sys.argv[1], sys.argv[2]

    if not Path(src_path).is_file():
        print(f"Error: source file '{src_path}' not found")
        sys.exit(1)
    if not Path(tgt_path).is_file():
        print(f"Error: target file '{tgt_path}' not found")
        sys.exit(1)

    img_src = cv2.imread(src_path, cv2.IMREAD_COLOR)
    img_tgt = cv2.imread(tgt_path, cv2.IMREAD_COLOR)

    if img_src is None:
        print(f"Error: could not decode source image '{src_path}'")
        sys.exit(1)
    if img_tgt is None:
        print(f"Error: could not decode target image '{tgt_path}'")
        sys.exit(1)

    h, w = img_src.shape[:2]
    print(f"Source: {w}x{h}")

    img_tgt = cv2.resize(img_tgt, (w, h))
    print(f"Target: resized to {w}x{h}")

    # ----- Optimal pixel mapping -----
    print("Computing optimal pixel rearrangement (sorting by color)...")

    src_lum, src_hue, src_sat = compute_sort_keys(img_src)
    tgt_lum, tgt_hue, tgt_sat = compute_sort_keys(img_tgt)

    # Sort by luminance (primary), then hue, then saturation
    # lexsort applies keys in reverse order of the tuple
    src_order = np.lexsort((src_sat, src_hue, src_lum))
    tgt_order = np.lexsort((tgt_sat, tgt_hue, tgt_lum))

    # Map: source pixel with rank i goes to target position with rank i
    src_flat = img_src.reshape(-1, 3)
    output_flat = np.empty_like(src_flat, dtype=np.uint8)
    output_flat[tgt_order] = src_flat[src_order]
    output_img = output_flat.reshape(h, w, 3)

    # ----- Display setup -----
    max_d = 900
    sc = min(max_d / (w * 3), max_d / h, 1.0)
    dw, dh = int(w * sc), int(h * sc)

    src_s = cv2.resize(img_src, (dw, dh))
    tgt_s = cv2.resize(img_tgt, (dw, dh))

    label_h = 22
    canvas = np.full((dh + label_h, dw * 3, 3), 32, dtype=np.uint8)
    canvas[label_h:, :dw] = src_s
    canvas[label_h:, dw:2 * dw] = tgt_s
    rec_region = canvas[label_h:, 2 * dw:3 * dw]

    font = cv2.FONT_HERSHEY_SIMPLEX
    for label, xo in [("Source", 0), ("Target", dw), ("Reconstruction", 2 * dw)]:
        cv2.rectangle(canvas, (xo, 0), (xo + dw, label_h), (0, 0, 0), -1)
        cv2.putText(canvas, label, (xo + 6, 16), font, 0.45, (200, 200, 200), 1)

    wn = "Pixel Rearrangement  (ESC/q  anytime  to  quit)"
    cv2.namedWindow(wn, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(wn, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cv2.imshow(wn, canvas)
    cv2.waitKey(300)

    # ----- True pixel-sliding animation -----
    # Forward map: for each source pixel, which target position it goes to
    total = h * w
    forward = np.empty(total, dtype=np.int32)
    forward[src_order] = tgt_order

    # For each display pixel (dx, dy), the source pixel index it corresponds to
    s_idx_x = (np.arange(dw, dtype=np.float32) * w / dw).clip(0, w - 1).round().astype(np.int32)
    s_idx_y = (np.arange(dh, dtype=np.float32) * h / dh).clip(0, h - 1).round().astype(np.int32)
    gx, gy = np.meshgrid(s_idx_x, s_idx_y)
    src_lin = gy * w + gx

    # Where does that source pixel go in the target?
    tgt_lin = forward[src_lin]
    tgt_dx = (tgt_lin % w).astype(np.float32) * sc
    tgt_dy = (tgt_lin // w).astype(np.float32) * sc

    # Starting position (display coords) of each source pixel
    src_dx = gx.astype(np.float32) * sc
    src_dy = gy.astype(np.float32) * sc

    # Colors of the source pixels
    colors = src_s.reshape(-1, 3).astype(np.float32)

    num_frames = 60
    for fi in range(num_frames):
        t = (fi + 1) / num_frames

        # Each pixel's current position: linearly interpolated
        curr_x = np.clip((1 - t) * src_dx.ravel() + t * tgt_dx.ravel(), 0, dw - 1)
        curr_y = np.clip((1 - t) * src_dy.ravel() + t * tgt_dy.ravel(), 0, dh - 1)
        rx = np.round(curr_x).astype(np.int32)
        ry = np.round(curr_y).astype(np.int32)

        # Scatter: add each pixel's colour to its current position
        accum = np.zeros((dh, dw, 3), dtype=np.float32)
        cnt = np.zeros((dh, dw), dtype=np.float32)
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
            src_flat[src_order][tgt_order.argsort()].reshape(h, w, 3),
            (dw, dh),
        )
        cv2.imshow(wn, canvas)

    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
