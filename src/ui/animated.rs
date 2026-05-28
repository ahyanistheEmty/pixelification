use windows::Win32::Foundation::{RECT, COLORREF};
use windows::Win32::Graphics::Gdi::HDC;
use crate::win32;

pub struct AnimatedBackground {
    time: f64,
    phase: f64,
    pub timer_id: usize,
}

impl AnimatedBackground {
    pub fn new() -> Self {
        Self { time: 0.0, phase: 0.0, timer_id: 0 }
    }

    pub fn tick(&mut self) {
        self.time += 0.016;
        self.phase = (self.phase + 0.005) % 6.2832;
    }

    pub fn render(&self, hdc: HDC, rect: &RECT, is_dark: bool) {
        let w = rect.right - rect.left;
        let h = rect.bottom - rect.top;
        if w <= 0 || h <= 0 { return; }

        let (r1, g1, b1) = if is_dark { (18u8, 18u8, 22u8) } else { (245u8, 245u8, 248u8) };
        let (r2, g2, b2) = if is_dark { (22u8, 20u8, 28u8) } else { (240u8, 238u8, 245u8) };

        let bg_color = COLORREF(r1 as u32 | (g1 as u32) << 8 | (b1 as u32) << 16);
        let brush = win32::create_solid_brush(bg_color);
        win32::fill_rect(hdc, rect, brush);
        win32::delete_object(brush.into());

        let cells_x = w / 4;
        let cells_y = h / 4;

        for cy in 0..cells_y {
            for cx in 0..cells_x {
                let nx = cx as f64 / cells_x as f64 - 0.5;
                let ny = cy as f64 / cells_y as f64 - 0.5;
                let dist = (nx * nx + ny * ny).sqrt();
                let wave = ((dist * 3.0 - self.phase).sin() + 1.0) * 0.5;
                let blend = wave * 0.08;

                let cr = (r1 as f64 + (r2 as f64 - r1 as f64) * blend) as u8;
                let cg = (g1 as f64 + (g2 as f64 - g1 as f64) * blend) as u8;
                let cb = (b1 as f64 + (b2 as f64 - b1 as f64) * blend) as u8;

                let pixel_color = COLORREF(cr as u32 | (cg as u32) << 8 | (cb as u32) << 16);
                win32::set_pixel(hdc, cx * 4, cy * 4, pixel_color);
            }
        }
    }
}
