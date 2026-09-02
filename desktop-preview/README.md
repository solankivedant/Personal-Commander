# Munshiji — desktop preview shell

A [Tauri](https://tauri.app) wrapper around the Control Center UI mockup
(`dist/index.html`) so it can be built into a real, installable Windows app
(an NSIS `.exe` installer). Windows-only, deliberately: the real Munshiji
product only ever targets Windows (Office COM automation has no macOS/Linux
equivalent per `docs/ARCHITECTURE.md`), so a preview build for other platforms
would advertise support that will never exist.

**This is not the Munshiji product.** It's a static HTML/CSS/JS UI preview with
no Rust ↔ frontend bridge, no calls into `src/munshiji/`, and no network
access. It exists so people can download something and see the intended shape
of the app while the real engine (router, tools, voice loop) is built out
phase by phase — see `../docs/ROADMAP.md`. The real shipping installer, once
the engine exists, is the PyInstaller + Inno Setup pipeline under `../installer/`
and `../scripts/package.py` (§8 of `munshiji-full-report.md`), not this Tauri
shell — do not confuse the two.

## Why Tauri here, PyInstaller there

The actual assistant is a Python process (ASR/TTS/LLM/COM automation) with no
reason to ship a second GUI runtime. This preview shell is a separate,
disposable artifact: Tauri gives a small (~10 MB) installer for a page that's
otherwise just static assets, which matters if this preview is meant to be
freely downloadable. It does not imply the real app will be rewritten in Rust.

## Building it yourself

Prerequisites: [Rust](https://rustup.rs), Node.js 18+, and the WebView2
runtime (present by default on Windows 11 and most updated Windows 10
installs — see [Tauri's Windows setup guide](https://tauri.app/start/prerequisites/)
if `tauri dev` complains about it).

```bash
cd desktop-preview
npm install

# Generate icon.ico / remaining PNG sizes from the source mark (only
# src-tauri/icons/{32x32,128x128,128x128@2x}.png and icon.png are committed —
# icon.ico isn't, since it needs the Tauri CLI to produce):
npm run icon

npm run dev      # opens the preview in a native window
npm run build    # produces an NSIS installer under src-tauri/target/release/bundle/nsis/
```

## Testing the UI in a browser, no Rust required

```bash
cd desktop-preview
npm install
npm run web      # http://localhost:5180 (override with PORT=xxxx)
```

`serve.mjs` is a zero-dependency Node static server for `dist/` — the same
file the Tauri window loads, just opened as a normal browser tab. Use this
for quick UI iteration; use `npm run dev` (below) when you need to check how
it actually looks inside a native window.

## Getting a build without installing Rust

Push a tag matching `desktop-preview-v*` (e.g. `git tag desktop-preview-v0.1.0
&& git push origin desktop-preview-v0.1.0`) and
`.github/workflows/desktop-preview-release.yml` builds a Windows installer in
CI and attaches it to a GitHub Release — that Release page is what the
landing page's download button links to.

## Updating the UI

`dist/index.html` is a hand-copy of the Claude-artifact Control Center design,
with the Claude-runtime frame script stripped out and a preview-build ribbon
added at the top. If the artifact is revised, re-sync the `<style>`/body/
`<script>` content here (keep the ribbon and the `<title>`).
