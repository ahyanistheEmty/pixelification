use std::ffi::c_void;
use windows::Win32::Foundation::{HWND, HINSTANCE, RECT, LPARAM, WPARAM, LRESULT, COLORREF};
use windows::Win32::Graphics::Gdi::{
    HDC, HBITMAP, HBRUSH, HFONT, HPEN, HGDIOBJ,
    BACKGROUND_MODE, PEN_STYLE, GET_STOCK_OBJECT_FLAGS,
};

// --- Handle helpers ---
#[inline]
pub fn hfont_from_isize(v: isize) -> HFONT { HFONT(v as *mut c_void) }

#[inline]
pub fn hbrush_from_isize(v: isize) -> HBRUSH { HBRUSH(v as *mut c_void) }

#[inline]
pub fn handle_to_isize(h: *mut c_void) -> isize { h as isize }

// --- Module & Window ---
pub fn get_module_handle() -> HINSTANCE {
    unsafe { windows::Win32::System::LibraryLoader::GetModuleHandleA(None).unwrap_or_default().into() }
}

pub fn register_class(wc: &windows::Win32::UI::WindowsAndMessaging::WNDCLASSW) {
    unsafe { windows::Win32::UI::WindowsAndMessaging::RegisterClassW(wc); }
}

pub fn create_window(class_name: &[u16], title: &[u16], instance: HINSTANCE) -> Option<HWND> {
    unsafe {
        windows::Win32::UI::WindowsAndMessaging::CreateWindowExW(
            windows::Win32::UI::WindowsAndMessaging::WS_EX_APPWINDOW,
            windows::core::PCWSTR(class_name.as_ptr()),
            windows::core::PCWSTR(title.as_ptr()),
            windows::Win32::UI::WindowsAndMessaging::WS_OVERLAPPEDWINDOW
                | windows::Win32::UI::WindowsAndMessaging::WS_CLIPCHILDREN,
            windows::Win32::UI::WindowsAndMessaging::CW_USEDEFAULT,
            windows::Win32::UI::WindowsAndMessaging::CW_USEDEFAULT,
            1200, 800, None, None, Some(instance), None,
        ).ok()
    }
}

pub fn show_window(hwnd: HWND) {
    unsafe { let _ = windows::Win32::UI::WindowsAndMessaging::ShowWindow(hwnd, windows::Win32::UI::WindowsAndMessaging::SW_SHOW); }
}

pub fn destroy_window(hwnd: HWND) {
    unsafe { let _ = windows::Win32::UI::WindowsAndMessaging::DestroyWindow(hwnd); }
}

pub fn def_window_proc(hwnd: HWND, msg: u32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    unsafe { windows::Win32::UI::WindowsAndMessaging::DefWindowProcW(hwnd, msg, wparam, lparam) }
}

pub fn get_client_rect(hwnd: HWND) -> RECT {
    let mut rect = RECT::default();
    unsafe { let _ = windows::Win32::UI::WindowsAndMessaging::GetClientRect(hwnd, &mut rect); }
    rect
}

pub fn set_window_pos(hwnd: HWND, left: i32, top: i32, width: i32, height: i32) {
    unsafe {
        let _ = windows::Win32::UI::WindowsAndMessaging::SetWindowPos(
            hwnd, Default::default(), left, top, width, height,
            windows::Win32::UI::WindowsAndMessaging::SWP_NOZORDER,
        );
    }
}

pub fn set_timer(hwnd: HWND, id: usize, ms: u32) {
    unsafe { windows::Win32::UI::WindowsAndMessaging::SetTimer(Some(hwnd), id, ms, None); }
}

pub fn set_userdata(hwnd: HWND, data: isize) {
    unsafe { windows::Win32::UI::WindowsAndMessaging::SetWindowLongPtrW(hwnd, windows::Win32::UI::WindowsAndMessaging::GWLP_USERDATA, data); }
}

pub fn get_userdata(hwnd: HWND) -> isize {
    unsafe { windows::Win32::UI::WindowsAndMessaging::GetWindowLongPtrW(hwnd, windows::Win32::UI::WindowsAndMessaging::GWLP_USERDATA) }
}

pub fn load_cursor_default() -> windows::Win32::UI::WindowsAndMessaging::HCURSOR {
    unsafe { windows::Win32::UI::WindowsAndMessaging::LoadCursorW(None, windows::Win32::UI::WindowsAndMessaging::IDC_ARROW).unwrap_or_default() }
}

pub fn get_message(msg: &mut windows::Win32::UI::WindowsAndMessaging::MSG, hwnd: Option<HWND>, min: u32, max: u32) -> bool {
    unsafe { windows::Win32::UI::WindowsAndMessaging::GetMessageW(msg, hwnd, min, max).as_bool() }
}

pub fn translate_message(msg: &windows::Win32::UI::WindowsAndMessaging::MSG) {
    unsafe { let _ = windows::Win32::UI::WindowsAndMessaging::TranslateMessage(msg); }
}

pub fn dispatch_message(msg: &windows::Win32::UI::WindowsAndMessaging::MSG) -> LRESULT {
    unsafe { windows::Win32::UI::WindowsAndMessaging::DispatchMessageW(msg) }
}

// --- Painting ---
pub fn begin_paint(hwnd: HWND, ps: &mut windows::Win32::Graphics::Gdi::PAINTSTRUCT) -> HDC {
    unsafe { windows::Win32::Graphics::Gdi::BeginPaint(hwnd, ps) }
}

pub fn end_paint(hwnd: HWND, ps: &windows::Win32::Graphics::Gdi::PAINTSTRUCT) {
    unsafe { let _ = windows::Win32::Graphics::Gdi::EndPaint(hwnd, ps); }
}

// --- GDI Helpers ---
pub fn set_text_color(hdc: HDC, color: COLORREF) {
    unsafe { windows::Win32::Graphics::Gdi::SetTextColor(hdc, color); }
}

pub fn set_bk_mode(hdc: HDC, mode: BACKGROUND_MODE) {
    unsafe { windows::Win32::Graphics::Gdi::SetBkMode(hdc, mode); }
}

pub fn text_out(hdc: HDC, x: i32, y: i32, text: &[u16]) {
    unsafe { let _ = windows::Win32::Graphics::Gdi::TextOutW(hdc, x, y, text); }
}

pub fn get_text_extent(hdc: HDC, text: &[u16]) -> (i32, i32) {
    let mut sz = unsafe { std::mem::zeroed() };
    unsafe { let _ = windows::Win32::Graphics::Gdi::GetTextExtentPoint32W(hdc, text, &mut sz); }
    (sz.cx, sz.cy)
}

pub fn select_object(hdc: HDC, obj: HGDIOBJ) -> HGDIOBJ {
    unsafe { windows::Win32::Graphics::Gdi::SelectObject(hdc, obj) }
}

pub fn delete_object(obj: HGDIOBJ) {
    unsafe { let _ = windows::Win32::Graphics::Gdi::DeleteObject(obj); }
}

pub fn create_compatible_dc(hdc: Option<HDC>) -> Option<HDC> {
    let dc = unsafe { windows::Win32::Graphics::Gdi::CreateCompatibleDC(hdc) };
    if dc.is_invalid() { None } else { Some(dc) }
}

pub fn create_compatible_bitmap(hdc: HDC, w: i32, h: i32) -> Option<HBITMAP> {
    let bmp = unsafe { windows::Win32::Graphics::Gdi::CreateCompatibleBitmap(hdc, w, h) };
    if bmp.is_invalid() { None } else { Some(bmp) }
}

pub fn delete_dc(hdc: HDC) {
    unsafe { let _ = windows::Win32::Graphics::Gdi::DeleteDC(hdc); }
}

pub fn bitblt(dest: HDC, x: i32, y: i32, w: i32, h: i32, src: HDC, sx: i32, sy: i32) {
    unsafe { let _ = windows::Win32::Graphics::Gdi::BitBlt(dest, x, y, w, h, Some(src), sx, sy, windows::Win32::Graphics::Gdi::SRCCOPY); }
}

pub fn fill_rect(hdc: HDC, rect: &RECT, brush: HBRUSH) {
    unsafe { windows::Win32::Graphics::Gdi::FillRect(hdc, rect, brush); }
}

pub fn invalidate_rect(hwnd: HWND, rect: Option<&RECT>) {
    unsafe { let _ = windows::Win32::Graphics::Gdi::InvalidateRect(Some(hwnd), rect.map(|r| r as *const RECT), true); }
}

pub fn create_solid_brush(color: COLORREF) -> HBRUSH {
    unsafe { windows::Win32::Graphics::Gdi::CreateSolidBrush(color) }
}

pub fn create_font(height: i32, weight: i32, italic: bool, name: &[u16]) -> Option<HFONT> {
    unsafe {
        let font = windows::Win32::Graphics::Gdi::CreateFontW(
            height, 0, 0, 0, weight,
            if italic { 1 } else { 0 },
            0, 0,
            windows::Win32::Graphics::Gdi::FONT_CHARSET(windows::Win32::Graphics::Gdi::DEFAULT_CHARSET.0),
            windows::Win32::Graphics::Gdi::FONT_OUTPUT_PRECISION(windows::Win32::Graphics::Gdi::OUT_DEFAULT_PRECIS.0),
            windows::Win32::Graphics::Gdi::FONT_CLIP_PRECISION(windows::Win32::Graphics::Gdi::CLIP_DEFAULT_PRECIS.0),
            windows::Win32::Graphics::Gdi::FONT_QUALITY(windows::Win32::Graphics::Gdi::DEFAULT_QUALITY.0),
            windows::Win32::Graphics::Gdi::FF_DONTCARE.0 as u32,
            windows::core::PCWSTR(name.as_ptr()),
        );
        if font.is_invalid() { None } else { Some(font) }
    }
}

pub fn move_to(hdc: HDC, x: i32, y: i32) {
    unsafe { let _ = windows::Win32::Graphics::Gdi::MoveToEx(hdc, x, y, None); }
}

pub fn line_to(hdc: HDC, x: i32, y: i32) {
    unsafe { let _ = windows::Win32::Graphics::Gdi::LineTo(hdc, x, y); }
}

pub fn create_pen(style: PEN_STYLE, width: i32, color: COLORREF) -> HPEN {
    unsafe { windows::Win32::Graphics::Gdi::CreatePen(style, width, color) }
}

pub fn get_stock_object(flag: GET_STOCK_OBJECT_FLAGS) -> HGDIOBJ {
    unsafe { windows::Win32::Graphics::Gdi::GetStockObject(flag) }
}

pub fn round_rect(hdc: HDC, left: i32, top: i32, right: i32, bottom: i32, corner_w: i32, corner_h: i32) {
    unsafe { let _ = windows::Win32::Graphics::Gdi::RoundRect(hdc, left, top, right, bottom, corner_w, corner_h); }
}

pub fn set_pixel(hdc: HDC, x: i32, y: i32, color: COLORREF) {
    unsafe { windows::Win32::Graphics::Gdi::SetPixel(hdc, x, y, color); }
}

pub fn to_wide(s: &str) -> Vec<u16> {
    let mut v: Vec<u16> = s.encode_utf16().collect();
    v.push(0);
    v
}
