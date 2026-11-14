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

Tests: `uv run pytest`. They cover `outage_schedule.py` and `outage_feed.py` (pure Python), the urllib transport (against a local HTTP server), and the coordinator's transition timer (real HA core, fake API and clock), using `tests/fixtures/`.

This runs inside Home Assistant — copy `custom_components/tauron_outages/` into HA's `custom_components/` directory.

## Architecture

All source lives in `custom_components/tauron_outages/`.

**Data flow:** `config_flow.py` (user setup) → `__init__.py` (coordinator) → `outage_feed.py` (requests the feed through a transport) → `outage_schedule.py` (typed Outages) → `sensor.py` / `calendar.py` (entities)

- **Coordinator pattern**: `TauronDataUpdateCoordinator` in `__init__.py` polls every 4 hours (configurable). It owns the `OutageFeed` and narrows its schedule to the Locality.
- **Outage feed** (`outage_feed.py`): Pure Python. Built with an `Address`, a transport and the local time zone; `fetch(now)` builds the 7-day request, calls the transport and returns an `OutageSchedule`. `fetch` turns any transport failure (`OSError`, `ValueError`, incl. timeouts, HTTP errors and invalid JSON) into an `OutageFeedError`. `outage_feed_for(entry data)` in `__init__.py` builds the production feed for both the coordinator and the config flow's connection check.
- **Transport**: an async callable taking the request params and returning decoded JSON; it may raise freely. Production uses `http_transport.urllib_transport()` (blocking urllib in `asyncio.to_thread()`); tests use `FixtureTransport` from `tests/conftest.py`.
- **Outage schedule** (`outage_schedule.py`): Pure Python, no `homeassistant` imports. Builds immutable `Outage`s from the feed (all key spellings, feed shapes and date formats live here only) and answers time questions for an explicit `now` (`active`, `upcoming`, `next`, `overlapping`, `next_transition`, `local(locality)`). Entities do no parsing and no key fallbacks; they query the schedule at read time.
- **Platforms**: device info shared via `entity.py`; `sensor.py` (4 sensors: status, next outage, count, items) and `calendar.py` (1 calendar), all showing Local outages only (ADR-0001).
- **Config flow** (`config_flow.py`): UI-based setup using city/street GAID codes + house number + Locality. Address and name live in entry data; the Locality lives only in entry options. Options flow edits Locality and update interval and the update listener calls `TauronDataUpdateCoordinator.async_apply_options` only. Config entry migrations are pure functions in `migration.py`.
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
