# Tauron Power Outages

Watches Tauron Dystrybucja's published power outages for one household and exposes the ones that affect it to Home Assistant.

## Language

**Outage**:
A single interruption of power supply published by Tauron, with a start, an end and a message naming the affected localities.
_Avoid_: Event, item, shutdown

**Address**:
The household's place in Tauron's register of address points: a city, a street (if the city has named streets) and a house number. The integration queries the Outage feed for it. Chosen by searching Tauron's register by name, never typed in as codes, and shown by those names. A village without named streets has a single unnamed street carrying the village's name.
_Avoid_: Location, GAID

**Outage feed**:
Everything Tauron returns for an address query. It covers a whole group of neighbouring addresses, not only the household's own.
_Avoid_: API response, outage list

**Locality**:
The named place (village or town) whose outages the household cares about, e.g. "Ogrodnica".
_Avoid_: Area, region, town

**Active outage**:
An Outage whose start-to-end window contains the current moment. Tauron's own "active" flag is informational only and does not decide this.
_Avoid_: Current outage, ongoing outage

**Local outage**:
An Outage from the Outage feed whose message names the household's Locality. If no Locality is set, every Outage in the feed is local. These are the only outages the integration shows.
_Avoid_: Filtered outage, relevant outage
