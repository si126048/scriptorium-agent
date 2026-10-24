use tauri::{Manager, State};
use std::sync::RwLock;
use tauri_plugin_store::StoreExt;

const STORE_PATH: &str = "settings.json";
const API_KEY_FIELD: &str = "dashscope_api_key";

pub struct ApiKeyState {
    pub dashscope: RwLock<Option<String>>,
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
pub async fn get_research_connection(app: tauri::AppHandle) -> Result<serde_json::Value, String> {
    use tauri_plugin_shell::ShellExt;
    if let Some(value) = app.store(STORE_PATH).map_err(|_| "settings unavailable")?.get("research_service_url") {
        if let Some(url) = value.as_str() {
            if !url.is_empty() { return Ok(serde_json::json!({"url":url,"api_key":""})); }
        }
    }
    let command = app.shell().sidecar("hermeneut-backend").map_err(|_| "research backend unavailable")?;
    let result = command.args(["local-runtime", "connection"]).output().await.map_err(|_| "research services not ready")?;
    if !result.status.success() { return Err("research services not installed yet".to_string()); }
    serde_json::from_slice(&result.stdout).map_err(|_| "invalid local service connection".to_string())
}
