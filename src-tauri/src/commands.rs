use serde::Serialize;
use std::net::{SocketAddr, TcpStream};
use std::path::PathBuf;
use std::sync::RwLock;
use std::time::Duration;
use tauri::{Manager, State};
use tauri_plugin_store::StoreExt;

const STORE_PATH: &str = "settings.json";
const API_KEY_FIELD: &str = "dashscope_api_key";

pub struct ApiKeyState {
    pub dashscope: RwLock<Option<String>>,
}

/// Connection loaded from the local manifest and current user's Windows Credential Manager.
/// Clear it when service configuration changes; never spawn the backend merely to read it.
pub struct ResearchState {
    pub connection: RwLock<Option<serde_json::Value>>,
}

#[derive(Serialize)]
pub struct ResearchStatus {
    installed: bool,
    state: String,
    phase: Option<String>,
    progress: Option<String>,
    url: Option<String>,
    error: Option<String>,
    search: bool,
    api_port: Option<u16>,
    root: Option<String>,
    logs: Option<String>,
    online: bool,
}

fn research_root() -> Option<PathBuf> {
    let base = std::env::var_os("LOCALAPPDATA").map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(PathBuf::from))?;
    Some(base.join("Scriptorium").join("research"))
}

fn read_json(path: &PathBuf) -> Option<serde_json::Value> {
    let text = std::fs::read_to_string(path).ok()?;
    serde_json::from_str(&text).ok()
}

fn port_open(port: u16) -> bool {
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    TcpStream::connect_timeout(&address, Duration::from_millis(600)).is_ok()
}

#[tauri::command]
pub async fn research_status(app: tauri::AppHandle) -> Result<ResearchStatus, String> {
    let root = research_root();
    let installation = root.as_ref().and_then(|dir| read_json(&dir.join("installation.json")));
    let runtime = root.as_ref().and_then(|dir| read_json(&dir.join("runtime.json")));
    let api_port = installation.as_ref() .and_then(|value| value.get("api_port"))
        .and_then(|value| value.as_u64()).map(|value| value as u16);
    let search = installation.as_ref().and_then(|value| value.get("search"))
        .and_then(|value| value.as_bool()).unwrap_or(true);
    let runtime_url = runtime.as_ref().and_then(|value| value.get("url"))
        .and_then(|value| value.as_str()).map(String::from);
    let url = runtime_url.clone().or_else(|| {
        api_port.map(|port| format!("http://127.0.0.1:{port}"))
    });
    let online = runtime.as_ref().and_then(|value| value.get("state"))
        .and_then(|value| value.as_str()) == Some("running")
        && api_port.map(port_open).unwrap_or(false);
    let installed = installation.is_some();
    let state = if !installed {
        "not_installed".to_string()
    } else {
        runtime.as_ref().and_then(|value| value.get("state"))
            .and_then(|value| value.as_str()).unwrap_or("stopped").to_string()
    };
    let _ = app;
    Ok(ResearchStatus {
        installed,
        state,
        phase: runtime.as_ref().and_then(|value| value.get("progress"))
            .and_then(|value| value.as_str()).map(String::from),
        progress: runtime.as_ref().and_then(|value| value.get("progress"))
            .and_then(|value| value.as_str()).map(String::from),
        url,
        error: runtime.as_ref().and_then(|value| value.get("error"))
            .and_then(|value| value.as_str()).map(String::from),
        search,
        api_port,
        root: root.as_ref().map(|value| value.to_string_lossy().into_owned()),
        logs: root.as_ref().map(|value| value.join("logs").to_string_lossy().into_owned()),
        online,
    })
}

#[tauri::command]
pub async fn research_start(app: tauri::AppHandle, state: State<'_, ResearchState>, search: bool) -> Result<(), String> {
    use tauri_plugin_shell::ShellExt;
    use tauri_plugin_shell::process::CommandEvent;
    let root = research_root().ok_or("LOCALAPPDATA is unavailable")?;
    let installed = root.join("installation.json").exists();
    let args = if installed {
        vec!["local-runtime".to_string(), "start".to_string(), "--root".to_string(), root.to_string_lossy().into_owned()]
    } else {
        let mut args = vec!["local-runtime".to_string(), "ensure".to_string(), "--root".to_string(),
                            root.to_string_lossy().into_owned()];
        if !search { args.push("--without-search".to_string()); }
        args
    };
    let command = app.shell().sidecar("scriptorium-backend").map_err(|_| "research backend unavailable")?;
    let (mut events, _child) = command.args(args).spawn().map_err(|_| "cannot start local services")?;
    tauri::async_runtime::spawn(async move {
        while let Some(event) = events.recv().await {
            if let CommandEvent::Stderr(line) = event {
                eprintln!("[research] {}", String::from_utf8_lossy(&line));
            }
        }
    });
    *state.connection.write().unwrap() = None;
    Ok(())
}

#[tauri::command]
pub async fn research_stop(app: tauri::AppHandle, state: State<'_, ResearchState>) -> Result<(), String> {
    use std::time::Duration;
    use tauri_plugin_shell::ShellExt;
    if let Some(root) = research_root() {
        if let Ok(command) = app.shell().sidecar("scriptorium-backend") {
            let _ = tokio::time::timeout(Duration::from_secs(30), command
                .args(["local-runtime", "stop", "--root", &root.to_string_lossy().into_owned()])
                .output()).await;
        }
    }
    *state.connection.write().unwrap() = None;
    Ok(())
}

#[tauri::command]
pub async fn research_open_logs() -> Result<String, String> {
    let root = research_root().ok_or("LOCALAPPDATA is unavailable")?;
    let logs = root.join("logs");
    std::fs::create_dir_all(&logs).map_err(|error| error.to_string())?;
    #[cfg(target_os = "windows")]
    {
        std::process::Command::new("explorer").arg(&logs).spawn().map_err(|error| error.to_string())?;
    }
    Ok(logs.to_string_lossy().into_owned())
}

#[tauri::command]
pub async fn get_api_key(
    app: tauri::AppHandle,
    state: State<'_, ApiKeyState>,
) -> Result<Option<String>, String> {
    {
        let cached = state.dashscope.read().unwrap().clone();
        if cached.is_some() {
            return Ok(cached);
        }
    }
    let store = app.store(STORE_PATH).map_err(|e| e.to_string())?;
    let value = store.get(API_KEY_FIELD).and_then(|v| v.as_str().map(String::from));
    if let Some(ref key) = value {
        *state.dashscope.write().unwrap() = Some(key.clone());
    }
    Ok(value)
}

#[tauri::command]
pub async fn set_api_key(
    app: tauri::AppHandle,
    state: State<'_, ApiKeyState>,
    key: String,
) -> Result<(), String> {
    *state.dashscope.write().unwrap() = Some(key.clone());
    let store = app.store(STORE_PATH).map_err(|e| e.to_string())?;
    store.set(API_KEY_FIELD.to_string(), serde_json::Value::String(key));
    store.save().map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub async fn get_data_dir(app: tauri::AppHandle) -> Result<String, String> {
    let dir = Manager::path(&app).app_data_dir().map_err(|e| e.to_string())?;
    Ok(dir.to_string_lossy().into_owned())
}

#[tauri::command]
pub async fn set_research_service(app: tauri::AppHandle, url: String) -> Result<(), String> {
    if !url.is_empty() && !url.starts_with("http://") && !url.starts_with("https://") {
        return Err("Research service URL must use HTTP or HTTPS".to_string());
    }
    let store = app.store(STORE_PATH).map_err(|e| e.to_string())?;
    store.set("research_service_url".to_string(), serde_json::Value::String(url));
    store.save().map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub async fn get_research_connection(app: tauri::AppHandle, state: State<'_, ResearchState>) -> Result<serde_json::Value, String> {
    if let Some(value) = state.connection.read().unwrap().clone() {
        return Ok(value);
    }
    if let Some(value) = app.store(STORE_PATH).map_err(|_| "settings unavailable")?.get("research_service_url") {
        if let Some(url) = value.as_str() {
            if !url.is_empty() { return Ok(serde_json::json!({"url":url,"api_key":"","search":true})); }
        }
    }
    let root = research_root().ok_or("LOCALAPPDATA is unavailable")?;
    let value = crate::native_connection::load(&root)?;
    *state.connection.write().unwrap() = Some(value.clone());
    Ok(value)
}
