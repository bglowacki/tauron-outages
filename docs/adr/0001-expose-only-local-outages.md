# Expose only Local outages

Tauron's address query returns an Outage feed covering a whole group of neighbouring addresses, not just the household's own, so most outages in the feed (e.g. Chwalimierz for a household in Ogrodnica) never affect the household. We decided the integration exposes only Local outages: outages whose message names the configured Locality, or every outage in the feed when no Locality is set. There is a single set of entities and no "all outages" view.

## Considered Options

- **Keep both an "all" and a "filtered" set of entities** (the original design): rejected. It doubled the entities, and the all/filtered split leaked into every sensor and calendar. The only consumer (the GoodWe outage automations) used just the filtered calendar.
- **Locality as an optional filter in Options**: rejected. The Locality defines which outages are the household's, so it is set during setup alongside the address. It is stored only in Options, so there is a single place to edit it.

## Consequences

- There is no entity registry migration. The integration is removed and reinstalled, which creates the single set of entities under clean IDs (e.g. `calendar.<name>_outages`). Entity history is not preserved. The config entry stays at version 2; that migration only moves the Locality into Options.
- Automations that referenced `…_filtered_…` or `…_local_…` entity IDs must be fixed by hand after the reinstall. Until then, the GoodWe pre-outage charge doesn't run; this risk was knowingly accepted.
- The type filter was dropped. Tauron has only ever sent one outage type for this feed.
