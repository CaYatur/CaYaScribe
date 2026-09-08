use std::fs::{self, OpenOptions};
use std::net::TcpListener;
use std::path::{Path, PathBuf};
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

struct Launch {
    exe: PathBuf,
    cwd: PathBuf,
    pythonpath: Option<PathBuf>,
    manifest: Option<PathBuf>,
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

fn python_in(dir: &Path) -> Option<PathBuf> {
    let exe = dir.join("python.exe");
    if exe.is_file() {
        Some(exe)
    } else {
        None
    }
}

fn launch_from_runtime(dir: PathBuf) -> Option<Launch> {
    let exe = python_in(&dir)?;
    let manifest = dir.join("assets/manifest.json");
    Some(Launch {
        exe,
        cwd: dir,
        pythonpath: None,
        manifest: manifest.is_file().then_some(manifest),
    })
}

fn resolve_launch(resource_dir: Option<&Path>, exe_dir: Option<&Path>) -> Result<Launch, String> {
    if let Ok(override_py) = std::env::var("CAYA_PYTHON") {
        let exe = PathBuf::from(override_py);
        if exe.is_file() {
            let cwd = exe.parent().unwrap_or(Path::new(".")).to_path_buf();
            return Ok(Launch {
                exe,
                cwd,
                pythonpath: None,
                manifest: None,
            });
        }
    }

    let mut candidates: Vec<PathBuf> = Vec::new();
    if let Some(dir) = resource_dir {
        candidates.push(dir.join("runtime"));
        candidates.push(dir.to_path_buf());
    }
    if let Some(dir) = exe_dir {
        candidates.push(dir.join("runtime"));
        candidates.push(dir.join("resources/runtime"));
        candidates.push(dir.join("../resources/runtime"));
    }
    if let Ok(local) = std::env::var("LOCALAPPDATA") {
        let base = PathBuf::from(local).join("CaYaScribe");
        candidates.push(base.join("runtime"));
        candidates.push(base.join("runtime/python"));
    }
    for dir in candidates {
        if let Some(launch) = launch_from_runtime(dir) {
            return Ok(launch);
        }
    }

    let root = repo_root();
    let venv = root.join("sidecar/python/.venv/Scripts/python.exe");
    if venv.is_file() {
        let sidecar_dir = root.join("sidecar/python");
        let manifest = root.join("assets/manifest.json");
        return Ok(Launch {
            exe: venv,
            cwd: sidecar_dir.clone(),
            pythonpath: Some(sidecar_dir),
            manifest: manifest.is_file().then_some(manifest),
        });
    }

    Err(format!(
        "sidecar python not found (resource={:?} exe_dir={:?})",
        resource_dir.map(|p| p.display().to_string()),
        exe_dir.map(|p| p.display().to_string())
    ))
}

fn prepend_path(dir: &Path) -> String {
    let extra = dir.display().to_string();
    match std::env::var("PATH") {
        Ok(rest) => format!("{extra};{rest}"),
        Err(_) => extra,
    }
}

impl Sidecar {
    pub fn spawn(resource_dir: Option<PathBuf>, exe_dir: Option<PathBuf>) -> Result<Self, String> {
        let port = free_port();
        let token = token();
        let launch = resolve_launch(resource_dir.as_deref(), exe_dir.as_deref())?;
        let data = PathBuf::from(std::env::var("LOCALAPPDATA").unwrap_or_else(|_| ".".into()))
            .join("CaYaScribe");
        let logs = data.join("logs");
        let _ = fs::create_dir_all(&logs);
        let log_path = logs.join("sidecar.log");
        let log_file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&log_path)
            .map_err(|e| format!("sidecar log {}: {e}", log_path.display()))?;
        let log_err = log_file
            .try_clone()
            .map_err(|e| format!("sidecar log clone: {e}"))?;
        let mut cmd = Command::new(&launch.exe);
        cmd.args([
            "-m",
            "cayascribe.server",
            "--host",
            "127.0.0.1",
            "--port",
            &port.to_string(),
        ])
        .current_dir(&launch.cwd)
        .env("CAYA_TOKEN", &token)
        .env("CAYA_PORT", port.to_string())
        .env("CAYA_DATA_DIR", &data)
        .env("HF_HUB_OFFLINE", "1")
        .env("TRANSFORMERS_OFFLINE", "1")
        .env("HF_HUB_DISABLE_TELEMETRY", "1")
        .env("PYANNOTE_METRICS_ENABLED", "0")
        .env("PATH", prepend_path(&launch.cwd))
        .stdin(Stdio::null())
        .stdout(Stdio::from(log_file))
        .stderr(Stdio::from(log_err));
        if let Some(pp) = &launch.pythonpath {
            cmd.env("PYTHONPATH", pp);
        }
        if let Some(manifest) = &launch.manifest {
            cmd.env("CAYA_MANIFEST", manifest);
        }
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
            .map_err(|e| format!("sidecar spawn failed ({:?}): {e}", launch.exe))?;
        let url = format!("http://127.0.0.1:{port}/v1/health");
        let deadline = Instant::now() + Duration::from_secs(90);
        let mut ok = false;
        while Instant::now() < deadline {
            if let Ok(resp) = ureq::get(&url).timeout(Duration::from_secs(1)).call() {
                if resp.status() == 200 {
                    ok = true;
                    break;
                }
            }
            thread::sleep(Duration::from_millis(250));
        }
        if !ok {
            let tail = fs::read_to_string(&log_path).unwrap_or_default();
            let tail = tail.chars().rev().take(1200).collect::<String>().chars().rev().collect::<String>();
            return Err(format!(
                "sidecar health timeout. log {}: {}",
                log_path.display(),
                tail
            ));
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
