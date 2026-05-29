use windows::Win32::Foundation::{HWND, WPARAM, LPARAM, LRESULT};
use windows::Win32::UI::WindowsAndMessaging::{
    WM_CREATE, WM_DESTROY, WM_CLOSE, WM_PAINT, WM_SIZE, WM_ERASEBKGND,
    WM_DPICHANGED, WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP,
    WM_MOUSEWHEEL, WM_KEYDOWN, WM_CHAR, WM_TIMER, WM_POWERBROADCAST,
    DefWindowProcW, PostQuitMessage,
};

use crate::app::App;

const PBT_APMPOWERSTATUSCHANGE: u32 = 0x000A;

pub fn handle_message(app: &mut App, hwnd: HWND, msg: u32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    match msg {
        WM_CREATE => { app.on_create(hwnd); LRESULT(0) }
        WM_DESTROY => { unsafe { PostQuitMessage(0); } LRESULT(0) }
        WM_CLOSE => { app.on_close(); LRESULT(0) }
        WM_PAINT => { app.on_paint(); LRESULT(0) }
        WM_ERASEBKGND => LRESULT(1),
        WM_SIZE => {
            app.on_resize((lparam.0 & 0xFFFF) as i32, ((lparam.0 >> 16) & 0xFFFF) as i32, wparam.0 as u32);
            LRESULT(0)
        }
        WM_DPICHANGED => { app.on_dpi_changed((wparam.0 & 0xFFFF) as u32, lparam); LRESULT(0) }
        WM_MOUSEMOVE => { app.on_mouse_move((lparam.0 & 0xFFFF) as i32, ((lparam.0 >> 16) & 0xFFFF) as i32, wparam.0 as u32); LRESULT(0) }
        WM_LBUTTONDOWN => { app.on_lbutton_down((lparam.0 & 0xFFFF) as i32, ((lparam.0 >> 16) & 0xFFFF) as i32, wparam.0 as u32); LRESULT(0) }
        WM_LBUTTONUP => { app.on_lbutton_up((lparam.0 & 0xFFFF) as i32, ((lparam.0 >> 16) & 0xFFFF) as i32, wparam.0 as u32); LRESULT(0) }
        WM_MOUSEWHEEL => { app.on_mouse_wheel((lparam.0 & 0xFFFF) as i32, ((lparam.0 >> 16) & 0xFFFF) as i32, ((wparam.0 >> 16) as i16) as i32); LRESULT(0) }
        WM_KEYDOWN => { app.on_key_down(wparam.0 as u32, lparam.0 as u32); LRESULT(0) }
        WM_CHAR => { app.on_char(wparam.0 as u32); LRESULT(0) }
        WM_TIMER => { app.on_timer(wparam.0 as usize); LRESULT(0) }
        WM_POWERBROADCAST => {
            if wparam.0 as u32 == PBT_APMPOWERSTATUSCHANGE { app.on_power_change(); }
            LRESULT(0)
        }
        _ => unsafe { DefWindowProcW(hwnd, msg, wparam, lparam) },
    }
}
