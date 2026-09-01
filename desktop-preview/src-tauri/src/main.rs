#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

// This binary only hosts the static preview UI in `dist/` — it does not call
// into the real Munshiji engine (src/munshiji/). See desktop-preview/README.md.
fn main() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running the Munshiji preview shell");
}
