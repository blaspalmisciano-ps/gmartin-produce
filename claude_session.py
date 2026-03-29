"""Claude conversation manager with Ableton tool use."""

import json
import anthropic
from ableton_client import AbletonClient
from presets import list_presets, load_preset, apply_preset

SYSTEM_PROMPT = """You are GMartin, a music production assistant named after George Martin — the legendary Beatles producer. You control Ableton Live directly through tools.

## Your personality
- You're a seasoned producer who knows music theory, mixing, and arrangement
- You're practical and action-oriented — when the user asks for something, DO it via tools
- You explain what you're doing briefly but focus on executing

## Critical rules
- ALWAYS use set_track_monitor state=1 (Auto) after recording so clips play back. Monitor=In (state=0) silences recorded clips — only use for live playing.
- After firing session clips, call back_to_arrangement to prevent arrangement override
- When user says "can't hear" — check monitor state FIRST
- Device indices shift when Tuner is at front of chain — always verify with get_track_info
- Track panning: use set_track_panning (mixer pan), NOT Utility Balance
- EQ boosts should be moderate (2-5dB) to avoid clipping/distortion
- Compressor Output Gain is in dB (-36 to 36), not 0-1
- Audio input device (Behringer UMC) resets on Ableton restart — user must set it manually

## Device URIs
Instruments: Operator=query:Synths#Operator, Wavetable=query:Synths#Wavetable, Drift=query:Synths#Drift, Drum Rack=query:Synths#Drum%20Rack, Simpler=query:Synths#Simpler
Effects: EQ Eight=query:AudioFx#EQ%20Eight, Compressor=query:AudioFx#Compressor, Reverb=query:AudioFx#Reverb, Echo=query:AudioFx#Echo, Delay=query:AudioFx#Delay, Saturator=query:AudioFx#Saturator, Chorus-Ensemble=query:AudioFx#Chorus-Ensemble, Utility=query:AudioFx#Utility, Amp=query:AudioFx#Amp, Gate=query:AudioFx#Gate, Tuner=query:AudioFx#Tuner, Drum Buss=query:AudioFx#Drum%20Buss, Overdrive=query:AudioFx#Overdrive, Pedal=query:AudioFx#Pedal, Cabinet=query:AudioFx#Cabinet, Limiter=query:AudioFx#Limiter, Glue Compressor=query:AudioFx#Glue%20Compressor
Drum Kits: 909=query:Drums#FileId_5447, 808=query:Drums#FileId_5446, 707=query:Drums#FileId_5445

## Available presets
{presets}
"""

TOOLS = [
    {"name": "get_session_info", "description": "Get tempo, time sig, track count, master volume", "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_track_info", "description": "Get track details: name, type, devices, clips, arm, mute, solo, volume", "input_schema": {"type": "object", "properties": {"track_index": {"type": "integer"}}, "required": ["track_index"]}},
    {"name": "create_midi_track", "description": "Create a MIDI track. index=-1 appends at end.", "input_schema": {"type": "object", "properties": {"index": {"type": "integer", "default": -1}}}},
    {"name": "create_audio_track", "description": "Create an audio track for live instruments. index=-1 appends.", "input_schema": {"type": "object", "properties": {"index": {"type": "integer", "default": -1}}}},
    {"name": "delete_track", "description": "Delete a track by index. Cannot delete last track. Delete high to low.", "input_schema": {"type": "object", "properties": {"track_index": {"type": "integer"}}, "required": ["track_index"]}},
    {"name": "set_track_name", "description": "Rename a track", "input_schema": {"type": "object", "properties": {"track_index": {"type": "integer"}, "name": {"type": "string"}}, "required": ["track_index", "name"]}},
    {"name": "set_track_volume", "description": "Set track volume (0.0-1.0, default 0.85)", "input_schema": {"type": "object", "properties": {"track_index": {"type": "integer"}, "volume": {"type": "number"}}, "required": ["track_index", "volume"]}},
    {"name": "set_track_panning", "description": "Set track pan (-1=full left, 0=center, 1=full right). Use THIS for panning, not Utility.", "input_schema": {"type": "object", "properties": {"track_index": {"type": "integer"}, "panning": {"type": "number"}}, "required": ["track_index", "panning"]}},
    {"name": "set_track_arm", "description": "Arm/disarm track for recording", "input_schema": {"type": "object", "properties": {"track_index": {"type": "integer"}, "arm": {"type": "boolean"}}, "required": ["track_index", "arm"]}},
    {"name": "set_track_monitor", "description": "Set monitor mode. 0=In (live only, clips SILENT), 1=Auto (plays clips + live when armed), 2=Off. ALWAYS use 1 for playback.", "input_schema": {"type": "object", "properties": {"track_index": {"type": "integer"}, "state": {"type": "integer"}}, "required": ["track_index", "state"]}},
    {"name": "set_track_solo", "description": "Solo/unsolo a track", "input_schema": {"type": "object", "properties": {"track_index": {"type": "integer"}, "solo": {"type": "boolean"}}, "required": ["track_index", "solo"]}},
    {"name": "set_track_mute", "description": "Mute/unmute a track", "input_schema": {"type": "object", "properties": {"track_index": {"type": "integer"}, "mute": {"type": "boolean"}}, "required": ["track_index", "mute"]}},
    {"name": "set_track_input_routing", "description": "Set audio input routing. input_type='Ext. In', input_channel=1 or 2.", "input_schema": {"type": "object", "properties": {"track_index": {"type": "integer"}, "input_type": {"type": "string", "default": "Ext. In"}, "input_channel": {"type": "integer"}}, "required": ["track_index", "input_channel"]}},
    {"name": "get_track_routing_info", "description": "Get current input routing and available options", "input_schema": {"type": "object", "properties": {"track_index": {"type": "integer"}}, "required": ["track_index"]}},
    {"name": "set_tempo", "description": "Set BPM", "input_schema": {"type": "object", "properties": {"tempo": {"type": "number"}}, "required": ["tempo"]}},
    {"name": "create_clip", "description": "Create an empty MIDI clip", "input_schema": {"type": "object", "properties": {"track_index": {"type": "integer"}, "clip_index": {"type": "integer"}, "length": {"type": "number", "default": 8.0}}, "required": ["track_index", "clip_index"]}},
    {"name": "add_notes_to_clip", "description": "Add MIDI notes. Each note: {pitch, start_time, duration, velocity, mute}", "input_schema": {"type": "object", "properties": {"track_index": {"type": "integer"}, "clip_index": {"type": "integer"}, "notes": {"type": "array", "items": {"type": "object"}}}, "required": ["track_index", "clip_index", "notes"]}},
    {"name": "get_clip_notes", "description": "Read MIDI notes from a clip", "input_schema": {"type": "object", "properties": {"track_index": {"type": "integer"}, "clip_index": {"type": "integer"}}, "required": ["track_index", "clip_index"]}},
    {"name": "set_clip_name", "description": "Rename a clip", "input_schema": {"type": "object", "properties": {"track_index": {"type": "integer"}, "clip_index": {"type": "integer"}, "name": {"type": "string"}}, "required": ["track_index", "clip_index", "name"]}},
    {"name": "delete_clip", "description": "Delete a session clip from a slot", "input_schema": {"type": "object", "properties": {"track_index": {"type": "integer"}, "clip_index": {"type": "integer"}}, "required": ["track_index", "clip_index"]}},
    {"name": "fire_clip", "description": "Launch a clip. Fires empty slots too (starts recording if record mode on).", "input_schema": {"type": "object", "properties": {"track_index": {"type": "integer"}, "clip_index": {"type": "integer"}}, "required": ["track_index", "clip_index"]}},
    {"name": "stop_clip", "description": "Stop a clip", "input_schema": {"type": "object", "properties": {"track_index": {"type": "integer"}, "clip_index": {"type": "integer"}}, "required": ["track_index", "clip_index"]}},
    {"name": "load_instrument_or_effect", "description": "Load a device onto a track by URI. Loads at END of chain.", "input_schema": {"type": "object", "properties": {"track_index": {"type": "integer"}, "uri": {"type": "string"}}, "required": ["track_index", "uri"]}},
    {"name": "get_device_parameters", "description": "List all parameters of a device with name/value/min/max", "input_schema": {"type": "object", "properties": {"track_index": {"type": "integer"}, "device_index": {"type": "integer"}}, "required": ["track_index", "device_index"]}},
    {"name": "set_device_parameter", "description": "Set a device parameter. WARNING: values use the param's own range (check min/max), NOT always 0-1.", "input_schema": {"type": "object", "properties": {"track_index": {"type": "integer"}, "device_index": {"type": "integer"}, "param_name": {"type": "string"}, "value": {"type": "number"}}, "required": ["track_index", "device_index", "param_name", "value"]}},
    {"name": "start_playback", "description": "Start transport playback", "input_schema": {"type": "object", "properties": {}}},
    {"name": "stop_playback", "description": "Stop transport", "input_schema": {"type": "object", "properties": {}}},
    {"name": "start_recording", "description": "Enable global session record mode", "input_schema": {"type": "object", "properties": {}}},
    {"name": "stop_recording", "description": "Disable record mode", "input_schema": {"type": "object", "properties": {}}},
    {"name": "back_to_arrangement", "description": "Stop all session clips and return to arrangement playback. Call after firing any session clips.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "apply_preset", "description": "Apply a song style preset. Available: indie_rock, blues_90bpm", "input_schema": {"type": "object", "properties": {"preset_id": {"type": "string"}}, "required": ["preset_id"]}},
]


class ClaudeSession:
    """Manages a Claude conversation with Ableton tool use."""

    def __init__(self, ableton: AbletonClient):
        self.ableton = ableton
        self.client = None
        self.messages = []
        self.model = "claude-sonnet-4-6"

    def _get_client(self):
        """Get or create the Anthropic client — picks up key from env."""
        import os
        self.client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        return self.client

    def _get_system_prompt(self) -> str:
        presets = list_presets()
        preset_text = "\n".join(f"- {p['id']}: {p['name']} — {p['description']}" for p in presets)
        return SYSTEM_PROMPT.format(presets=preset_text or "No presets available")

    def _execute_tool(self, name: str, input_data: dict) -> str:
        """Execute an Ableton tool and return the result as a string."""
        if name == "apply_preset":
            preset = load_preset(input_data["preset_id"])
            if preset is None:
                return json.dumps({"error": f"Preset '{input_data['preset_id']}' not found"})
            log = apply_preset(preset, self.ableton)
            return json.dumps({"log": log})

        # All other tools map directly to Ableton commands
        result = self.ableton.send_command(name, input_data)
        return json.dumps(result)

    async def chat(self, user_message: str):
        """Send a user message and yield response chunks with streaming."""
        import asyncio
        import queue
        import threading

        self.messages.append({"role": "user", "content": user_message})

        try:
            loop = asyncio.get_event_loop()

            while True:
                client = self._get_client()

                # Use a queue to stream chunks from the sync thread to async
                chunk_queue = queue.Queue()
                collected_content = []

                def run_stream():
                    try:
                        with client.messages.stream(
                            model=self.model,
                            max_tokens=4096,
                            system=self._get_system_prompt(),
                            tools=TOOLS,
                            messages=self.messages,
                        ) as stream:
                            for event in stream:
                                chunk_queue.put(("event", event))
                            # Get the final message
                            msg = stream.get_final_message()
                            chunk_queue.put(("final", msg))
                    except Exception as e:
                        chunk_queue.put(("error", e))

                thread = threading.Thread(target=run_stream, daemon=True)
                thread.start()

                # Process chunks as they arrive
                while True:
                    # Non-blocking check with short timeout
                    try:
                        item = await loop.run_in_executor(None, lambda: chunk_queue.get(timeout=0.1))
                    except queue.Empty:
                        continue

                    kind, data = item

                    if kind == "error":
                        raise data

                    if kind == "event":
                        # Stream text deltas
                        if hasattr(data, 'type'):
                            if data.type == "content_block_delta":
                                if hasattr(data.delta, 'text'):
                                    yield {"type": "text_delta", "content": data.delta.text}
                            elif data.type == "content_block_start":
                                if hasattr(data.content_block, 'type') and data.content_block.type == "tool_use":
                                    yield {"type": "tool_call", "name": data.content_block.name, "input": {}}
                        continue

                    if kind == "final":
                        response = data
                        break

                # Process the final message
                assistant_content = response.content
                self.messages.append({"role": "assistant", "content": assistant_content})

                has_tool_use = False
                tool_results = []

                for block in assistant_content:
                    if block.type == "tool_use":
                        has_tool_use = True
                        # Update the tool call with actual input
                        yield {"type": "tool_call", "name": block.name, "input": block.input}

                        result = await loop.run_in_executor(None, self._execute_tool, block.name, block.input)
                        yield {"type": "tool_result", "name": block.name, "result": result}

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

                if has_tool_use:
                    self.messages.append({"role": "user", "content": tool_results})
                else:
                    break

        except Exception as e:
            yield {"type": "error", "content": str(e)}

        yield {"type": "done"}

    def reset(self):
        """Clear conversation history."""
        self.messages = []
