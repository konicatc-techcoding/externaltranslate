# ExternalTranslate Project Instructions

## Project Goal

Build a Windows application that:

- Captures audio from a microphone or external audio interface.
- Streams 16 kHz mono PCM16 audio to Gemini Live Translate.
- Uses `gemini-3.5-live-translate-preview` through a configurable provider adapter.
- Produces Traditional Chinese subtitles using target language code `zh-Hant`.
- Displays subtitles on a configurable web overlay.
- Integrates with vMix through its HTTP API and supports a vMix Browser Input overlay.
- Allows control of font family, font size, text color, background color, alignment, maximum subtitle lines, and line width.

## Architecture Direction

Use a local-first architecture:

1. Python 3.11 backend.
2. FastAPI REST API and WebSocket server.
3. `google-genai` for Gemini Live Translate.
4. PortAudio/`sounddevice` for initial Windows audio capture.
5. React and TypeScript frontend for the control and overlay pages.
6. A canonical `CaptionState` shared by the web overlay and vMix output.
7. Adapter boundaries for audio capture, translation providers, and output targets.
8. vMix Browser Input as the preferred fully styled overlay; GT Title `SetText` as compatibility output.

Use the official Gemini Live Translate documentation as the authoritative API source:

`https://ai.google.dev/gemini-api/docs/live-api/live-translate`

Re-check this documentation before implementing or changing Gemini integration because the model and API are preview features. Report any conflict between the documentation and the current design before changing code.

The application must provide a Traditional Chinese settings input where the user can enter the Google Gemini API key. The key may be submitted only to the loopback backend, must never be placed in frontend source, browser storage, WebSocket caption messages, URLs, or logs, and should be stored through Windows Credential Manager when the user chooses to save it. `.env` may be supported for development only. Keep non-secret settings in configuration files.

## Development Rules

- Understand the current implementation before modifying it.
- Read `BUILD.md` and `PLAN.md` before planning or implementing a version. Treat `BUILD.md` as the version delivery contract and `PLAN.md` as the staged execution and acceptance plan unless the user explicitly changes them.
- Start agent sessions from the project root so this `AGENTS.md` is loaded. Use command-specific working directories rather than moving the agent session into `backend/` or `frontend/`.
- Implement only the explicitly requested stage; do not continue to later stages without approval.
- Prefer small, focused, production-quality changes.
- Do not redesign unrelated parts of the project.
- Use configuration for model names, device selection, language codes, paths, ports, caption limits, and vMix settings; do not hard-code operational values.
- Keep audio capture callbacks non-blocking. Network operations must never run inside the capture callback.
- Use bounded queues so network slowdown cannot cause unlimited latency or memory growth.
- Keep Gemini-specific event handling behind a translation-provider adapter because the model is currently a preview.
- Treat partial and final transcripts separately.
- Perform caption line wrapping in the application before sending text to vMix.
- Calculate caption width using Unicode display width rather than Python string length.
- Rate-limit and deduplicate vMix updates.
- A vMix or Gemini failure must not crash unrelated application components.
- Do not persist transcripts unless the feature is explicitly enabled.
- Bind the local FastAPI service to `127.0.0.1` by default. Do not expose the control API or WebSocket to the LAN unless the user explicitly enables it and access control is implemented.
- Treat the packaged application as a single Windows desktop product even if it contains a Python backend and compiled web frontend.

## Configuration and Repository Hygiene

- Resolve non-secret settings in this order: explicit CLI or runtime override, user configuration, then project defaults. Document any setting that intentionally uses a different order.
- Keep secrets in process memory, Windows Credential Manager, or development-only environment variables. Never store secrets in YAML, frontend assets, browser storage, test fixtures, or committed files.
- Provide `.env.example` with variable names and safe placeholders only.
- Add `.env`, local configuration, logs, caches, recordings, transcripts, API response captures, Python/Node build artifacts, coverage output, and downloaded executables to `.gitignore` as soon as those paths exist.
- Do not commit real voice recordings, credentials, generated transcripts, large binaries, downloaded tools, or user-specific device identifiers.
- Use short, non-sensitive fixture audio for automated tests.

## Planned Stages

1. Audio device discovery, capture, metering, and PCM conversion proof of concept.
2. Gemini Live Translate command-line integration.
3. Transcript assembly and Unicode-aware caption formatting.
4. FastAPI/WebSocket backend and React control/overlay pages.
5. vMix API and Browser Input integration.
6. Windows packaging, soak testing, reconnect behavior, and documentation.

Fixes and refinements inside an existing capability should use sub-stage numbers such as `2.1` rather than consuming a new main stage.

## Verification Requirements

For every implementation stage:

- Write or update focused automated tests.
- Run the relevant tests and report actual output.
- Run a real CLI or application smoke test where possible.
- Verify failure paths relevant to the stage.
- Confirm no unrelated files were changed.
- Stop after the requested stage is complete.
- Summarize changed files, test results, completed scope, and remaining stages.

Never report a feature as working based only on a stub, mock, or unexecuted code path. If hardware, credentials, Gemini access, or vMix availability blocks an integration test, report the exact blocker and still verify all locally testable behavior.

## Coding Standards

- Python: type hints, explicit error handling, `pathlib.Path`, structured logging, and testable dependency boundaries.
- TypeScript: strict mode, typed WebSocket messages, accessible controls, and reusable state models.
- Prefer standard-library functionality and existing dependencies before adding packages.
- Python and npm project dependencies may be installed through the documented project dependency workflow.
- Before development or release verification, inventory every required driver, runtime, external program, and native component. Confirm that all prerequisites required by the selected hardware and enabled features are installed and functional so the complete application can run.
- For system-level prerequisites such as FFmpeg, Node.js, audio drivers, ASIO components, and vMix, first tell the user their purpose, recommended or supported version, installation impact, and verification command or procedure.
- Do not modify the system `PATH`, install or replace drivers, install global packages, or install system-level programs without the user's explicit approval.
- After installation, perform both a version check and a functional check. A version string alone is not sufficient verification.
- Do not silently assume that an external executable, driver, device, or service is available. Do not report dependent functionality as complete until every required prerequisite has been installed and exercised.
- Avoid hidden global mutable state.
- Keep functions and classes narrowly scoped.
- Document non-obvious streaming, concurrency, and reconnect behavior.

## Communication and UI Language

- Use Traditional Chinese for user-facing progress reports, errors, installation guidance, prerequisite notices, and verification results.
- Keep source code identifiers, API fields, class names, function names, and protocol payload fields in English.
- The packaged application's default UI language must be Traditional Chinese.

## Input and Output Security

- Render frontend captions as text nodes. Do not use unfiltered `innerHTML` or equivalent HTML injection paths.
- Correctly URL-encode every vMix `Value`, `Input`, and `SelectedName` parameter.
- Never concatenate caption text into HTML, shell commands, executable arguments, or URL query strings without the appropriate safe API and encoding.
- Apply a configurable maximum caption payload length before broadcasting to the frontend or vMix. Reject or safely truncate oversized payloads and log only metadata, not sensitive transcript content.
- Validate configuration values, ports, vMix targets, device identifiers, caption dimensions, and WebSocket messages at the backend boundary.

## Windows Audio Compatibility

- Implement and verify WASAPI/WDM device support first.
- Enumerate actual devices, host APIs, channel counts, and sample rates; do not infer hardware support from package installation alone.
- If a selected device requires ASIO, report that requirement clearly and verify the manufacturer's ASIO driver and the application's ASIO-capable capture path before claiming support.
- If physical hardware is unavailable, virtual or fixture audio may test local processing, but the result must not be reported as real microphone or audio-interface verification.
- Device removal, driver errors, unsupported sample rates, and channel-selection errors must produce a Traditional Chinese actionable error without crashing the service.

## Initial Acceptance Targets

- The application can enumerate and select a Windows input device.
- Captured audio is converted to 16 kHz mono signed PCM16 little-endian in 100 ms chunks.
- Gemini output transcription is assembled into stable Traditional Chinese captions.
- The overlay and vMix consume the same formatted caption state.
- Caption font, size, colors, alignment, line count, and line width are configurable.
- vMix being offline does not stop the web overlay.
- Gemini API credentials never appear in frontend assets, WebSocket messages, or logs.
