# One Tauron register client

The integration does not merge the Outage feed source and the Address search into a single client for Tauron's register. `OutageFeedSource` and `AddressSearch` stay separate modules, each taking its own transport.

## Why this is out of scope

Both modules already earn their keep. Each owns rules the other doesn't need:

- `OutageFeedSource` builds the 7-day Outage feed request for an Address and hands the feed to `OutageSchedule`, which drops and logs malformed outages itself. It turns transport failures (`OSError`, `ValueError`) into `OutageFeedError`.
- `AddressSearch` owns the search rules (at least 3 characters, no matches, more than 20 matches) and parses register items itself, so it also catches `KeyError` and `TypeError` and turns them into `AddressSearchError`.

The difference in failure handling is deliberate, not drift. A shared client that applied "the same treatment to every endpoint" would have to absorb each module's parsing and search rules, which makes it wider without making it deeper.

The transport seam is already real and shared: one transport type, two adapters (the aiohttp transport in production and `FixtureTransport` in tests), and one aiohttp adapter reused for all three URLs. A single client would mostly save one hop when reading the code.

## When to reconsider

Revisit this if Tauron's register gives the integration a third endpoint to call. At that point the routes and failure translation may be worth a single home.

A smaller tidy-up stays in scope: moving the `Transport` type out of the Outage feed module, so `AddressSearch` does not import from it.

## Prior requests

- #22: "Architecture candidate: one Tauron register client for the Outage feed and Address search"
