# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Home Assistant custom integration ("Tauron Power Outages") that monitors power outages from Tauron Dystrybucja (Polish power distribution company). Provides sensors and calendar entities for outage tracking.

HA dashboards and automations (incl. the GoodWe outage manager) live in `~/Projects/sensors`, not here.

## Development Setup

```bash
mise install          # Install Python + uv via mise
uv sync               # Install dependencies
```

Tests: `uv run pytest`. They cover `outage_schedule.py` and `outage_feed_source.py` (pure Python), the aiohttp transport (against a local HTTP server), the coordinator's transition timer (real HA core, fake API and clock), and the whole integration in a test HA instance (`tests/test_config_flow.py`: the address-search setup flow against recorded register responses in `tests/fixtures/register/`; `tests/test_integration.py`: options flow, migration refusal, entity states, calendar trigger, unload; network stubbed with `aioclient_mock`, time with `freezer`), using `tests/fixtures/`.

`pytest-homeassistant-custom-component` lags HA releases: `[tool.uv] override-dependencies` pins the test HA to 2026.11.1 in place of the plugin's own pin, `tests/conftest.py` loads it (its entry point is disabled) after shimming HA internals it imports, and `-p homeassistant.const` imports HA before respx so HA can alias `httpx` to `httpx2`. When bumping HA, update the override; drop the shim and override once a plugin release pins that HA version. Tests that open sockets need the `socket_enabled` fixture.

This runs inside Home Assistant — copy `custom_components/tauron_outages/` into HA's `custom_components/` directory.

Distribution: Home Assistant Marketplace / HACS (`hacs.json`, brand images in `custom_components/tauron_outages/brand/`, releases tagged `vX.Y.Z` = manifest `version`). CI (`.github/workflows/validate.yml`) runs hassfest and hacs/action; hassfest rejects manifest keys it doesn't know. See `docs/publishing.md`.

## Architecture

All source lives in `custom_components/tauron_outages/`.

**Data flow:** `config_flow.py` (user setup) → `__init__.py` (coordinator) → `outage_feed_source.py` (requests the Outage feed through a transport) → `outage_schedule.py` (typed Outages) → `sensor.py` / `calendar.py` (entities)

- **Coordinator pattern**: `TauronDataUpdateCoordinator` in `__init__.py` polls every 4 hours (configurable). It owns the `OutageFeedSource` and narrows its schedule to the Locality.
- **Outage feed source** (`outage_feed_source.py`): Pure Python. `OutageFeedSource` requests the Outage feed. Built with an `Address`, a transport and the local time zone; `fetch(now)` builds the 7-day request, calls the transport and returns an `OutageSchedule`. `fetch` turns any transport failure (`OSError`, `ValueError`, incl. timeouts, HTTP errors and invalid JSON) into an `OutageFeedError`. `outage_feed_source_for(hass, entry data)` in `__init__.py` builds the production source for both the coordinator and the config flow's connection check.
- **Transport**: an async callable taking the request params and returning decoded JSON; it may raise freely. Production uses `http_transport.aiohttp_transport()` with HA's shared client session (`async_get_clientsession`); it reports HTTP ≥ 400 and aiohttp client errors as `OSError`; tests use `FixtureTransport` from `tests/conftest.py`.
- **Outage schedule** (`outage_schedule.py`): Pure Python, no `homeassistant` imports. Builds immutable `Outage`s from the feed (all key spellings, feed shapes and date formats live here only) and answers time questions for an explicit `now` (`active`, `upcoming`, `next`, `overlapping`, `next_transition`, `local(locality)`). Entities do no parsing and no key fallbacks; they query the schedule at read time.
- **Platforms**: device info shared via `entity.py`; `sensor.py` (4 sensors: status, next outage, count, items) and `calendar.py` (1 calendar), all showing Local outages only (ADR-0001).
- **Address search** (`address_search.py`): Pure Python. `AddressSearch` searches Tauron's register for cities and a city's streets through two transports (geo `cities` and `streets` endpoints) and returns immutable `CityMatch`/`StreetMatch`es. It owns the search rules (≥3 characters, no matches, >20 matches → `SearchRefused`) and turns transport failures into `AddressSearchError`. A street is a village's unnamed street when its prefix is blank and its name is the city's. `address_search_for(hass)` in `__init__.py` builds the production one.
- **Config flow** (`config_flow.py`, version 3): city search → city pick (skipped for one match) → street search (pre-filled with the city name) → street pick → house number, Name and Locality (pre-filled with the city name), then the Outage feed check. GAIDs plus display names (city name/label, commune, street label, empty for an unnamed street) live in entry data and are only used for display (device model, Options "Watching: …"); the Locality lives only in entry options. Options flow edits Locality and update interval and the update listener calls `TauronDataUpdateCoordinator.async_apply_options` only. Entries older than version 3 fail migration; users re-add them.
- **Locality**: decides which outages are Local; the coordinator's data is the Local-outage schedule; an empty Locality means every outage is local.

## Tools

- **Home Assistant MCP** is available — use it to query live device/entity states, control devices, and inspect automations directly.

## Key Conventions

- Python 3.14+ (HA 2026.11+), async/await throughout
- Translations in `translations/` (en + pl)
- Integration metadata in `manifest.json` (domain: `tauron_outages`, iot_class: `cloud_polling`)
- No YAML configuration — config flow only
- No comments or docstrings in code

# context-mode — MANDATORY routing rules

You have context-mode MCP tools available. These rules are NOT optional — they protect your context window from flooding. A single unrouted command can dump 56 KB into context and waste the entire session.

## BLOCKED commands — do NOT attempt these

### curl / wget — BLOCKED
Any Bash command containing `curl` or `wget` is intercepted and replaced with an error message. Do NOT retry.
Instead use:
- `ctx_fetch_and_index(url, source)` to fetch and index web pages
- `ctx_execute(language: "javascript", code: "const r = await fetch(...)")` to run HTTP calls in sandbox

### Inline HTTP — BLOCKED
Any Bash command containing `fetch('http`, `requests.get(`, `requests.post(`, `http.get(`, or `http.request(` is intercepted and replaced with an error message. Do NOT retry with Bash.
Instead use:
- `ctx_execute(language, code)` to run HTTP calls in sandbox — only stdout enters context

### WebFetch — BLOCKED
WebFetch calls are denied entirely. The URL is extracted and you are told to use `ctx_fetch_and_index` instead.
Instead use:
- `ctx_fetch_and_index(url, source)` then `ctx_search(queries)` to query the indexed content

## REDIRECTED tools — use sandbox equivalents

### Bash (>20 lines output)
Bash is ONLY for: `git`, `mkdir`, `rm`, `mv`, `cd`, `ls`, `npm install`, `pip install`, and other short-output commands.
For everything else, use:
- `ctx_batch_execute(commands, queries)` — run multiple commands + search in ONE call
- `ctx_execute(language: "shell", code: "...")` — run in sandbox, only stdout enters context

### Read (for analysis)
If you are reading a file to **Edit** it → Read is correct (Edit needs content in context).
If you are reading to **analyze, explore, or summarize** → use `ctx_execute_file(path, language, code)` instead. Only your printed summary enters context. The raw file content stays in the sandbox.

### Grep (large results)
Grep results can flood context. Use `ctx_execute(language: "shell", code: "grep ...")` to run searches in sandbox. Only your printed summary enters context.

## Tool selection hierarchy

1. **GATHER**: `ctx_batch_execute(commands, queries)` — Primary tool. Runs all commands, auto-indexes output, returns search results. ONE call replaces 30+ individual calls.
2. **FOLLOW-UP**: `ctx_search(queries: ["q1", "q2", ...])` — Query indexed content. Pass ALL questions as array in ONE call.
3. **PROCESSING**: `ctx_execute(language, code)` | `ctx_execute_file(path, language, code)` — Sandbox execution. Only stdout enters context.
4. **WEB**: `ctx_fetch_and_index(url, source)` then `ctx_search(queries)` — Fetch, chunk, index, query. Raw HTML never enters context.
5. **INDEX**: `ctx_index(content, source)` — Store content in FTS5 knowledge base for later search.

## Subagent routing

When spawning subagents (Agent/Task tool), the routing block is automatically injected into their prompt. Bash-type subagents are upgraded to general-purpose so they have access to MCP tools. You do NOT need to manually instruct subagents about context-mode.

## Output constraints

- Keep responses under 500 words.
- Write artifacts (code, configs, PRDs) to FILES — never return them as inline text. Return only: file path + 1-line description.
- When indexing content, use descriptive source labels so others can `ctx_search(source: "label")` later.

## ctx commands

| Command | Action |
|---------|--------|
| `ctx stats` | Call the `ctx_stats` MCP tool and display the full output verbatim |
| `ctx doctor` | Call the `ctx_doctor` MCP tool, run the returned shell command, display as checklist |
| `ctx upgrade` | Call the `ctx_upgrade` MCP tool, run the returned shell command, display as checklist |

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues at `bglowacki/tauron-outages` via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five canonical labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` + `docs/adr/` at the repo root (created lazily). See `docs/agents/domain.md`.
