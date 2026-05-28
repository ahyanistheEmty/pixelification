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
    cv2.imshow(wn, canvas)
    cv2.waitKey(300)

    # ----- Per-pixel swarm animation -----
    total = h * w
    rng = np.random.default_rng()

    src_flat = img_src.reshape(-1, 3)

    # For each target position: which source pixel colour ends up there
    rearranged = np.empty((total, 3), dtype=np.uint8)
    rearranged[tgt_order] = src_flat[src_order]

    # Each output position transitions independently at a random time
    transition_times = rng.random(total)

    num_frames = 60
    for fi in range(num_frames):
        frac = (fi + 1) / num_frames
        mask = transition_times < frac

        frame = np.where(mask[:, None], rearranged, src_flat)
        rec_region[:] = cv2.resize(frame.reshape(h, w, 3), (dw, dh))
        cv2.imshow(wn, canvas)
        if cv2.waitKey(25) & 0xFF in (27, ord("q")):
            break
    else:
        rec_region[:] = cv2.resize(rearranged.reshape(h, w, 3), (dw, dh))
        cv2.imshow(wn, canvas)

    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
