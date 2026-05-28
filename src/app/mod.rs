use windows::Win32::Foundation::{HWND, HINSTANCE, RECT, LPARAM, WPARAM};
use windows::Win32::UI::WindowsAndMessaging::WNDCLASSW;
use windows::Win32::Graphics::Gdi::HDC;
use crate::win32;
use crate::ui::color::{ThemePalette, DARK, LIGHT};
use crate::ui::font::{FontRegistry, FontKey};
use crate::ui::brush::BrushRegistry;
use crate::ui::render::{Renderer, fill_rect, draw_text, draw_rounded_rect};
use crate::ui::animated::AnimatedBackground;
use crate::state::{AppState, TabId, Tab, TabOrFolder, Workspace, WorkspaceId, Folder, FolderId};
use crate::webview::WebViewManager;
use crate::events;

const ANIMATION_TIMER_ID: usize = 1001;
const SIDEBAR_ANIM_TIMER_ID: usize = 1002;

#[derive(Clone, Copy, PartialEq)]
pub enum SidebarMode { Hidden, Overlay, Pushed }
#[derive(Clone, Copy, PartialEq)]
pub enum ThemeMode { Dark, Light }

pub struct App {
    pub hwnd: HWND,
    pub hinstance: HINSTANCE,
    pub renderer: Renderer,
    pub theme: ThemeMode,
    pub dpi: u32,
    pub fonts: FontRegistry,
    pub brushes: BrushRegistry,
    pub animated_bg: AnimatedBackground,
    pub sidebar_mode: SidebarMode,
    pub sidebar_target_width: i32,
    pub sidebar_current_width: i32,
    pub sidebar_animating: bool,
    pub window_width: i32,
    pub window_height: i32,
    pub topbar_height: i32,
    pub mouse_x: i32,
    pub mouse_y: i32,
    pub mouse_in_sidebar: bool,
    pub mouse_in_topbar: bool,
    pub hovered_tab: Option<usize>,
    pub hovered_workspace: Option<usize>,

    pub state: AppState,
    pub webview: WebViewManager,
    pub webview_init: bool,
    pub address_text: String,
    pub address_focused: bool,
    pub is_loading: bool,
    pub can_go_back: bool,
    pub can_go_forward: bool,
}

impl App {
    pub fn new() -> Self {
        let dpi = 96;
        Self {
            hwnd: HWND::default(), hinstance: HINSTANCE::default(),
            renderer: Renderer::new(), theme: ThemeMode::Dark, dpi,
            fonts: FontRegistry::new(dpi), brushes: BrushRegistry::new(),
            animated_bg: AnimatedBackground::new(),
            sidebar_mode: SidebarMode::Pushed, sidebar_target_width: 240,
            sidebar_current_width: 240, sidebar_animating: false,
            window_width: 1200, window_height: 800, topbar_height: 44,
            mouse_x: 0, mouse_y: 0, mouse_in_sidebar: false, mouse_in_topbar: false,
            hovered_tab: None, hovered_workspace: None,
            state: AppState::default(),
            webview: WebViewManager::new(),
            webview_init: false,
            address_text: String::new(),
            address_focused: false, is_loading: false,
            can_go_back: false, can_go_forward: false,
        }
    }

    pub fn create_window(&mut self) {
        let instance = win32::get_module_handle();
        self.hinstance = instance;
        let class_name = win32::to_wide("AsterBrowserWindow");
        let window_title = win32::to_wide("Aster Browser");

        let wc = WNDCLASSW {
            style: windows::Win32::UI::WindowsAndMessaging::CS_DBLCLKS
                | windows::Win32::UI::WindowsAndMessaging::CS_HREDRAW
                | windows::Win32::UI::WindowsAndMessaging::CS_VREDRAW,
            lpfnWndProc: Some(Self::wnd_proc_thunk),
            cbClsExtra: 0, cbWndExtra: 0, hInstance: instance,
            hIcon: Default::default(),
            hCursor: win32::load_cursor_default(),
            hbrBackground: Default::default(),
            lpszMenuName: windows::core::PCWSTR::null(),
            lpszClassName: windows::core::PCWSTR(class_name.as_ptr()),
        };
        win32::register_class(&wc);

        if let Some(hwnd) = win32::create_window(&class_name, &window_title, instance) {
            self.hwnd = hwnd;
            win32::set_userdata(hwnd, self as *mut Self as isize);
            win32::show_window(hwnd);
            self.on_create(hwnd);
        }
    }

    pub fn run(&self) {
        let mut msg = windows::Win32::UI::WindowsAndMessaging::MSG::default();
        while win32::get_message(&mut msg, None, 0, 0) {
            win32::translate_message(&msg);
            win32::dispatch_message(&msg);
        }
    }

    unsafe extern "system" fn wnd_proc_thunk(
        hwnd: HWND, msg: u32, wparam: WPARAM, lparam: LPARAM,
    ) -> windows::Win32::Foundation::LRESULT {
        let ptr = win32::get_userdata(hwnd);
        if ptr == 0 { return win32::def_window_proc(hwnd, msg, wparam, lparam); }
        let app = unsafe { &mut *(ptr as *mut App) };
        events::handle_message(app, hwnd, msg, wparam, lparam)
    }

    pub fn on_create(&mut self, _hwnd: HWND) {
        win32::set_timer(self.hwnd, ANIMATION_TIMER_ID, 50);
        win32::set_timer(self.hwnd, SIDEBAR_ANIM_TIMER_ID, 16);
        self.ensure_webview();
    }

    fn ensure_webview(&mut self) {
        if self.webview_init { return; }
        if let Err(e) = self.webview.initialize(self.hwnd) {
            eprintln!("WebView2 init error: {}", e);
        }
        self.webview_init = true;
    }

    pub fn on_close(&self) { win32::destroy_window(self.hwnd); }

    pub fn on_paint(&mut self) {
        let mut ps: windows::Win32::Graphics::Gdi::PAINTSTRUCT = unsafe { std::mem::zeroed() };
        let hdc = win32::begin_paint(self.hwnd, &mut ps);
        if hdc.is_invalid() { return; }
        let rect = win32::get_client_rect(self.hwnd);
        let w = rect.right - rect.left;
        let h = rect.bottom - rect.top;

        if let Some(hdc_buf) = self.renderer.begin_frame(hdc, w, h).map(|bb| bb.hdc) {
            fill_rect(hdc_buf, &RECT { left: 0, top: 0, right: w, bottom: h }, self.brushes.get(self.palette().background));
            self.render_topbar(hdc_buf, w);
            self.render_sidebar(hdc_buf, w, h);
            self.render_content_bg(hdc_buf, w, h);
            self.render_workspace_switcher(hdc_buf, w, h);
            self.renderer.end_frame(hdc);
        }
        win32::end_paint(self.hwnd, &ps);
    }

    pub fn on_resize(&mut self, width: i32, height: i32, _: u32) {
        self.window_width = width; self.window_height = height;
        self.update_webview_rect();
        self.renderer.refresh(self.hwnd);
    }

    fn update_webview_rect(&self) {
        let content = self.get_content_rect();
        let ws = self.state.active_workspace();
        if let Some(active_id) = ws.active_tab_id {
            self.webview.set_visibility(active_id, true, self.hwnd, content);
        }
    }

    pub fn on_dpi_changed(&mut self, new_dpi: u32, lparam: LPARAM) {
        self.dpi = new_dpi;
        self.fonts.set_dpi(new_dpi);
        self.topbar_height = scale_value(44, new_dpi);
        self.sidebar_target_width = scale_value(240, new_dpi);
        self.sidebar_current_width = self.sidebar_target_width;
        if let Some(new_rect) = unsafe { (lparam.0 as *const RECT).as_ref() } {
            win32::set_window_pos(self.hwnd, new_rect.left, new_rect.top,
                new_rect.right - new_rect.left, new_rect.bottom - new_rect.top);
        }
        self.renderer.refresh(self.hwnd);
    }

    pub fn on_mouse_move(&mut self, x: i32, y: i32, _: u32) {
        self.mouse_x = x; self.mouse_y = y;
        let old_s = self.mouse_in_sidebar; let old_t = self.mouse_in_topbar;
        self.mouse_in_sidebar = self.is_point_in_sidebar(x, y);
        self.mouse_in_topbar = y < self.topbar_height;

        let ws = self.state.active_workspace();
        self.hovered_tab = if self.mouse_in_sidebar {
            self.hit_test_tab(x, y, &ws.tabs)
        } else { None };
        self.hovered_workspace = if self.mouse_in_sidebar && !self.mouse_in_topbar {
            self.hit_test_workspace(x, y)
        } else { None };

        if old_s != self.mouse_in_sidebar || old_t != self.mouse_in_topbar || self.hovered_tab.is_some() {
            self.renderer.refresh(self.hwnd);
        }
    }

    pub fn on_lbutton_down(&mut self, x: i32, y: i32, _: u32) {
        if self.mouse_in_sidebar {
            if let Some(idx) = self.hit_test_tab(x, y, &self.state.active_workspace().tabs) {
                self.activate_tab(idx);
            }
            if let Some(ws_idx) = self.hit_test_workspace(x, y) {
                self.switch_workspace(ws_idx);
            }
        }
        if y < self.topbar_height {
            if x < 36 { self.toggle_sidebar(); }
        }
    }

    pub fn on_lbutton_up(&mut self, _: i32, _: i32, _: u32) {}
    pub fn on_mouse_wheel(&mut self, _: i32, _: i32, _: i32) { self.renderer.refresh(self.hwnd); }

    pub fn on_key_down(&mut self, vkey: u32, _: u32) {
        match vkey {
            0x46 if (unsafe { windows::Win32::UI::Input::KeyboardAndMouse::GetAsyncKeyState(0x11) } & (0x8000u16 as i16)) != 0 => self.toggle_theme(),
            0x54 if (unsafe { windows::Win32::UI::Input::KeyboardAndMouse::GetAsyncKeyState(0x11) } & (0x8000u16 as i16)) != 0 => self.new_tab(),
            0x4E if (unsafe { windows::Win32::UI::Input::KeyboardAndMouse::GetAsyncKeyState(0x11) } & (0x8000u16 as i16)) != 0 => self.new_tab(),
            0x57 if (unsafe { windows::Win32::UI::Input::KeyboardAndMouse::GetAsyncKeyState(0x11) } & (0x8000u16 as i16)) != 0 && (unsafe { windows::Win32::UI::Input::KeyboardAndMouse::GetAsyncKeyState(0x10) } & (0x8000u16 as i16)) != 0 => self.close_current_tab(),
            _ => {}
        }
    }
    pub fn on_char(&mut self, _: u32) {}

    pub fn on_timer(&mut self, timer_id: usize) {
        if timer_id == ANIMATION_TIMER_ID { self.animated_bg.tick(); self.renderer.refresh(self.hwnd); }
        else if timer_id == SIDEBAR_ANIM_TIMER_ID { self.tick_sidebar_animation(); }
    }
    pub fn on_power_change(&mut self) {}

    // --- Tab Management ---

    pub fn new_tab(&mut self) {
        let id = TabId(self.state.next_tab_id);
        self.state.next_tab_id += 1;
        let tab = Tab {
            id, title: "New Tab".into(), url: "about:blank".into(),
            is_pinned: false, is_sleeping: false, is_loading: false,
            scroll_offset: 0, history: vec![], history_index: 0,
            site_theme: crate::state::ThemeMode::Auto, container_id: None,
        };
        self.state.active_workspace_mut().tabs.push(TabOrFolder::Tab(tab));
        self.state.active_workspace_mut().active_tab_id = Some(id);
        self.address_text.clear();
        self.ensure_webview();
        self.update_webview_rect();
        self.renderer.refresh(self.hwnd);
    }

    fn close_current_tab(&mut self) {
        let ws = self.state.active_workspace();
        if let Some(active_id) = ws.active_tab_id {
            let idx = ws.tabs.iter().position(|t| match t {
                TabOrFolder::Tab(t) => t.id == active_id,
                _ => false,
            });
            if let Some(idx) = idx {
                self.state.active_workspace_mut().tabs.remove(idx);
                self.state.active_workspace_mut().active_tab_id = None;
                self.webview.remove_tab(active_id);
                self.renderer.refresh(self.hwnd);
            }
        }
    }

    fn activate_tab(&mut self, idx: usize) {
        let ws = self.state.active_workspace_mut();
        let tab_opt = ws.tabs.get(idx).and_then(|t| match t {
            TabOrFolder::Tab(t) => Some(t.clone()),
            _ => None,
        });
        if let Some(tab) = tab_opt {
            ws.active_tab_id = Some(tab.id);
            self.address_text = tab.url.clone();
            self.update_webview_rect();
            self.renderer.refresh(self.hwnd);
        }
    }

    fn switch_workspace(&mut self, idx: usize) {
        if idx < self.state.workspaces.len() {
            self.state.active_workspace_index = idx;
            self.update_webview_rect();
            self.renderer.refresh(self.hwnd);
        }
    }

    // --- Rendering ---

    fn render_topbar(&mut self, hdc: HDC, w: i32) {
        let p = self.palette().clone();
        let th = self.topbar_height;
        fill_rect(hdc, &RECT { left: 0, top: 0, right: w, bottom: th }, self.brushes.get(p.surface));
        fill_rect(hdc, &RECT { left: 0, top: th - 1, right: w, bottom: th }, self.brushes.get(p.divider));

        let icon_font = self.fonts.get(FontKey { size: 16, bold: false, italic: false });
        draw_text(hdc, if self.sidebar_mode == SidebarMode::Hidden { "\u{2630}" } else { "\u{229E}" }, 10, 12, p.text_primary, icon_font);

        let btn_rect = RECT { left: 36, top: 0, right: 56, bottom: th };
        draw_text(hdc, "\u{25C0}", 38, 12, if self.can_go_back { p.text_primary } else { p.text_secondary }, self.fonts.get(FontKey { size: 12, bold: false, italic: false }));
        draw_text(hdc, "\u{25B6}", 56, 12, if self.can_go_forward { p.text_primary } else { p.text_secondary }, self.fonts.get(FontKey { size: 12, bold: false, italic: false }));

        let reload_char = if self.is_loading { "\u{2715}" } else { "\u{21BB}" };
        draw_text(hdc, reload_char, 74, 12, p.text_primary, self.fonts.get(FontKey { size: 14, bold: false, italic: false }));

        let addr_x = 94;
        let addr_w = (w - addr_x - 12).max(100);
        let addr_rect = RECT { left: addr_x, top: 6, right: addr_x + addr_w, bottom: th - 6 };
        let addr_h = addr_rect.bottom - addr_rect.top;
        draw_rounded_rect(hdc, &addr_rect, self.brushes.get(p.surface_raised), 6);
        let display_url = if self.address_text.is_empty() { "Search or enter URL..." } else { &self.address_text };
        let url_color = if self.address_text.is_empty() { p.text_secondary } else { p.text_primary };
        draw_text(hdc, display_url, addr_x + 10, 12, url_color, self.fonts.get(FontKey { size: 13, bold: false, italic: false }));
    }

    fn render_sidebar(&mut self, hdc: HDC, w: i32, _h: i32) {
        if self.sidebar_mode == SidebarMode::Hidden || self.sidebar_current_width <= 0 { return; }
        let p = self.palette().clone();
        let sw = self.sidebar_current_width;
        let th = self.topbar_height;
        fill_rect(hdc, &RECT { left: 0, top: th, right: sw, bottom: _h }, self.brushes.get(p.surface));
        fill_rect(hdc, &RECT { left: sw - 1, top: th, right: sw, bottom: _h }, self.brushes.get(p.divider));

        let ws = self.state.active_workspace();
        let tabs = &ws.tabs;
        let active_id = ws.active_tab_id;

        if tabs.is_empty() {
            let ef = self.fonts.get(FontKey { size: 13, bold: false, italic: false });
            draw_text(hdc, "No open tabs", 16, th + 36, p.text_secondary, ef);
            draw_text(hdc, "Ctrl+T to open a tab", 16, th + 54, p.text_secondary, ef);
            return;
        }

        let row_h = 32;
        let start_y = th + 8;
        for (i, item) in tabs.iter().enumerate() {
            let y = start_y + (i as i32) * row_h;
            let is_active = match item {
                TabOrFolder::Tab(t) => Some(t.id) == active_id,
                _ => false,
            };
            let is_hovered = self.hovered_tab == Some(i);

            if is_active {
                fill_rect(hdc, &RECT { left: 0, top: y, right: sw, bottom: y + row_h }, self.brushes.get(p.accent));
                fill_rect(hdc, &RECT { left: 0, top: y, right: 3, bottom: y + row_h }, self.brushes.get(p.accent_hover));
            } else if is_hovered {
                fill_rect(hdc, &RECT { left: 0, top: y, right: sw, bottom: y + row_h }, self.brushes.get(p.hover));
            }

            let title = match item {
                TabOrFolder::Tab(t) => &t.title,
                TabOrFolder::Folder(f) => &f.name,
            };
            let icon = match item {
                TabOrFolder::Tab(_) => "\u{1F310}",
                TabOrFolder::Folder(_) => "\u{1F4C1}",
            };

            let text_color = if is_active { p.background } else { p.text_primary };
            draw_text(hdc, icon, 12, y + 6, text_color, self.fonts.get(FontKey { size: 11, bold: false, italic: false }));
            draw_text(hdc, title, 34, y + 7, text_color, self.fonts.get(FontKey { size: 12, bold: false, italic: false }));

            if matches!(item, TabOrFolder::Tab(t) if t.is_loading) {
                draw_text(hdc, "\u{25D0}", sw - 20, y + 7, text_color, self.fonts.get(FontKey { size: 10, bold: false, italic: false }));
            }
        }
    }

    fn render_content_bg(&mut self, hdc: HDC, w: i32, _h: i32) {
        let left = if self.sidebar_mode == SidebarMode::Pushed { self.sidebar_current_width } else { 0 };
        let cr = RECT { left, top: self.topbar_height, right: w, bottom: _h };
        self.animated_bg.render(hdc, &cr, self.theme == ThemeMode::Dark);
    }

    fn render_workspace_switcher(&mut self, hdc: HDC, _w: i32, _h: i32) {
        if self.sidebar_mode == SidebarMode::Hidden || self.sidebar_current_width <= 0 { return; }
        let p = self.palette().clone();
        let sw = self.sidebar_current_width;
        let bh = 36;
        let by = self.window_height - bh;

        fill_rect(hdc, &RECT { left: 0, top: by, right: sw, bottom: self.window_height }, self.brushes.get(p.surface_sunken));
        fill_rect(hdc, &RECT { left: 0, top: by, right: sw, bottom: by + 1 }, self.brushes.get(p.divider));

        let ws_count = self.state.workspaces.len();
        let chip_w = (sw - 16).max(40) / ws_count.max(1);
        for (i, ws) in self.state.workspaces.iter().enumerate() {
            let cx = 8 + (i as i32) * (chip_w + 4);
            let is_active = i == self.state.active_workspace_index;
            let chip_bg = if is_active { p.accent } else { p.surface_raised };
            let chip_rect = RECT { left: cx, top: by + 4, right: cx + chip_w, bottom: by + bh - 4 };
            draw_rounded_rect(hdc, &chip_rect, self.brushes.get(chip_bg), 4);
            draw_text(hdc, &ws.name, cx + 6, by + 8, if is_active { p.background } else { p.text_primary },
                      self.fonts.get(FontKey { size: 11, bold: false, italic: false }));
        }

        let plus_x = 8 + (ws_count as i32) * (chip_w + 4);
        draw_text(hdc, "+", plus_x + 4, by + 7, p.text_secondary, self.fonts.get(FontKey { size: 14, bold: false, italic: false }));
    }

    // --- Hit Testing ---

    fn hit_test_tab(&self, x: i32, y: i32, tabs: &[TabOrFolder]) -> Option<usize> {
        let th = self.topbar_height;
        let row_h = 32;
        let start_y = th + 8;
        for (i, _) in tabs.iter().enumerate() {
            let ty = start_y + (i as i32) * row_h;
            if x >= 0 && x < self.sidebar_current_width && y >= ty && y < ty + row_h {
                return Some(i);
            }
        }
        None
    }

    fn hit_test_workspace(&self, x: i32, y: i32) -> Option<usize> {
        if self.sidebar_mode == SidebarMode::Hidden || self.sidebar_current_width <= 0 { return None; }
        let sw = self.sidebar_current_width;
        let bh = 36;
        let by = self.window_height - bh;
        if x >= 0 && x < sw && y >= by && y < self.window_height {
            let chip_w = (sw - 16).max(40) / self.state.workspaces.len().max(1);
            let idx = ((x - 8) / (chip_w + 4)) as usize;
            if idx < self.state.workspaces.len() { return Some(idx); }
        }
        None
    }

    // --- Helpers ---

    pub fn palette(&self) -> &ThemePalette {
        match self.theme { ThemeMode::Dark => &DARK, ThemeMode::Light => &LIGHT }
    }

    pub fn toggle_theme(&mut self) {
        self.theme = match self.theme { ThemeMode::Dark => ThemeMode::Light, ThemeMode::Light => ThemeMode::Dark };
        self.renderer.refresh(self.hwnd);
    }

    pub fn toggle_sidebar(&mut self) {
        self.sidebar_mode = match self.sidebar_mode {
            SidebarMode::Hidden => SidebarMode::Pushed,
            SidebarMode::Overlay => SidebarMode::Hidden,
            SidebarMode::Pushed => SidebarMode::Hidden,
        };
        self.sidebar_target_width = if self.sidebar_mode == SidebarMode::Hidden { 0 } else { scale_value(240, self.dpi) };
        self.sidebar_animating = true;
    }

    fn tick_sidebar_animation(&mut self) {
        if !self.sidebar_animating { return; }
        let diff = self.sidebar_target_width - self.sidebar_current_width;
        if diff.abs() <= 1 { self.sidebar_current_width = self.sidebar_target_width; self.sidebar_animating = false; }
        else { self.sidebar_current_width += (diff as f64 * 0.25) as i32; }
        self.renderer.refresh(self.hwnd);
    }

    pub fn is_point_in_sidebar(&self, x: i32, y: i32) -> bool {
        if self.sidebar_mode == SidebarMode::Hidden || self.sidebar_current_width <= 0 { return false; }
        if self.sidebar_mode == SidebarMode::Overlay && x > self.sidebar_current_width { return false; }
        x < self.sidebar_current_width && y > self.topbar_height
    }

    pub fn get_content_rect(&self) -> RECT {
        let left = if self.sidebar_mode == SidebarMode::Pushed { self.sidebar_current_width } else { 0 };
        RECT { left, top: self.topbar_height, right: self.window_width, bottom: self.window_height }
    }
}

fn scale_value(value: i32, dpi: u32) -> i32 {
    if dpi == 0 { return value; }
    (value * dpi as i32) / 96
}
