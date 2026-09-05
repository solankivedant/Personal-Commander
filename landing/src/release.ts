/** Live release info for the Download page.
 *
 * The button itself is a plain link to GitHub's permalink:
 *
 *   /releases/latest/download/Munshiji-Setup-x64.exe
 *
 * GitHub resolves that server-side to the newest published release and
 * streams the .exe, so downloading works with the link alone and needs no
 * JavaScript at all. This module only fills in the details *around* the
 * button - version, size, release date - by asking the GitHub API.
 *
 * Those numbers were previously hardcoded ("Version 1.0.2 - 180 MB") for a
 * build that did not exist. Reading them from the release that is actually
 * published is the only way they stay true, and it means a new release
 * updates the site with no edit.
 *
 * Everything here degrades quietly: no network, rate-limited API, or no
 * release published yet all leave the button working and the metadata line
 * showing its neutral fallback. A marketing page must never break because a
 * third-party API was slow.
 */

const OWNER_REPO = "solankivedant/Personal-Commander";
const ASSET_NAME = "Munshiji-Setup-x64.exe";

/** Permalink to the newest published installer. Kept in sync by name with
 * ASSET_NAME in .github/workflows/desktop-preview-release.yml - renaming the
 * asset there breaks this link and every copy of it people have shared. */
export const DOWNLOAD_URL =
  `https://github.com/${OWNER_REPO}/releases/latest/download/${ASSET_NAME}`;

interface ReleaseAsset {
  name: string;
  size: number;
  browser_download_url: string;
}

interface Release {
  tag_name: string;
  name: string | null;
  published_at: string;
  html_url: string;
  assets: ReleaseAsset[];
}

function formatSize(bytes: number): string {
  const mb = bytes / (1024 * 1024);
  return mb >= 100 ? `${Math.round(mb)} MB` : `${mb.toFixed(1)} MB`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

/** "desktop-preview-v0.1.0" -> "0.1.0"; anything else is left alone. */
function versionFrom(tag: string): string {
  const m = /v(\d[\w.\-+]*)$/.exec(tag);
  return m?.[1] ?? tag;
}

async function fetchLatest(signal: AbortSignal): Promise<Release | null> {
  const res = await fetch(`https://api.github.com/repos/${OWNER_REPO}/releases/latest`, {
    headers: { Accept: "application/vnd.github+json" },
    signal,
  });
  // 404 is the normal answer before the first release is published, not an
  // error worth surfacing to a visitor.
  if (!res.ok) return null;
  return (await res.json()) as Release;
}

export function initDownload(): void {
  const meta = document.getElementById("releaseMeta");
  const checksum = document.getElementById("releaseChecksum");
  const buttons = document.querySelectorAll<HTMLAnchorElement>("a[data-download]");

  // Set the href from one constant so no page can drift to a stale URL.
  buttons.forEach((a) => {
    a.href = DOWNLOAD_URL;
  });

  if (!meta) return;

  // Never let a hung request hold the page's story open.
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 6000);

  fetchLatest(controller.signal)
    .then((release) => {
      if (!release) return;
      const asset =
        release.assets.find((a) => a.name === ASSET_NAME) ??
        release.assets.find((a) => a.name.endsWith(".exe"));
      if (!asset) return;

      meta.textContent =
        `Version ${versionFrom(release.tag_name)} · 64-bit · ` +
        `${formatSize(asset.size)} · Windows 10 & 11 · ${formatDate(release.published_at)}`;

      if (checksum) {
        const sha = release.assets.find((a) => a.name === `${ASSET_NAME}.sha256`);
        if (sha) {
          checksum.innerHTML =
            `SHA-256 published with this build - ` +
            `<a href="${sha.browser_download_url}" rel="noopener">verify your download</a>`;
        }
      }
    })
    .catch(() => {
      /* Offline, blocked, or rate-limited. The fallback copy already in the
         markup is accurate, so there is nothing to correct. */
    })
    .finally(() => window.clearTimeout(timeout));
}
