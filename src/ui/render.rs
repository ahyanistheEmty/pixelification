use windows::Win32::Foundation::{HWND, RECT, COLORREF};
use windows::Win32::Graphics::Gdi::{HDC, HBITMAP, HGDIOBJ, NULL_BRUSH, PS_SOLID, TRANSPARENT};
use crate::win32;

pub struct BackBuffer {
    pub hdc: HDC,
    pub bitmap: HBITMAP,
    pub old_bitmap: HGDIOBJ,
    width: i32,
    height: i32,
}

impl BackBuffer {
    pub fn new(hdc: HDC, width: i32, height: i32) -> Option<Self> {
        let mem_dc = win32::create_compatible_dc(Some(hdc))?;
        let bitmap = win32::create_compatible_bitmap(hdc, width, height)?;
        let old_bitmap = win32::select_object(mem_dc, bitmap.into());
        Some(Self { hdc: mem_dc, bitmap, old_bitmap, width, height })
    }

    pub fn resize(&mut self, hdc: HDC, width: i32, height: i32) {
        if width == self.width && height == self.height { return; }
        win32::select_object(self.hdc, self.old_bitmap);
        win32::delete_object(self.bitmap.into());
        win32::delete_dc(self.hdc);
        if let Some(mem_dc) = win32::create_compatible_dc(Some(hdc)) {
            if let Some(bitmap) = win32::create_compatible_bitmap(hdc, width, height) {
                let old = win32::select_object(mem_dc, bitmap.into());
                self.hdc = mem_dc; self.bitmap = bitmap; self.old_bitmap = old;
                self.width = width; self.height = height;
            }
        }
    }

    pub fn present(&self, dest_hdc: HDC, x: i32, y: i32, w: i32, h: i32) {
        win32::bitblt(dest_hdc, x, y, w, h, self.hdc, x, y);
    }

    pub fn clear(&self, color: COLORREF) {
        let rect = RECT { left: 0, top: 0, right: self.width, bottom: self.height };
        let brush = win32::create_solid_brush(color);
        win32::fill_rect(self.hdc, &rect, brush);
        win32::delete_object(brush.into());
    }
}

impl Drop for BackBuffer {
    fn drop(&mut self) {
        win32::select_object(self.hdc, self.old_bitmap);
        win32::delete_object(self.bitmap.into());
        win32::delete_dc(self.hdc);
    }
}

pub struct Renderer {
    pub backbuffer: Option<BackBuffer>,
    pub width: i32,
    pub height: i32,
}

impl Renderer {
    pub fn new() -> Self { Self { backbuffer: None, width: 0, height: 0 } }

    pub fn ensure_backbuffer(&mut self, hdc: HDC, width: i32, height: i32) {
        if let Some(ref mut bb) = self.backbuffer { bb.resize(hdc, width, height); }
        else { self.backbuffer = BackBuffer::new(hdc, width, height); }
        self.width = width; self.height = height;
    }

    pub fn begin_frame(&mut self, dest_hdc: HDC, width: i32, height: i32) -> Option<&BackBuffer> {
        self.ensure_backbuffer(dest_hdc, width, height);
        self.backbuffer.as_ref()
    }

    pub fn end_frame(&self, dest_hdc: HDC) {
        if let Some(ref bb) = self.backbuffer { bb.present(dest_hdc, 0, 0, self.width, self.height); }
    }

    pub fn refresh(&self, hwnd: HWND) { win32::invalidate_rect(hwnd, None); }

    pub fn refresh_region(&self, hwnd: HWND, rect: &RECT) { win32::invalidate_rect(hwnd, Some(rect)); }
}

pub fn fill_rect(hdc: HDC, rect: &RECT, brush: isize) {
    win32::fill_rect(hdc, rect, win32::hbrush_from_isize(brush));
}

pub fn draw_text(hdc: HDC, text: &str, x: i32, y: i32, color: COLORREF, font: isize) {
    let wide = win32::to_wide(text);
    let old_font = win32::select_object(hdc, win32::hfont_from_isize(font).into());
    win32::set_text_color(hdc, color);
    win32::set_bk_mode(hdc, TRANSPARENT);
    win32::text_out(hdc, x, y, &wide);
    win32::select_object(hdc, old_font);
}

pub fn draw_text_ellipsis(hdc: HDC, text: &str, x: i32, y: i32, max_width: i32, color: COLORREF, font: isize) {
    let wide = win32::to_wide(text);
    let old_font = win32::select_object(hdc, win32::hfont_from_isize(font).into());
    win32::set_text_color(hdc, color);
    win32::set_bk_mode(hdc, TRANSPARENT);
    let (tw, _) = win32::get_text_extent(hdc, &wide);
    if tw <= max_width { win32::text_out(hdc, x, y, &wide); }
    else {
        let mut display = String::new();
        for c in text.chars() {
            let mut trial = display.clone(); trial.push(c); trial.push_str("...");
            let tw2 = win32::to_wide(&trial);
            let (tw, _) = win32::get_text_extent(hdc, &tw2);
            if tw > max_width { break; }
            display.push(c);
        }
        display.push_str("...");
        let final_wide = win32::to_wide(&display);
        win32::text_out(hdc, x, y, &final_wide);
    }
    win32::select_object(hdc, old_font);
}

pub fn get_text_width(hdc: HDC, text: &str, font: isize) -> i32 {
    let wide = win32::to_wide(text);
    let old_font = win32::select_object(hdc, win32::hfont_from_isize(font).into());
    let (w, _) = win32::get_text_extent(hdc, &wide);
    win32::select_object(hdc, old_font);
    w
}

pub fn draw_rounded_rect(hdc: HDC, rect: &RECT, brush: isize, corner: i32) {
    let old_brush = win32::select_object(hdc, win32::hbrush_from_isize(brush).into());
    let old_pen = win32::select_object(hdc, win32::get_stock_object(NULL_BRUSH));
    win32::round_rect(hdc, rect.left, rect.top, rect.right, rect.bottom, corner, corner);
    win32::select_object(hdc, old_brush);
    win32::select_object(hdc, old_pen);
}

pub fn draw_line(hdc: HDC, x1: i32, y1: i32, x2: i32, y2: i32, color: COLORREF) {
    let pen = win32::create_pen(PS_SOLID, 1, color);
    let old_pen = win32::select_object(hdc, pen.into());
    win32::move_to(hdc, x1, y1);
    win32::line_to(hdc, x2, y2);
    win32::select_object(hdc, old_pen);
    win32::delete_object(pen.into());
}
