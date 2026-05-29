use std::collections::HashMap;
use crate::win32;

pub struct BitmapRegistry {
    bitmaps: HashMap<u64, isize>,
    next_id: u64,
}

impl BitmapRegistry {
    pub fn new() -> Self {
        Self { bitmaps: HashMap::new(), next_id: 1 }
    }

    pub fn register(&mut self, bitmap: windows::Win32::Graphics::Gdi::HBITMAP) -> u64 {
        let id = self.next_id; self.next_id += 1;
        self.bitmaps.insert(id, win32::handle_to_isize(bitmap.0));
        id
    }

    pub fn get(&self, id: u64) -> Option<windows::Win32::Graphics::Gdi::HBITMAP> {
        self.bitmaps.get(&id).map(|&h| windows::Win32::Graphics::Gdi::HBITMAP(h as *mut _))
    }

    pub fn remove(&mut self, id: u64) {
        if let Some(&h) = self.bitmaps.get(&id) {
            let hbmp = windows::Win32::Graphics::Gdi::HBITMAP(h as *mut _);
            win32::delete_object(hbmp.into());
            self.bitmaps.remove(&id);
        }
    }
}
