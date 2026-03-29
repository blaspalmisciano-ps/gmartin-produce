"""Preset manager — load/save/apply song style presets."""

import json
import os
from pathlib import Path

PRESETS_DIR = Path(__file__).parent / "presets"


def list_presets():
    """List all available presets."""
    presets = []
    for f in sorted(PRESETS_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            presets.append({
                "id": f.stem,
                "name": data.get("name", f.stem),
                "description": data.get("description", ""),
                "tempo": data.get("tempo", 120),
            })
        except (json.JSONDecodeError, KeyError):
            continue
    return presets


def load_preset(preset_id: str):
    """Load a preset by ID (filename without extension)."""
    path = PRESETS_DIR / f"{preset_id}.json"
    if path.exists():
        return json.loads(path.read_text())
    return None


def save_preset(preset_id: str, data: dict) -> None:
    """Save a preset."""
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    path = PRESETS_DIR / f"{preset_id}.json"
    path.write_text(json.dumps(data, indent=2))


def apply_preset(preset: dict, ableton) -> list[str]:
    """Apply a preset to Ableton. Returns log of actions taken."""
    log = []

    # Clean slate
    info = ableton.send_command("get_session_info")
    if info.get("status") != "success":
        return ["ERROR: Cannot connect to Ableton"]

    tc = info["result"]["track_count"]
    for i in range(tc - 1, 0, -1):
        ableton.send_command("delete_track", {"track_index": i})
    log.append(f"Cleaned slate ({tc} tracks removed)")

    # Set tempo
    tempo = preset.get("tempo", 120)
    ableton.send_command("set_tempo", {"tempo": tempo})
    log.append(f"Tempo set to {tempo} BPM")

    # Build tracks
    for idx, track_def in enumerate(preset.get("tracks", [])):
        if idx > 0:
            if track_def.get("type") == "audio":
                ableton.send_command("create_audio_track", {"index": -1})
            else:
                ableton.send_command("create_midi_track", {"index": -1})

        # Name
        name = track_def.get("name", f"Track {idx}")
        ableton.send_command("set_track_name", {"track_index": idx, "name": name})

        # Devices
        for device in track_def.get("devices", []):
            uri = device.get("uri", "")
            if uri:
                ableton.send_command("load_instrument_or_effect", {"track_index": idx, "uri": uri})

            # Device params
            for param_name, value in device.get("params", {}).items():
                dev_idx = device.get("device_index")
                if dev_idx is not None:
                    ableton.send_command("set_device_parameter", {
                        "track_index": idx,
                        "device_index": dev_idx,
                        "param_name": param_name,
                        "value": value,
                    })

        # Routing
        routing = track_def.get("input_routing")
        if routing:
            ableton.send_command("set_track_input_routing", {
                "track_index": idx,
                "input_type": routing.get("type", "Ext. In"),
                "input_channel": routing.get("channel", 1),
            })

        # Volume, panning
        if "volume" in track_def:
            ableton.send_command("set_track_volume", {"track_index": idx, "volume": track_def["volume"]})
        if "panning" in track_def:
            ableton.send_command("set_track_panning", {"track_index": idx, "panning": track_def["panning"]})

        # Clips
        for clip_def in track_def.get("clips", []):
            clip_idx = clip_def.get("index", 0)
            length = clip_def.get("length", 8.0)
            ableton.send_command("create_clip", {"track_index": idx, "clip_index": clip_idx, "length": length})
            if clip_def.get("notes"):
                ableton.send_command("add_notes_to_clip", {
                    "track_index": idx,
                    "clip_index": clip_idx,
                    "notes": clip_def["notes"],
                })

        log.append(f"Track {idx}: {name} ({track_def.get('type', 'midi')})")

    # Arm tracks
    for idx in preset.get("arm_tracks", []):
        ableton.send_command("set_track_arm", {"track_index": idx, "arm": True})
        ableton.send_command("set_track_monitor", {"track_index": idx, "state": 1})  # Auto

    # Fire autoplay clip
    autoplay = preset.get("autoplay_clip")
    if autoplay:
        ableton.send_command("fire_clip", {
            "track_index": autoplay["track"],
            "clip_index": autoplay["clip"],
        })
        log.append("Drums playing!")

    log.append(f"Preset '{preset['name']}' applied!")
    return log
