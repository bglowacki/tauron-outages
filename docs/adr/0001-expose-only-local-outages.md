# Expose only Local outages

Tauron's address query returns an Outage feed covering a whole group of neighbouring addresses, not just the household's own, so most outages in the feed (e.g. Chwalimierz for a household in Ogrodnica) never affect the household. We decided the integration exposes only Local outages: outages whose message names the configured Locality, or every outage in the feed when no Locality is set. There is a single set of entities and no "all outages" view.

## Considered Options

- **Keep both an "all" and a "filtered" set of entities** (the original design): rejected. It doubled the entities, and the all/filtered split leaked into every sensor and calendar. The only consumer (the GoodWe outage automations) used just the filtered calendar.
- **Locality as an optional filter in Options**: rejected. The Locality defines which outages are the household's, so it is set during setup alongside the address. It is stored only in Options, so there is a single place to edit it.

## Consequences

- Version 2 of the config entry migration removes the former unfiltered entities, together with their history. The filtered entities take over the clean entity IDs (e.g. `calendar.<name>_outages`).
- Automations that referenced `…_filtered_…` entity IDs must be updated after the upgrade. Until then, the GoodWe pre-outage charge doesn't run; this risk was knowingly accepted.
- The type filter was dropped. Tauron has only ever sent one outage type for this feed.
