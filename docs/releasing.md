# Releasing CaYaScribe

Default docs language is English. Turkish: [README.tr.md](../README.tr.md).

## Cut a GitHub Release

1. Bump `version` in:
   - `apps/desktop/src-tauri/tauri.conf.json`
   - `apps/desktop/src-tauri/Cargo.toml`
   - `apps/desktop/package.json`
   - `package.json` (root)
   - `sidecar/python/pyproject.toml`
2. Commit on `main`.
3. Tag and push:

```powershell
git tag v0.1.0
git push origin v0.1.0
```

The [release workflow](../.github/workflows/release.yml) runs on `v*` tags:

- Builds the Windows NSIS installer (`CaYaScribe_x.y.z_x64-setup.exe`)
- Creates a **published** GitHub Release (not a draft or pre-release; marked Latest)
- English notes; Turkish blurb in the body
- Uploads the installer as a release asset

Unsigned builds will show a SmartScreen warning. Code signing is a later step.

v0.1 installers ship the UI. Transcription still needs the Python sidecar from a development checkout until the embeddable CPython runtime is bundled.
