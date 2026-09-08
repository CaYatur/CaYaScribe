use std::net::TcpListener;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use rand::RngCore;

pub struct Sidecar {
    pub port: u16,
    pub token: String,
    child: Mutex<Option<Child>>,
}

fn free_port() -> u16 {
    TcpListener::bind("127.0.0.1:0")
        .ok()
        .and_then(|l| l.local_addr().ok())
        .map(|a| a.port())
        .unwrap_or(8765)
}

fn token() -> String {
    let mut buf = [0u8; 32];
    rand::thread_rng().fill_bytes(&mut buf);
    hex::encode(buf)
}

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../..")
}

fn python_exe() -> PathBuf {
    let root = repo_root();
    let venv = root.join("sidecar/python/.venv/Scripts/python.exe");
    if venv.is_file() {
        return venv;
    }
    let data = std::env::var("LOCALAPPDATA").unwrap_or_default();
    let embedded = PathBuf::from(data).join("CaYaScribe/runtime/python/python.exe");
    if embedded.is_file() {
        return embedded;
    }
    PathBuf::from("python")
}

impl Sidecar {
    pub fn spawn() -> Result<Self, String> {
        let port = free_port();
        let token = token();
        let py = python_exe();
        let sidecar_dir = repo_root().join("sidecar/python");
        let data = PathBuf::from(std::env::var("LOCALAPPDATA").unwrap_or_else(|_| ".".into()))
            .join("CaYaScribe");
        let mut cmd = Command::new(&py);
        cmd.args([
            "-m",
            "cayascribe.server",
            "--host",
            "127.0.0.1",
            "--port",
            &port.to_string(),
        ])
        .current_dir(&sidecar_dir)
        .env("CAYA_TOKEN", &token)
        .env("CAYA_PORT", port.to_string())
        .env("CAYA_DATA_DIR", &data)
        .env("PYTHONPATH", &sidecar_dir)
        .env("HF_HUB_OFFLINE", "1")
        .env("TRANSFORMERS_OFFLINE", "1")
        .env("HF_HUB_DISABLE_TELEMETRY", "1")
        .env("PYANNOTE_METRICS_ENABLED", "0")
        .stdin(Stdio::null())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x08000000;
            if !cfg!(debug_assertions) {
                cmd.creation_flags(CREATE_NO_WINDOW);
            }
        }
        let child = cmd
            .spawn()
            .map_err(|e| format!("sidecar spawn failed ({:?}): {e}", py))?;
        let url = format!("http://127.0.0.1:{port}/v1/health");
        let deadline = Instant::now() + Duration::from_secs(30);
        let mut ok = false;
        while Instant::now() < deadline {
            if let Ok(resp) = ureq::get(&url).timeout(Duration::from_secs(1)).call() {
                if resp.status() == 200 {
                    ok = true;
                    break;
                }
            }
            thread::sleep(Duration::from_millis(200));
        }
        if !ok {
            return Err("sidecar health timeout".into());
        }
        Ok(Self {
            port,
            token,
            child: Mutex::new(Some(child)),
        })
    }

    pub fn shutdown(&self) {
        if let Ok(mut g) = self.child.lock() {
            if let Some(mut c) = g.take() {
                let _ = c.kill();
                let _ = c.wait();
            }
        }
    }
}

impl Drop for Sidecar {
    fn drop(&mut self) {
        self.shutdown();
    }
}
