#![cfg_attr(all(not(debug_assertions), windows), windows_subsystem = "windows")]

#[cfg(windows)]
mod app;
#[cfg(windows)]
mod ui;
#[cfg(windows)]
mod events;
#[cfg(windows)]
mod state;
#[cfg(windows)]
mod config;
#[cfg(windows)]
mod drag;
#[cfg(windows)]
mod webview;
#[cfg(windows)]
mod win32;

#[cfg(windows)]
fn main() {
    let mut app = app::App::new();
    app.create_window();
    app.run();
}

#[cfg(not(windows))]
fn main() {
    println!("The Aster Browser (Rust component) is currently only supported on Windows.");
    println!("The Python component (pixelification) is supported on Linux and macOS.");
}
