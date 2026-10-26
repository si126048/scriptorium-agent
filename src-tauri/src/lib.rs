pub mod commands;
pub mod sidecar;
mod native_connection;

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_store::Builder::new().build())
        .manage(commands::ApiKeyState {
            dashscope: std::sync::RwLock::new(None),
        })
        .manage(commands::ResearchState {
            connection: std::sync::RwLock::new(None),
        })
        .invoke_handler(tauri::generate_handler![
            commands::get_api_key,
            commands::set_api_key,
            commands::get_data_dir,
            commands::set_research_service,
            commands::get_research_connection,
            commands::research_status,
            commands::research_start,
            commands::research_stop,
            commands::research_open_logs,
        ])
        .setup(|app| {
            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                sidecar::start_sidecar(&app_handle).await;
            });
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
