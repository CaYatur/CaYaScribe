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
git tag v0.1.3
git push origin v0.1.3
```

The [release workflow](../.github/workflows/release.yml) runs on `v*` tags:

- Builds an embeddable CPython sidecar (`scripts/prepare_runtime.py`)
- Builds the Windows NSIS installer (`CaYaScribe_x.y.z_x64-setup.exe`)
- Creates a **published** GitHub Release (not a draft or pre-release; marked Latest)
- English notes; Turkish blurb in the body
- Uploads the installer as a release asset

Unsigned builds will show a SmartScreen warning. Code signing is a later step.

The installer includes the local Python engine. Models are still downloaded after you consent.
