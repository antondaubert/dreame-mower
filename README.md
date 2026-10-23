# 🏡 Dreame & MOVA Lawn Mower Integration for Home Assistant

[![GitHub Release](https://img.shields.io/github/v/release/antondaubert/dreame-mower?style=flat-square)](https://github.com/antondaubert/dreame-mower/releases)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg?style=flat-square)](https://hacs.xyz/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)

A Home Assistant integration for **Dreame** and **MOVA** robotic lawn mowers, with a live map card to mow, follow and set up the mower from a dashboard.

*If this integration saves you time, consider to [buy me a ☕](https://buymeacoffee.com/antondaubert).*

### Disclaimer
This is a **community-developed integration** for interoperability with Home Assistant. It is not affiliated with or supported by Dreame Technology or MOVA.

Provided "as-is" under the MIT License for personal, non-commercial use with devices you own. Use at your own risk.

## Features

- **Map card** - the active map drawn live: striped lawns, no-go areas, obstacles with their photos, and the mower with the lanes it has cut. Tap edges, zones or spot areas to mow just those.
- **Control** - start, pause, end and dock; mow the whole map, zones, edges or spot areas; go on from where an unfinished task stopped.
- **Work log** - past tasks with the area, the time, the battery each took per m² (marked when a task used more than like ones before it), a map of the lanes each one mowed and the photos of the obstacles it met.
- **Mowing settings** - cutting height, mowing direction, edges and obstacle avoidance, per map or per zone.
- **Map editor** - no-go zones, ignore-obstacle and spot areas, maintenance points; rename, split and merge zones; rename, back up, restore and switch maps.
- **Mower settings** - rain protection, charging period, frost protection, Do Not Disturb, lights, anti-theft alarms, child lock, robot voice and more, each where the mower offers it.
- **Schedules** - the mower's own schedules of the active map, switched on and off.
- **Maintenance** - wear of the blades, the station brush and the mower, with resets; send the mower to a maintenance point.
- **Entities** - battery, state, progress, errors and every setting above as sensors, switches, selects and times, for automations.

## Installation

1. Ensure [HACS](https://hacs.xyz/) is installed.
2. In HACS, open ⋮ → **Custom repositories** and add `https://github.com/antondaubert/dreame-mower` as an **Integration**.
3. Install **Dreame Mower** and restart Home Assistant.
4. **Settings → Devices & Services → Add Integration → Dreame Mower**, and sign in with your Dreamehome or MOVAhome account.

## Map card

The card is registered as a dashboard resource automatically. Add it from the dashboard editor (**Add card → Dreame Mower Card**) or in YAML:

```yaml
type: custom:dreame-mower-card
entity: lawn_mower.your_mower
# optional
title: Garden        # a small caption above the state
theme: auto          # the map's colours: auto, light or dark
show_header: true    # the status row with the state and the battery
show_controls: true  # what to mow and the start button
show_trail: true     # the lanes cut during a session
```

Its tabs are **Mow** (the map and what to mow), **History** (the work log), **Schedules** and **Settings** (the mower's settings, the map editor and the maps). It fits a phone screen, so it works well on its own in a **panel** view. Dashboards whose resources are managed in YAML need it added by hand, as a JavaScript module at `/dreame_mower/dreame-mower-card.js`. The map's rotation is set in the integration's options.

## Actions

Besides the standard `lawn_mower` actions, the integration offers these, each targeting the mower entity. Their fields are described in **Developer tools → Actions**.

| Action | What it does |
|---|---|
| `start_all_area_mowing`, `start_zone_mowing`, `start_edge_mowing`, `start_spot_mowing` | Mow the whole map, or several zones, edges or spot areas in one run |
| `end_task`, `recharge`, `stop_returning` | End a task where the mower is, send it to charge keeping the task, or stop it on its way home |
| `select_map` | Make another map the active one (only while no task runs) |
| `set_mowing_settings`, `set_mowing_preference_mode` | Change the mowing settings of a map or a zone, or switch between map-wide and per-zone settings |
| `set_no_go_zone`, `set_ignore_obstacle_area`, `set_spot_area`, `set_maintenance_point`, `delete_map_item` | Draw, change or delete what lies on the map |
| `rename_zone`, `split_zone`, `merge_zones`, `rename_map`, `backup_map`, `restore_map`, `delete_map` | Change zones and maps |
| `go_to_maintenance_point`, `reset_consumable`, `find_robot`, `clear_error`, `ignore_obstacle`, `clear_rain_protection` | Drive to a maintenance point, start a consumable's count over, have the mower call out, clear an error and go on, forget an obstacle, clear reported rain |
| `set_do_not_disturb`, `set_low_speed_at_night`, `set_start_from_stop_point`, `set_light`, `set_human_presence_alert`, `set_robot_voice` | Change the mower settings that take more than a switch |

```yaml
action: dreame_mower.start_zone_mowing
target:
  entity_id: lawn_mower.your_mower
data:
  zone_ids: [1, 3]
```

Zone, contour and map IDs are in the mower entity's attributes once the map has been read; a spot area's ID is what `set_spot_area` answers with.

To mow on a schedule kept in Home Assistant rather than on the mower, import the [schedule blueprint](blueprints/automation/antondaubert/dreame_mower_ha_schedule.yaml).

## Community & Support

- **Discussions**: Questions and ideas → [GitHub Discussions](https://github.com/antondaubert/dreame-mower/discussions)
- **Issues**: Bug reports and feature requests → [GitHub Issues](https://github.com/antondaubert/dreame-mower/issues)
- **Contributing**: see [CONTRIBUTING.md](CONTRIBUTING.md)

## License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

This integration builds upon:

- [Benedikt Hübschen's](https://github.com/bhuebschen/dreame-mower) original mower integration
- Insights from [Tasshack's](https://github.com/Tasshack/dreame-vacuum) vacuum integration
- Testing and feedback by the Home Assistant community

*Happy mowing! 🌱*
