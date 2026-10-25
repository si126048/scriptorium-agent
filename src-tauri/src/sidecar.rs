use tauri::{AppHandle, Manager};
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandEvent;
use tauri_plugin_store::StoreExt;

const STORE_PATH: &str = "settings.json";
const API_KEY_FIELD: &str = "dashscope_api_key";
const EXTERNAL_SERVICE_FIELD: &str = "research_service_url";

pub async fn start_sidecar(app: &AppHandle) {
    // External research mode connects from the workbench and does not start a legacy writer.
    let external_mode = app.store(STORE_PATH).ok()
        .and_then(|s| s.get(EXTERNAL_SERVICE_FIELD))
        .and_then(|v| v.as_str().map(String::from))
        .filter(|url| url.starts_with("http://") || url.starts_with("https://"));
    if external_mode.is_some() {
        return;
    }
    if std::env::var("SCRIPTORIUM_RUNTIME").unwrap_or_default() != "sqlite" {
        // Installation and progress belong to the workbench gate: it shows download/startup
        // state and reports failures. Here we only bring up an already installed runtime.
        let root = std::env::var_os("LOCALAPPDATA").map(std::path::PathBuf::from)
            .map(|base| base.join("Scriptorium").join("research"));
        match root.filter(|dir| dir.join("installation.json").exists()) {
            Some(dir) => {
                if let Ok(command) = app.shell().sidecar("scriptorium-backend") {
                    let root = dir.to_string_lossy().into_owned();
                    if let Err(error) = command.args(["local-runtime", "start", "--root", &root]).spawn() {
                        eprintln!("[research] cannot start local services: {error}");
                    }
                } else {
                    eprintln!("[research] development mode: start the unified research service explicitly");
                }
            }
            None => eprintln!("[research] no local runtime yet; the workbench offers one-click setup"),
        }
        return;
    }
    let data_dir = Manager::path(app).app_data_dir().expect("failed to get app_data_dir");
    let db_path = data_dir.join("lacan.db");
    let storage_path = data_dir.join("storage");

    std::fs::create_dir_all(&storage_path).ok();

    let dashscope_key = app
        .store(STORE_PATH)
        .ok()
        .and_then(|s| s.get(API_KEY_FIELD))
        .and_then(|v| v.as_str().map(String::from))
        .unwrap_or_default();

    let api_key_state = app.state::<crate::commands::ApiKeyState>();
    *api_key_state.dashscope.write().unwrap() = if dashscope_key.is_empty() {
        None
    } else {
        Some(dashscope_key.clone())
    };

    let sidecar = match app.shell().sidecar("scriptorium-backend") {
        Ok(cmd) => cmd,
        Err(e) => {
            eprintln!("[sidecar] not available (dev mode?): {}", e);
            eprintln!("[sidecar] run backend manually: uvicorn scriptorium.api:app --host 127.0.0.1 --port 8000");
            return;
        }
    };

    let sidecar = sidecar.envs(vec![
        ("LACAN_DB_PATH".to_string(), db_path.to_string_lossy().into_owned()),
        ("LACAN_STORAGE_PATH".to_string(), storage_path.to_string_lossy().into_owned()),
        ("DASHSCOPE_API_KEY".to_string(), dashscope_key),
        ("SCRIPTORIUM_PORT".to_string(), "8000".to_string()),
        ("LACAN_API_KEY".to_string(), String::new()),
    ]);

    let (mut rx, _child) = match sidecar.spawn() {
        Ok(result) => result,
        Err(e) => {
            eprintln!("[sidecar] failed to spawn: {}", e);
            return;
        }
    };

    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    println!("[backend] {}", String::from_utf8_lossy(&line));
                }
                CommandEvent::Stderr(line) => {
                    eprintln!("[backend] {}", String::from_utf8_lossy(&line));
                }
                CommandEvent::Error(err) => {
                    eprintln!("[backend] error: {}", err);
                }
                CommandEvent::Terminated(payload) => {
                    eprintln!("[backend] terminated: {:?}", payload);
                    break;
                }
                _ => {}
            }
        }
    });
}
