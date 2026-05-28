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

    # ----- Real-time row-by-row display -----
    max_display = 900
    scale = min(max_display / (w * 3), max_display / h, 1.0)
    dw, dh = int(w * scale), int(h * scale)

    src_small = cv2.resize(img_src, (dw, dh))
    tgt_small = cv2.resize(img_tgt, (dw, dh))
    out_small = cv2.resize(output_img, (dw, dh))

    canvas = np.full((dh, dw * 3, 3), 32, dtype=np.uint8)

    # Place source and target immediately
    canvas[:, :dw] = src_small
    canvas[:, dw:2 * dw] = tgt_small

    # Labels with dark background strip for readability
    font = cv2.FONT_HERSHEY_SIMPLEX
    label_y = 18
    for label, x_off in [("Source", 0), ("Target", dw), ("Reconstruction", 2 * dw)]:
        cv2.rectangle(canvas, (x_off, 0), (x_off + dw, label_y + 4), (0, 0, 0), -1)
        cv2.putText(canvas, label, (x_off + 5, label_y), font, 0.5, (255, 255, 255), 1)

    cv2.imshow("Pixel Rearrangement (ESC/q to quit)", canvas)

    # Small pause before the animation
    if cv2.waitKey(500) & 0xFF == 27:
        cv2.destroyAllWindows()
        return

    print("Rendering reconstruction row by row...")

    completed = True
    row_delay = max(1, min(10, 500 // dh))

    for y in range(dh):
        canvas[y, 2 * dw:3 * dw] = out_small[y, :]
        cv2.imshow("Pixel Rearrangement (ESC/q to quit)", canvas)

        if cv2.waitKey(row_delay) & 0xFF in (27, ord("q")):
            completed = False
            break

    if completed:
        cv2.rectangle(canvas, (2 * dw, dh - 24), (2 * dw + 140, dh), (0, 0, 0), -1)
        cv2.putText(canvas, "Complete!", (2 * dw + 8, dh - 8), font, 0.55, (0, 220, 0), 1)
        cv2.imshow("Pixel Rearrangement (ESC/q to quit)", canvas)
        print("Complete. Press any key to exit.")
    else:
        print("Interrupted. Press any key to exit.")

    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
