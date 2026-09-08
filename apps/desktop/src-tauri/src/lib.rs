mod sidecar;

use sidecar::Sidecar;
use tauri::Manager;

#[derive(serde::Serialize, Clone)]
struct SidecarInfo {
    port: u16,
    token: String,
    error: Option<String>,
}

#[tauri::command]
fn sidecar_info(state: tauri::State<SidecarInfo>) -> SidecarInfo {
    state.inner().clone()
}

fn write_file(path: &str, bytes: &[u8]) -> Result<(), String> {
    let p = std::path::PathBuf::from(path);
    if path.trim().is_empty() {
        return Err("empty_path".into());
    }
    if let Some(parent) = p.parent() {
        if !parent.as_os_str().is_empty() {
            std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
        }
    }
    std::fs::write(&p, bytes).map_err(|e| e.to_string())
}

#[tauri::command]
fn save_text_file(path: String, contents: String) -> Result<(), String> {
    write_file(&path, contents.as_bytes())
}

#[tauri::command]
fn save_bytes_file(path: String, contents: Vec<u8>) -> Result<(), String> {
    write_file(&path, &contents)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            let resource_dir = app.path().resource_dir().ok();
            let exe_dir = std::env::current_exe()
                .ok()
                .and_then(|p| p.parent().map(|d| d.to_path_buf()));
            match Sidecar::spawn(resource_dir, exe_dir) {
                Ok(side) => {
                    app.manage(SidecarInfo {
                        port: side.port,
                        token: side.token.clone(),
                        error: None,
                    });
                    app.manage(side);
                }
                Err(e) => {
                    eprintln!("CaYaScribe sidecar spawn failed: {e}");
                    app.manage(SidecarInfo {
                        port: 8765,
                        token: "dev-token".into(),
                        error: Some(e),
                    });
                }
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![sidecar_info, save_text_file, save_bytes_file])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
