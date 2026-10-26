//! Read the current user's connection without spawning the Python application.
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::path::Path;

fn credential_target(path: &str) -> String {
    let normalized = path.strip_prefix(r"\\?\").unwrap_or(path).to_lowercase();
    let hash = format!("{:x}", Sha256::digest(normalized.as_bytes()));
    format!("Scriptorium/local/{}", &hash[..24])
}

fn connection(installation: &Value, credential: &Value) -> Result<Value, String> {
    let port = installation["api_port"].as_u64().filter(|p| *p > 0 && *p <= 65535)
        .ok_or("LOCAL_SERVICE_PORT_INVALID")?;
    let key = credential["api_key"].as_str().filter(|key| !key.is_empty())
        .ok_or("LOCAL_CREDENTIALS_MISSING_REPAIR_REQUIRED")?;
    Ok(json!({"url":format!("http://127.0.0.1:{port}"), "api_key":key,
        "search":installation["search"].as_bool().unwrap_or(true)}))
}

#[cfg(target_os = "windows")]
pub fn load(root: &Path) -> Result<Value, String> {
    use windows_sys::Win32::Security::Credentials::{CredReadW, CredFree, CREDENTIALW, CRED_TYPE_GENERIC};
    let text = std::fs::read_to_string(root.join("installation.json"))
        .map_err(|_| "LOCAL_SERVICES_NOT_INSTALLED")?;
    let installation: Value = serde_json::from_str(&text).map_err(|_| "LOCAL_INSTALLATION_INVALID")?;
    let path = std::fs::canonicalize(root).map_err(|_| "LOCAL_RUNTIME_ROOT_INVALID")?;
    let target = credential_target(&path.to_string_lossy());
    let wide: Vec<u16> = target.encode_utf16().chain(std::iter::once(0)).collect();
    let mut pointer: *mut CREDENTIALW = std::ptr::null_mut();
    unsafe {
        if CredReadW(wide.as_ptr(), CRED_TYPE_GENERIC, 0, &mut pointer) == 0 || pointer.is_null() {
            return Err("LOCAL_CREDENTIALS_MISSING_REPAIR_REQUIRED".into());
        }
        let parsed = if (*pointer).CredentialBlob.is_null() || (*pointer).CredentialBlobSize > 1_048_576 {
            Err("LOCAL_CREDENTIALS_INVALID".to_string())
        } else {
            let bytes = std::slice::from_raw_parts((*pointer).CredentialBlob, (*pointer).CredentialBlobSize as usize);
            serde_json::from_slice::<Value>(bytes).map_err(|_| "LOCAL_CREDENTIALS_INVALID".to_string())
        };
        CredFree(pointer.cast());
        connection(&installation, &parsed?)
    }
}

#[cfg(not(target_os = "windows"))]
pub fn load(_root: &Path) -> Result<Value, String> {
    Err("WINDOWS_CREDENTIAL_MANAGER_REQUIRED".into())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn canonical_windows_prefix_and_case_do_not_change_identity() {
        assert_eq!(credential_target(r"\\?\C:\Users\Example\AppData\Local\Scriptorium\research"),
            credential_target(r"c:\users\example\appdata\local\scriptorium\research"));
    }
    #[test]
    fn returns_only_connection_fields_and_rejects_invalid_port() {
        let secret = json!({"api_key":"test-key", "database":"private", "elastic":"private"});
        let value = connection(&json!({"api_port":8010,"search":false}), &secret).unwrap();
        assert_eq!(value["url"], "http://127.0.0.1:8010");
        assert_eq!(value["search"], false);
        assert!(value.get("database").is_none());
        assert!(connection(&json!({"api_port":0}), &secret).is_err());
    }
    #[test]
    #[ignore = "requires the current Windows user's installed runtime"]
    fn reads_installed_connection_without_a_child_process() {
        let root = std::path::PathBuf::from(std::env::var_os("LOCALAPPDATA").unwrap())
            .join("Scriptorium").join("research");
        let value = load(&root).unwrap();
        assert!(value["url"].as_str().unwrap().starts_with("http://127.0.0.1:"));
        assert!(!value["api_key"].as_str().unwrap().is_empty());
    }
}
