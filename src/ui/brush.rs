use std::collections::HashMap;
use windows::Win32::Foundation::COLORREF;
use crate::win32;

pub struct BrushRegistry {
    brushes: HashMap<u32, isize>,
}

impl BrushRegistry {
    pub fn new() -> Self {
        Self { brushes: HashMap::new() }
    }

    pub fn get(&mut self, color: COLORREF) -> isize {
        let key = color.0;
        if let Some(&h) = self.brushes.get(&key) {
            return h;
        }
        let brush = win32::create_solid_brush(color);
        let h = win32::handle_to_isize(brush.0);
        self.brushes.insert(key, h);
        h
    }
}
