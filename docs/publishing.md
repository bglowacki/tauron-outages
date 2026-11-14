# Publishing

The integration is installed through the Home Assistant Marketplace (HA 2026.11+, built-in HACS) and HACS on older versions. Both read `hacs.json` and the `hacs/default` catalog.

## What the repository ships

- `hacs.json`: display name and the minimum Home Assistant version (`2026.11.0`).
- `custom_components/tauron_outages/manifest.json`: its `version` is the release version.
- `custom_components/tauron_outages/brand/`: `icon.png` (256×256) and `icon@2x.png` (512×512), a placeholder "no power" pictogram. Replace the artwork any time; keep the sizes, PNG and a transparent, trimmed background. Don't use Home Assistant's or Tauron's logos.
- `.github/workflows/validate.yml`: hassfest and hacs/action (category: integration) on pushes to `main`, pull requests, daily and on demand. The `hacs/default` inclusion PR runs the same checks.

## Releasing

1. Bump `version` in `manifest.json` and merge to `main`.
2. Create a GitHub release with tag `vX.Y.Z` matching that version (e.g. `v1.3.3`) and notes saying what changed for households.

## Owner-only steps

In this order:

1. Repository settings: set the description (e.g. "Home Assistant integration for Tauron Dystrybucja power outages") and topics (`home-assistant`, `hacs`, `homeassistant-integration`, `tauron`, `power-outage`); keep Issues enabled.
2. Publish the first release, `v1.3.3`.
3. Run the Validate workflow on `main` (Actions → Validate → Run workflow) and confirm both jobs are green.
4. Open a PR to `hacs/default` adding `bglowacki/tauron-outages` to the `integration` list, following that repository's PR template.
5. Once it's merged, drop the "Custom repository" section from the README.
