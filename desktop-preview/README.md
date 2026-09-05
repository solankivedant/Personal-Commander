# Munshiji — desktop Control Center

`dist/index.html` is the Control Center UI. It is served two ways, and the
difference matters:

| How you open it | What it can do |
|---|---|
| **From the engine** — `uv run munshiji --no-voice` (or `uv run munshiji`), then <http://127.0.0.1:5180> | Real. Commands run on this machine. |
| From the [Tauri](https://tauri.app) shell here, or `npm run web` | Interface only. It probes for the engine and sends you to the served copy if it finds one; otherwise it says so and stays inert. |

**Every reply you see in the served copy came from a real tool.** Clicking
an example posts the utterance to `src/munshiji/ui/server.py`, which routes
it through the same cascade a spoken command takes
(`tools/dispatch.py` → `router/` → the tool), and shows what the tool
returned. The confirmation buttons carry your answer to
`security/confirm.py`, which is the only thing that can approve a delete or
a move — there is no "approved" flag the page can send.

Until 2026-09 this page replayed recorded strings on a timer. It doesn't any
more: with no engine running it renders the interface and refuses to
pretend, which is why the ribbon and the bar at the bottom both say the
engine is offline.

## Running it

```bash
# From the repo root. First start takes ~35s: the multilingual encoder loads.
uv run munshiji --no-voice          # typed commands only — no mic, no models
uv run munshiji                     # wake word + microphone as well
uv run munshiji --no-voice --open   # ...and open the browser for you
```

The URL printed at startup (`control_center_ready`) carries the session
token — the page is only able to act when it is served with it. The token is
minted per run, so a stale tab reconnects by reloading that URL.

What is exposed, and where it stops:

* Bound to loopback only. `src/munshiji/ui/server.py` refuses to start on any
  non-loopback host, `0.0.0.0` included. The remote/phone surface is a
  separate Phase 7 thing (`net/api.py`, Tailscale-bound) and is not this.
* Bearer token per run, plus Host and Origin checks, so a web page you happen
  to have open cannot reach the engine.
* `/command` and `/confirm` are rate limited; every request is logged, and
  every action lands in `data/audit.jsonl` the same as a spoken one.

## The Tauri shell

Windows-only, deliberately: the real product only ever targets Windows
(Office COM automation has no macOS/Linux equivalent per
`docs/ARCHITECTURE.md`), so a preview build for other platforms would
advertise support that will never exist.

The shell wraps `dist/` so the Control Center can be installed as a normal
Windows app (an NSIS `.exe`). It bundles the page without a token, so on
launch the page looks for the engine on `127.0.0.1:5180` and navigates to the
served copy. If the engine isn't running it shows the "engine isn't running"
note with the command to start it. The shell has no Rust ↔ frontend bridge
and never calls into `src/munshiji/` itself — the engine is a separate Python
process, and the page talks to it over loopback HTTP like any other client.

The shipping installer for the assistant itself is still the PyInstaller +
Inno Setup pipeline under `../installer/` and `../scripts/package.py` (§8 of
`munshiji-full-report.md`), not this Tauri shell — do not confuse the two.

### Why Tauri here, PyInstaller there

The assistant is a Python process (ASR/TTS/LLM/COM automation) with no reason
to ship a second GUI runtime. This shell is a separate, small artifact: Tauri
gives a ~10 MB installer for a page that is otherwise static assets, which
matters if it is meant to be freely downloadable. It does not imply the real
app will be rewritten in Rust.

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

npm run dev      # opens the Control Center in a native window
npm run build    # produces an NSIS installer under src-tauri/target/release/bundle/nsis/
```

## Testing the UI in a browser, no Rust required

```bash
cd desktop-preview
npm install
npm run web      # http://localhost:5181 (override with PORT=xxxx)
```

`serve.mjs` is a zero-dependency Node static server for `dist/`. It serves
the page without a token — same as the Tauri bundle — so use it for pure
layout/CSS iteration. Port 5181, not 5180: 5180 belongs to the engine
(`config/default.yaml`, `ui.control_center.port`), and taking it would stop
the real Control Center from starting.

## Publishing a downloadable installer

The website's Download button is a plain link to a GitHub permalink:

```
https://github.com/<owner>/<repo>/releases/latest/download/Munshiji-Setup-x64.exe
```

GitHub resolves `/releases/latest/` server-side to the newest published
release and streams the `.exe`, so the link never needs editing and works
with JavaScript disabled. It needs a network connection, since the file is
served from GitHub rather than bundled with the site.

To cut a release:

```bash
git tag desktop-preview-v0.1.0
git push origin desktop-preview-v0.1.0
```

`.github/workflows/desktop-preview-release.yml` then builds on
`windows-latest`, copies the versioned NSIS output to the fixed name
`Munshiji-Setup-x64.exe`, writes a `.sha256` beside it, uploads both, and
finally HEADs the public permalink so a broken release fails in CI rather
than on someone's download click. `workflow_dispatch` runs the same job for
an existing tag.

**Three things this depends on. All three will silently break the button.**

1. **The repository must be public.** Release assets on a private repo need
   an authenticated request, so the permalink returns 404 for every visitor.
   Nothing in the workflow can work around this.
2. **The release must not be a draft or a prerelease.** `/releases/latest/`
   skips both, so the workflow pins `releaseDraft: false` and
   `prerelease: false`. Do not "helpfully" mark a build as a prerelease.
3. **The asset name is a contract.** `ASSET_NAME` in the workflow and
   `ASSET_NAME` in `landing/src/release.ts` must match, and renaming it
   invalidates every download link anyone has already shared.

### Not code-signed

There is no code-signing certificate yet, so Windows SmartScreen shows
"Windows protected your PC" and users must choose **More info -> Run anyway**.
That warning costs real installs. Buying an OV/EV certificate and signing in
CI is Phase 8 work (`docs/ROADMAP.md`), tracked alongside the real installer.

### When the real installer exists

The engine ships through PyInstaller + Inno Setup (`scripts/package.py`,
`installer/`), not through this Tauri shell. Publish it under the **same**
asset name and the website, the docs and every shared link keep working with
no change - which is the reason the name is fixed rather than versioned.

## Updating the UI

`dist/index.html` started as a hand-copy of the Claude-artifact Control
Center design and has since diverged: the demo timer is gone and the page is
a real client of `ui/server.py` (`ENGINE`, `send()`, `openStream()` near the
bottom of the inline script). Re-syncing from a revised artifact means
keeping that block, the command bar, the connection note, and the
`__MUNSHIJI_SESSION_TOKEN__` placeholder the server substitutes on the way
out.
