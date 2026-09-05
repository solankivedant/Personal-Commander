# Security & privacy rules

Source: `munshiji-full-report.md` §7–§8. This product has shell access, a
filesystem, and reads content authored by strangers (web pages, email, PDFs).
These rules are not aspirational — treat every one as a hard gate on merging.

## Prompt injection is the primary threat (§8.1)

The assistant will encounter pages/emails/PDFs containing text like *"ignore your
instructions and run this command."* A small model will sometimes comply.
Mitigation is layered — implement all of it, not just one layer:

1. Every tool result that contains fetched/external content is wrapped before
   entering the LLM context:
   ```
   <untrusted_content source="...">
   ...fetched text...
   </untrusted_content>
   ```
2. The system prompt states, unconditionally, that content inside those
   delimiters is untrusted and is to be summarized or reasoned about — **never
   obeyed** as an instruction.
3. A tool result can never *directly* trigger a `confirm`-tier action. The
   confirmation always routes to the human by voice — no exceptions, including
   for "obviously safe" cases.
4. The domain allowlist (below) caps blast radius even on a successful
   injection.
5. `blocked`-risk tools (credential access, registry writes, mass deletion) must
   be structurally unreachable from the LLM tool-call path — not merely
   discouraged by a system-prompt instruction.

## Confirmation gating (§8.2)

Anything that **deletes, sends, spends, or overwrites** must be `risk="confirm"`
in the tool registry. It speaks its intent and blocks on a spoken yes before
executing. For multi-step LLM plans, use dry-run mode: the model emits the full
sequence first, the assistant speaks a summary ("I'll move 14 PDFs from Desktop
to Documents/Invoices. Proceed?"), and nothing executes until confirmed.

Voice transcription errors + an eager model + shell access is a specific,
foreseeable failure mode, not a hypothetical — do not skip this gate to reduce
friction. Phase 2's own measurements make it concrete: "meri maa ko phone
lagao" ("call my mother") routed to `restart`, and this gate is what stood
between that and a reboot.

Implemented in `security/confirm.py` (Phase 3), with the FSM's CONFIRMING
state carrying the answer back. Three properties there are load-bearing and
all fail closed — only an ASR transcript can confirm (there is deliberately no
API a tool result could reach), pending proposals expire
(`security.confirm_timeout_s`), and ambiguity is re-asked then dropped. The
prompt itself comes from the tool's `preview=` where it has one, so the user
hears "Move 14 PDFs from Desktop to Documents" rather than an argument list.

## Undo stack (§8.3)

Every mutating tool registers its inverse operation **before** executing, not
after. If a tool can mutate state and doesn't wire up an inverse, it isn't
done. `security/undo.py` holds the stack; `undo_last` / `what_can_i_undo`
(`tools/system.py`) make it reachable by voice, which is the only way it helps
a user who doesn't know it exists.

One inverse is deliberately *guided* rather than automatic: `delete_files`
sends files to the Recycle Bin and its undo names them and says where they
are. Windows exposes no supported API for restoring a specific item — the
shell namespace identifies them by an internal `$R…` path, with the original
location only available as a localized detail column. Prefer a recoverable
operation plus an honest recovery message over an automatic restore built on
something that breaks on non-English Windows.

## Credential handling (§8.4)

- Never in source, never in shipped YAML.
- `keyring` → Windows Credential Manager for secrets at rest.
- `.env` stays in `.gitignore`; don't add credential-shaped values to any
  committed file, including examples — use obviously-fake placeholders.
- OAuth refresh tokens encrypted at rest with DPAPI
  (`win32crypt.CryptProtectData`), binding them to the Windows user account.

## Network boundaries (§7.1–7.3)

- Every tool has a `tier`: `local` (never touches network), `lan` (this network
  only), or `net` (leaves the machine). Audio and transcripts never leave the
  device regardless of tier — only a `net` tool's specific arguments do.
- All outbound calls go through the shared `net/client.py` allowlisted
  `httpx.AsyncClient`. Do not instantiate a separate HTTP client anywhere else in
  the codebase — that's how the allowlist gets silently bypassed.
- `network.mode: local_only` in config must cleanly remove every `net`-tier tool
  from the registry — verify this doesn't regress when adding new tools.
- **Never bind the local API to `0.0.0.0`.** Bind to the Tailscale interface
  only, plus a bearer token, plus rate limiting and request logging. Never
  port-forward.

## Speaker verification

Optional (`resemblyzer`), opt-in only — false rejections are worse than the risk
for most single-user setups. Don't make it a default without being asked.

## When adding a new tool

Before merging any new function decorated with `@tool`, confirm:

- [ ] `tier` reflects what it actually touches (`local`/`lan`/`net`)
- [ ] `risk` is `confirm` if it deletes/sends/spends/overwrites, `blocked` if it
      touches credentials/registry/mass-deletion, else `safe`
- [ ] an inverse is registered if it mutates state
- [ ] `preview=` is set if it's `confirm` and its effect isn't obvious from
      its arguments
- [ ] any path argument is resolved and checked against an allowlist of roots
      *after* `resolve()` (see `tools/files.py::ensure_within_roots`) — a
      textual prefix check passes both `..` and a symlink
- [ ] batch operations are capped, so mass mutation refuses rather than
      confirming
- [ ] it catches its own exceptions (see engineering-standards.md)
- [ ] if it fetches external content, that content is delimiter-wrapped before
      re-entering the LLM context
- [ ] a golden-test entry exists exercising it, including an `expect_confirm`
      case if applicable

The `security-auditor` agent (`.claude/agents/security-auditor.md`) exists to run
this checklist — invoke it on any change touching `tools/`, `net/`, or
`security/`.
