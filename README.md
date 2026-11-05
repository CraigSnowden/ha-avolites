# Avolites Titan for Home Assistant

Control the playbacks on an Avolites Titan console or Titan server (D3 Core, Diamond, Arena, etc.) from Home Assistant, using the console's built-in WebAPI.

Each playback on the console's handle pages becomes a dimmable light:

| Home Assistant | Console |
| --- | --- |
| Turn on | Fire the playback (`Playbacks.FirePlaybackAtLevel`) |
| Brightness | Playback level (`Playbacks.SetPlaybackLevel` once fired) |
| Turn off | Release the playback, using its own release time |
| Turn off with `transition` | Release over that many seconds |

The console decides what each playback looks like, so whatever is programmed on the desk is what Home Assistant plays back.

## Installation

### HACS

1. In HACS, add this repository as a custom repository (category **Integration**).
2. Install **Avolites Titan** and restart Home Assistant.

### Manual

Copy `custom_components/avolites_titan` into your Home Assistant `config/custom_components` folder and restart.

## Setup

**Settings → Devices & services → Add integration → Avolites Titan**, then enter the console's IP address. The port defaults to `4430`.

The WebAPI has no authentication. Anything that can reach port 4430 can control the console, so keep it on a trusted network.

## Behaviour and limitations

- **Polling:** the console is polled every 5 seconds. Playbacks fired, released or faded on the desk show up in Home Assistant within that time.
- **Reading levels:** the WebAPI has no getter for a playback's level. The integration calls `SetPlaybackLevel` with a delta of 0, which returns the current level without changing it. Note that the API reference spells this parameter `level_leveldelta`, but the console only accepts `level_levelDelta`. This read is made only for active playbacks, once per poll.
- **New playbacks** added to the console's handle pages appear automatically. Playbacks that are deleted become unavailable and can then be removed from Home Assistant.
- Only playbacks are exposed for now. Groups, fixtures and palettes are not.

Each light has these attributes: `titan_id`, `user_number`, `handle_group`, `handle_page` and `handle_index` (page and index are 1-based).

## Development

```bash
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python -r requirements_test.txt
.venv/bin/python -m pytest
uvx ruff check custom_components tests
```

The tests use a mocked console. API reference: <https://api.avolites.com/19.2/>.
