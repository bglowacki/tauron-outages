# Tauron Power Outages - Home Assistant Integration

A custom Home Assistant integration that monitors power outages from Tauron Dystrybucja (Polish power distribution company).

## Features

- **Real-time outage status**: Know if there's currently an active power outage
- **Next outage prediction**: Get information about upcoming planned outages
- **Outage count**: Track the number of outages in the next 7 days
- **Detailed attributes & items**: Access additional information like outage reasons, start/end times, and a normalized list of outages
- **Locality**: Narrow results to outages whose message names your Locality (e.g. "Ogrodnica"); the Local group of entities follows it

## Entities

For each configuration entry, the integration creates the following sensors and a calendar. The "Local" group follows the Locality (see Configuration below).

1. **Outage Status** (`sensor.tauron_outage_status`)
   - State: "Active" or "Inactive"
   - Attributes: Next outage details, total outages count

2. **Next Outage** (`sensor.tauron_next_outage`)
   - State: Timestamp of next outage (or None)
   - Device Class: timestamp
   - Attributes: End time, reason, type

3. **Outage Count** (`sensor.tauron_outage_count`)
   - State: Number of outages in next 7 days
   - Attributes: Active outages, upcoming outages

4. **Outage Items** (`sensor.tauron_outage_items`)
   - State: Same as outage count (number of outages)
   - Attributes: `outages` list (normalized dicts with outageId, startDate, endDate, message, type, isActive, modified), convenience flags `has_active`, `has_upcoming`

Local group (outages in your Locality):

5. **Local Next Outage** (`sensor.tauron_local_next_outage`)
   - State: Timestamp of next outage among Local outages (or None)
   - Device Class: timestamp
   - Attributes: End time, reason, type

6. **Local Outage Count** (`sensor.tauron_local_outage_count`)
   - State: Number of outages matching filters
   - Attributes: Active outages, upcoming outages, `is_active` flag

7. **Local Outage Items** (`sensor.tauron_local_outage_items`)
   - State: Same as Local outage count
   - Attributes: `outages` list with same normalization as above, plus `has_active`, `has_upcoming`

8. **Outages Calendar** (`calendar.<your_name>_outages`)
   - Created automatically; no manual platform entry needed.
   - Name: Based on your configured Name (CONF_NAME), e.g. "My Home Outages".
   - Current event shows the next outage; the calendar view lists all outages overlapping the selected range.

## Installation

### HACS (Recommended)

1. Add this repository to HACS as a custom repository
2. Install "Tauron Power Outages" through HACS
3. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/tauron_outages` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant

## Configuration

1. Go to **Configuration** → **Integrations**
2. Click **Add Integration**
3. Search for "Tauron Power Outages"
4. Enter your address details:
   - **City GAID**: The city identifier from Tauron's system
   - **Street GAID**: The street identifier from Tauron's system  
   - **House Number**: Your house number
   - **Name**: A friendly name for the integration
   - (Optional) **Locality**: The place whose outages are yours, e.g. "Ogrodnica"

### Locality

- Tauron's feed covers a group of neighbouring addresses, so it often lists outages in nearby localities too. The Local entities show only outages whose message contains your Locality (case-insensitive substring match).
- An empty Locality means every outage in the feed counts as yours.
- The Locality and the update interval can be changed under **Configure** (Options) at any time. Changes apply immediately, without a restart and without a new request to Tauron. Clearing the Locality really clears it.

### Finding GAID Values

To find your GAID values, you can:

1. Use your browser's developer tools on the Tauron website
2. Look for network requests when searching for your address
3. Extract the `cityGAID` and `streetGAID` from the API calls

For example:
- `cityGAID`: "123456"
- `streetGAID`: "654321"
- `houseNo`: "1"

## Usage Examples

### Automations

```yaml
# Notify when an outage becomes active
- alias: "Power Outage Alert"
  trigger:
    - platform: state
      entity_id: sensor.tauron_outage_status
      to: "Active"
  action:
    - service: notify.mobile_app_phone
      data:
        message: "Power outage is now active at your address!"

# Prepare for upcoming outage
- alias: "Upcoming Outage Warning"
  trigger:
    - platform: state
      entity_id: sensor.tauron_next_outage
  condition:
    - condition: template
      value_template: >
        {{ (as_timestamp(states('sensor.tauron_next_outage')) - now().timestamp()) < 3600 }}
  action:
    - service: notify.mobile_app_phone
      data:
        message: "Power outage starts in less than 1 hour!"
```

### Lovelace Cards

```yaml
# Simple status card
type: entity
entity: sensor.tauron_outage_status
```

```yaml
# Detailed outage information
type: entities
entities:
  - sensor.tauron_outage_status
  - sensor.tauron_next_outage
  - sensor.tauron_outage_count
  - sensor.tauron_outage_items
```

#### Local examples

```yaml
# Local sensors card
type: entities
entities:
  - sensor.tauron_local_outage_count
  - sensor.tauron_local_next_outage
  - sensor.tauron_local_outage_items
```

#### Calendar Card

```yaml
# Show outages calendar (auto-created)
type: calendar
entities:
  - calendar.my_home_outages
```

## API Details

The integration polls the Tauron API every 30 minutes by default. It fetches outage data for the next 7 days and processes it to provide meaningful sensor states and attributes.

## Troubleshooting

### Common Issues

1. **Cannot connect error**: Verify your GAID values are correct
2. **No data**: Check if Tauron's API is accessible from your network
3. **Parsing errors**: The integration handles various datetime formats but may need updates for new API responses

### Debug Logging

Add this to your `configuration.yaml` for debug logging:

```yaml
logger:
  logs:
    custom_components.tauron_outages: debug
```

## Development

To contribute or modify:

1. Fork the repository
2. Make your changes
3. Test with your Home Assistant instance
4. Submit a pull request

## License

This project is licensed under the MIT License.

## Disclaimer

This is an unofficial integration and is not affiliated with Tauron Dystrybucja. Use at your own risk.
