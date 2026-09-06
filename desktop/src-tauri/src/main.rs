// mib-gold desktop shell: spawns the Python/FastAPI backend as a sidecar, then loads the React UI.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::sync::Mutex;
use tauri::Manager;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

struct Sidecar(Mutex<Option<CommandChild>>);

#[tauri::command]
fn backend_url() -> String {
    std::env::var("MIBGOLD_BACKEND_URL").unwrap_or_else(|_| "http://127.0.0.1:8001".to_string())
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(Sidecar(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![backend_url])
        .setup(|app| {
            // Sidecar binary name must match "externalBin" in tauri.conf.json (mibgold-backend[-triple].exe)
            let sidecar = app.shell().sidecar("mibgold-backend")?;
            let (mut rx, child) = sidecar.spawn()?;
            app.state::<Sidecar>().0.lock().unwrap().replace(child);
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    if let CommandEvent::Stderr(line) | CommandEvent::Stdout(line) = event {
                        eprintln!("[backend] {}", String::from_utf8_lossy(&line));
                    }
                }
            });
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(child) = window.state::<Sidecar>().0.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running mib-gold");
}
