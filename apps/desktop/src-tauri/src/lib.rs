mod sidecar;

use sidecar::Sidecar;
use tauri::Manager;

#[derive(serde::Serialize, Clone)]
struct SidecarInfo {
    port: u16,
    token: String,
}

#[tauri::command]
fn sidecar_info(state: tauri::State<SidecarInfo>) -> SidecarInfo {
    state.inner().clone()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            match Sidecar::spawn() {
                Ok(side) => {
                    app.manage(SidecarInfo {
                        port: side.port,
                        token: side.token.clone(),
                    });
                    app.manage(side);
                }
                Err(e) => {
                    eprintln!("CaYaScribe sidecar spawn failed: {e}");
                    app.manage(SidecarInfo {
                        port: 8765,
                        token: "dev-token".into(),
                    });
                }
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![sidecar_info])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
