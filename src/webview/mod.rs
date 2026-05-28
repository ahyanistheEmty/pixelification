use std::collections::HashMap;
use windows::Win32::Foundation::{HWND, RECT, LPARAM};
use crate::state::TabId;

pub struct WebViewManager {
    controllers: HashMap<TabId, WebViewInstance>,
    next_id: u64,
    env_ready: bool,
    user_data_folder: String,
}

pub struct WebViewInstance {
    pub tab_id: TabId,
    pub controller: Option<webview2_com::Controller>,
    pub webview: Option<webview2_com::WebView>,
    pub is_visible: bool,
}

impl WebViewManager {
    pub fn new() -> Self {
        let appdata = std::env::var("APPDATA").unwrap_or_else(|_| "%APPDATA%".into());
        Self {
            controllers: HashMap::new(),
            next_id: 1,
            env_ready: false,
            user_data_folder: format!("{}\\Aster\\WebView2", appdata),
        }
    }

    pub fn initialize(&mut self, parent_hwnd: HWND) -> Result<(), String> {
        let env = webview2_com::Environment::create(
            Some(&self.user_data_folder),
            None, None,
        ).map_err(|e| format!("Failed to create WebView2 env: {:?}", e))?;

        let controller = webview2_com::Controller::create(
            &env,
            parent_hwnd,
            webview2_com::RECT { left: 0, top: 0, right: 800, bottom: 600 },
        ).map_err(|e| format!("Failed to create WebView2 controller: {:?}", e))?;

        let webview = controller.web_view().unwrap();
        webview.navigate("https://duckduckgo.com").unwrap();
        self.env_ready = true;
        Ok(())
    }

    pub fn create_for_tab(&mut self, tab_id: TabId, parent_hwnd: HWND) {
        if !self.env_ready { return; }
        let id = self.next_id; self.next_id += 1;
        let instance = WebViewInstance {
            tab_id,
            controller: None,
            webview: None,
            is_visible: false,
        };
        self.controllers.insert(tab_id, instance);
    }

    pub fn remove_tab(&mut self, tab_id: TabId) {
        if let Some(instance) = self.controllers.remove(&tab_id) {
            drop(instance);
        }
    }

    pub fn navigate(&self, tab_id: TabId, url: &str) {
        if let Some(instance) = self.controllers.get(&tab_id) {
            if let Some(ref webview) = instance.webview {
                let normalized = if !url.contains("://") {
                    format!("https://{}", url)
                } else {
                    url.to_string()
                };
                webview.navigate(&normalized).unwrap();
            }
        }
    }

    pub fn set_visibility(&mut self, tab_id: TabId, visible: bool, parent_hwnd: HWND, rect: RECT) {
        if let Some(instance) = self.controllers.get_mut(&tab_id) {
            instance.is_visible = visible;
            if let Some(ref controller) = instance.controller {
                let wv_rect = webview2_com::RECT {
                    left: rect.left,
                    top: rect.top,
                    right: rect.right,
                    bottom: rect.bottom,
                };
                controller.put_bounds(&wv_rect).unwrap();
                controller.put_is_visible(visible).unwrap();
            }
        }
    }

    pub fn go_back(&self, tab_id: TabId) {
        if let Some(instance) = self.controllers.get(&tab_id) {
            if let Some(ref webview) = instance.webview {
                webview.go_back().unwrap();
            }
        }
    }

    pub fn go_forward(&self, tab_id: TabId) {
        if let Some(instance) = self.controllers.get(&tab_id) {
            if let Some(ref webview) = instance.webview {
                webview.go_forward().unwrap();
            }
        }
    }

    pub fn reload(&self, tab_id: TabId) {
        if let Some(instance) = self.controllers.get(&tab_id) {
            if let Some(ref webview) = instance.webview {
                webview.reload().unwrap();
            }
        }
    }

    pub fn stop(&self, tab_id: TabId) {
        if let Some(instance) = self.controllers.get(&tab_id) {
            if let Some(ref webview) = instance.webview {
                webview.stop().unwrap();
            }
        }
    }
}
