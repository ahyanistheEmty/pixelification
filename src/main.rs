#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod app;
mod ui;
mod events;
mod state;
mod config;
mod drag;
mod webview;
mod win32;

use app::App;

fn main() {
    let mut app = App::new();
    app.create_window();
    app.run();
}
