use std::collections::HashMap;
use crate::win32;

#[derive(Hash, Eq, PartialEq, Clone, Copy, Debug)]
pub struct FontKey {
    pub size: i32,
    pub bold: bool,
    pub italic: bool,
}

pub struct FontRegistry {
    fonts: HashMap<FontKey, isize>,
    dpi: u32,
}

impl FontRegistry {
    pub fn new(dpi: u32) -> Self {
        Self { fonts: HashMap::new(), dpi }
    }

    pub fn set_dpi(&mut self, dpi: u32) {
        self.dpi = dpi;
        for (_, h) in self.fonts.drain() {
            win32::delete_object(win32::hfont_from_isize(h).into());
        }
    }

    pub fn get(&mut self, key: FontKey) -> isize {
        if let Some(&h) = self.fonts.get(&key) {
            return h;
        }
        let h = self.create(key);
        self.fonts.insert(key, h);
        h
    }

    fn create(&self, key: FontKey) -> isize {
        let height = -MulDiv(key.size, self.dpi as i32, 72);
        let weight = if key.bold { 700 } else { 400 };
        let name = win32::to_wide("Segoe UI Variable");
        win32::create_font(height, weight, key.italic, &name)
            .map(|f| win32::handle_to_isize(f.0 as *mut _))
            .unwrap_or(0)
    }
}

fn MulDiv(a: i32, b: i32, c: i32) -> i32 {
    if c == 0 { 0 } else { (a * b) / c }
}
