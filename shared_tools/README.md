# AIMAOS Shared Tools

Tools in this directory are written once and registered directly (same file)
into as many agents' `capabilities.yaml` as need them — the pattern
`browse_files.py` already established for file research. Paths are recorded
office-root-relative (e.g. `shared_tools/browse_files.py`) so a checkout works
anywhere; `core/delegation.load_capabilities` resolves them at load time. Each
file is a self-contained `TOOL_DEFINITION` + `execute()` module; no shared
tool imports another agent's code.

`tool_catalog.yaml` is the central index of everything an office agent might
plausibly need, whether or not it's built yet. Browse it with
`list_tool_catalog.py`, install an entry onto any agent with
`install_catalog_tool.py` (both already wired into Zoe's `tool_engineering`
domain and Rae's `agent_making` domain) — that's the fast path for adding a
new capability without hand-authoring a schema.

## What's implemented right now

“Implemented” means a module has an executable body; it does not mean public-beta policy permits the call. `security.allow_network_tools`, `security.allow_external_mutations`, `security.allow_shell_tools`, developer mode, path checks, and optional dependencies are enforced separately.

| Tool | Needs | Module behavior |
|---|---|---|
| `web_fetch` | network policy enabled | performs HTTP read when explicitly enabled |
| `calculator` | nothing | yes |
| `unit_converter` | nothing | yes |
| `timezone_convert` | nothing | yes |
| `rss_feed_read` | network policy enabled | reads a feed when explicitly enabled |
| `web_search` | network policy; optional provider key | best-effort fallback can be anti-bot gated |
| `google_calendar` | network/external-mutation policy plus access token | not configured by default |
| `text_to_speech` | local `espeak-ng`/`espeak`/`flite`, or `TTS_API_URL` | no |
| `speech_to_text` | `ffmpeg` + (`WHISPER_CPP_BIN`+`WHISPER_CPP_MODEL`, or `STT_API_URL`) | no |
| `browse_files` | nothing | yes |
| `draft_client_request` | nothing | yes |
| `assemble_pdf` | `reportlab` (+ `pypdf` to merge) | after `pip install reportlab` |
| `edit_image` | `pillow` | after `pip install pillow` |
| `read_scanned_document` | `pytesseract` + the `tesseract` binary | no |
| `transcribe_audio` | same backends as `speech_to_text` | no |

Three more modules here are office utilities rather than agent tools:
`ingest_ssd_drive.py` (CLI drive-ingestion entry point), plus
`list_tool_catalog.py` and `install_catalog_tool.py`, which are themselves
registered as tools on Zoe and Rae.

Everything else in the catalog (`status: scaffold`) is a fully-specified
schema with no code yet — `install_catalog_tool.py` generates a stub module
you (or Zoe) fill in, same as `design_tool_subagent.py` does for a
hand-designed tool.

## Activating each integration

**Google Calendar** — set `GOOGLE_CALENDAR_ACCESS_TOKEN` to an OAuth2
access token scoped to `https://www.googleapis.com/auth/calendar` (or
`.events`). The quickest way to get one for testing: Google's
[OAuth 2.0 Playground](https://developers.google.com/oauthplayground),
authorize the Calendar API v3 scope, exchange for an access token, and
export it. Access tokens expire in ~1 hour — for anything beyond testing,
run your own small refresh script against your OAuth client's refresh token
and have it update the env var on a cron; that flow is intentionally out of
scope for the tool itself. Optionally set `GOOGLE_CALENDAR_ID` (defaults to
`primary`).

**Web search** — after the operator enables network tools, a no-key DuckDuckGo scrape may work, but
that path can fail (DuckDuckGo shows an anti-bot challenge to non-browser
traffic unpredictably). For reliable results, get a free key from
[Brave Search API](https://brave.com/search/api/) (`BRAVE_SEARCH_API_KEY`)
or [SerpApi](https://serpapi.com/) (`SERPAPI_KEY`) — either is checked
first automatically.

**Text-to-speech** — easiest path is `sudo apt install espeak-ng`, which
`text_to_speech.py` picks up automatically with no env vars. For higher
quality, set `TTS_API_URL` (and `TTS_API_KEY` if needed) to any provider
that accepts `{"text": ..., "voice": ...}` and returns raw audio bytes.

**Speech-to-text** — build [whisper.cpp](https://github.com/ggerganov/whisper.cpp)
(CPU-friendly, runs fully offline — a good fit for this box), point
`WHISPER_CPP_BIN` at the compiled binary and `WHISPER_CPP_MODEL` at a
downloaded `ggml-*.bin` model. `ffmpeg` (already installed) handles format
normalization. Alternatively set `STT_API_URL` (and `STT_API_KEY`) to a
hosted transcription endpoint that accepts a multipart file upload.

Set integration credentials as environment variables for the daemon process.
Do not store them in tracked files or command output. Enabling a hosted speech,
search, calendar, or other provider changes the data-flow boundary described in
`PRIVACY.md` and must be reviewed separately.

## Adding more from the catalog

From Zoe or Rae's turn, e.g.:

```
list_tool_catalog(action="search", query="invoice")
install_catalog_tool(target_agent="Marley", tool_name="create_invoice")
```

For an `implemented` entry this registers the existing module immediately.
For a `scaffold` entry it writes a stub into the target agent's own
`tools/` dir and registers it — the tool will report
"NOT YET IMPLEMENTED" until its `execute()` body is written, or you pass
`command_template` to wrap a local shell command directly (same mechanism
`design_tool_subagent.py` uses).

Catalog installation, tool design, and shell-backed tools are developer operations and are disabled by default. Review generated code before enabling it.

## Adding something *not* in the catalog

Use `design_tool_subagent.py` directly (Zoe's `tool_engineering` domain) —
it takes a full schema instead of a catalog lookup, for anything genuinely
new. Consider adding it to `tool_catalog.yaml` afterward if it's likely to
be useful to more than one agent.
