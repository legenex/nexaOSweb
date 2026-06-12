// nexaOSweb desktop wrapper.
//
// The web build is loaded directly. The desktop never bundles the bearer token: it reads
// it from the OS secure store (Keychain on macOS, Credential Manager on Windows) through
// the keyring crate, and reports the API base for the current build profile. The web app
// asks for this config on startup via the get_config command.

use serde::Serialize;

const KEYRING_SERVICE: &str = "nexaosweb";
const KEYRING_ACCOUNT: &str = "desktop-bearer";

#[derive(Serialize)]
struct DesktopConfig {
    api_base: String,
    bearer: Option<String>,
}

fn api_base() -> String {
    // Dev points at the local Brain, release at the hosted Brain behind Plesk.
    if cfg!(debug_assertions) {
        "http://localhost:8847".to_string()
    } else {
        "https://nexaos.example.com/api".to_string()
    }
}

fn read_bearer() -> Option<String> {
    let entry = keyring::Entry::new(KEYRING_SERVICE, KEYRING_ACCOUNT).ok()?;
    entry.get_password().ok()
}

#[tauri::command]
fn get_config() -> DesktopConfig {
    DesktopConfig {
        api_base: api_base(),
        bearer: read_bearer(),
    }
}

#[tauri::command]
fn set_bearer(token: String) -> Result<(), String> {
    let entry = keyring::Entry::new(KEYRING_SERVICE, KEYRING_ACCOUNT).map_err(|e| e.to_string())?;
    entry.set_password(&token).map_err(|e| e.to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![get_config, set_bearer])
        .run(tauri::generate_context!())
        .expect("error while running nexaOSweb");
}
