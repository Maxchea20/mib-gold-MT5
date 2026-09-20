#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{Manager, WindowEvent};

#[tauri::command]
fn backend_url() -> String {
    std::env::var("MIBGOLD_BACKEND_URL").unwrap_or_else(|_| "http://127.0.0.1:8001".to_string())
}

fn show_main(app: &tauri::AppHandle) {
    if let Some(win) = app.get_webview_window("main") {
        let _ = win.unminimize();
        let _ = win.show();
        let _ = win.set_focus();
    }
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![backend_url])
        .setup(|app| {
            let show = MenuItem::with_id(app, "show", "Show MIB Gold", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Exit MIB Gold", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &quit])?;

            let mut tray = TrayIconBuilder::with_id("main")
                .menu(&menu)
                .tooltip("MIB Gold · running")
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id().as_ref() {
                    "show" => show_main(app),
                    "quit" => app.exit(0),
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        show_main(tray.app_handle());
                    }
                });

            if let Some(icon) = app.default_window_icon() {
                tray = tray.icon(icon.clone());
            }

            tray.build(app)?;
            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running MIB Gold");
}