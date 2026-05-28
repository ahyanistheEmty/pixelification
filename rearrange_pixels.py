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
    out_s = cv2.resize(output_img, (dw, dh))

    title_h = 34
    label_h = 22
    gap = 3
    cw = dw * 3
    ch = title_h + gap + dh + gap
    canvas = np.full((ch, cw, 3), 20, dtype=np.uint8)
    content_y = title_h + gap
    font = cv2.FONT_HERSHEY_SIMPLEX

    # ----- Title bar -----
    cv2.rectangle(canvas, (0, 0), (cw, title_h), (14, 14, 14), -1)
    cv2.rectangle(canvas, (0, title_h - 3), (cw, title_h), (0, 200, 120), -1)
    cv2.putText(canvas, "  >>  Pixel Rearrangement",
                (8, title_h - 10), font, 0.55, (0, 200, 120), 2)
    cv2.putText(canvas, f"{w}x{h}",
                (cw - 140, title_h - 10), font, 0.45, (140, 140, 140), 1)

    # ----- Panel backgrounds & labels -----
    canvas[content_y:content_y + dh, :dw] = src_s
    canvas[content_y:content_y + dh, dw:2 * dw] = tgt_s
    rec_region = canvas[content_y:content_y + dh, 2 * dw:3 * dw]

    for label, xo in [("Source", 0), ("Target", dw), ("Reconstruction", 2 * dw)]:
        cv2.rectangle(canvas, (xo, content_y), (xo + dw, content_y + label_h), (0, 0, 0), -1)
        cv2.putText(canvas, label, (xo + 6, content_y + 16), font, 0.45, (200, 200, 200), 1)

    wn = "Pixel Rearrangement  (ESC/q  anytime  to  quit)"

    def draw_progress(pct, text=""):
        cv2.rectangle(canvas, (cw - 180, 0), (cw, title_h), (14, 14, 14), -1)
        if text:
            cv2.putText(canvas, text, (cw - 172, title_h - 10), font, 0.5, (0, 200, 120), 2)
        else:
            cv2.putText(canvas, f"{pct}%", (cw - 160, title_h - 10), font, 0.5, (0, 200, 120), 2)
        bw = int(80 * pct / 100)
        cv2.rectangle(canvas, (cw - 172, title_h - 20), (cw - 172 + bw, title_h - 17), (0, 200, 120), -1)
        cv2.rectangle(canvas, (cw - 172, title_h - 20), (cw - 92, title_h - 17), (60, 60, 60), 1)

    cv2.imshow(wn, canvas)
    if cv2.waitKey(400) & 0xFF in (27, ord("q")):
        cv2.destroyAllWindows()
        return

    # ----- Tile-sliding animation -----
    tile_size = max(8, min(24, int(np.sqrt(dw * dh / 180))))
    tile_h = dh // tile_size
    tile_w = dw // tile_size

    dest_lookup = np.empty(h * w, dtype=np.int32)
    dest_lookup[src_order] = tgt_order
    dest_map = dest_lookup.reshape(h, w)

    dest_x_full = (dest_map % w).astype(np.float32) * (dw / w)
    dest_y_full = (dest_map // w).astype(np.float32) * (dh / h)

    dest_x_small = cv2.resize(dest_x_full, (dw, dh), interpolation=cv2.INTER_NEAREST)
    dest_y_small = cv2.resize(dest_y_full, (dw, dh), interpolation=cv2.INTER_NEAREST)

    tile_dest_x = np.zeros((tile_h, tile_w), dtype=np.float32)
    tile_dest_y = np.zeros((tile_h, tile_w), dtype=np.float32)
    for ty in range(tile_h):
        y0 = ty * tile_size
        y1 = min(y0 + tile_size, dh)
        for tx in range(tile_w):
            x0 = tx * tile_size
            x1 = min(x0 + tile_size, dw)
            tile_dest_x[ty, tx] = dest_x_small[y0:y1, x0:x1].mean()
            tile_dest_y[ty, tx] = dest_y_small[y0:y1, x0:x1].mean()

    num_frames = 40
    frames = []
    for fi in range(num_frames):
        t_raw = (fi + 1) / num_frames
        ts = t_raw * t_raw * (3 - 2 * t_raw)
        frame = np.full((dh, dw, 3), 24, dtype=np.uint8)

        for ty in range(tile_h):
            y0 = ty * tile_size
            y1 = min(y0 + tile_size, dh)
            for tx in range(tile_w):
                x0 = tx * tile_size
                x1 = min(x0 + tile_size, dw)
                tile = src_s[y0:y1, x0:x1]
                th_act, tw_act = tile.shape[:2]

                cx = int(round(x0 * (1 - ts) + tile_dest_x[ty, tx] * ts))
                cy = int(round(y0 * (1 - ts) + tile_dest_y[ty, tx] * ts))

                if cx < dw and cy < dh:
                    cx1 = min(cx + tw_act, dw)
                    cy1 = min(cy + th_act, dh)
                    if cx1 > cx and cy1 > cy:
                        frame[cy:cy1, cx:cx1] = tile[:(cy1 - cy), :(cx1 - cx)]
        frames.append(frame)

    for fi, frame in enumerate(frames):
        rec_region[:] = frame
        draw_progress(int((fi + 1) / num_frames * 100))
        cv2.imshow(wn, canvas)
        if cv2.waitKey(20) & 0xFF in (27, ord("q")):
            break
    else:
        for di in range(12):
            a = (di + 1) / 12.0
            blended = cv2.addWeighted(frames[-1], 1 - a, out_s, a, 0)
            rec_region[:] = blended
            draw_progress(0, "refine")
            cv2.imshow(wn, canvas)
            if cv2.waitKey(25) & 0xFF in (27, ord("q")):
                break
        else:
            rec_region[:] = out_s

    draw_progress(0, "Done")
    cv2.imshow(wn, canvas)

    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
