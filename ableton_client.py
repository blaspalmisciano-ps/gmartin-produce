"""Ableton Live TCP socket client — wraps the AbletonMCP protocol."""

import socket
import json
import time


class AbletonClient:
    """Communicates with Ableton Live via the AbletonMCP Remote Script on localhost:9877."""

    def __init__(self, host="localhost", port=9877, timeout=15):
        self.host = host
        self.port = port
        self.timeout = timeout

    def send_command(self, cmd: str, params=None) -> dict:
        """Send a command to Ableton and return the JSON response."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect((self.host, self.port))
            msg = json.dumps({"type": cmd, "params": params or {}})
            sock.sendall((msg + "\n").encode())
            data = sock.recv(65536)
            return json.loads(data.decode())
        except (socket.timeout, ConnectionRefusedError, json.JSONDecodeError) as e:
            return {"status": "error", "result": {}, "message": str(e)}
        finally:
            sock.close()
            time.sleep(0.05)

    def is_connected(self) -> bool:
        """Check if Ableton is reachable."""
        r = self.send_command("get_session_info")
        return r.get("status") == "success"

    def get_state_light(self) -> dict:
        """Get lightweight Ableton state — session info only, no per-track details."""
        session = self.send_command("get_session_info")
        if session.get("status") != "success":
            return {"connected": False, "error": session.get("message", "Not connected")}

        return {
            "connected": True,
            "tempo": session["result"]["tempo"],
            "time_sig": f"{session['result']['signature_numerator']}/{session['result']['signature_denominator']}",
            "track_count": session["result"]["track_count"],
            "master_volume": session["result"]["master_track"]["volume"],
            "tracks": [],
        }

    def get_state(self) -> dict:
        """Get full Ableton state — session info + per-track details."""
        state = self.get_state_light()
        if not state.get("connected"):
            return state

        for i in range(state["track_count"]):
            t = self.send_command("get_track_info", {"track_index": i})
            if t.get("status") == "success":
                r = t["result"]
                track = {
                    "index": i,
                    "name": r["name"],
                    "is_audio": r["is_audio_track"],
                    "is_midi": r["is_midi_track"],
                    "mute": r["mute"],
                    "solo": r["solo"],
                    "arm": r["arm"],
                    "volume": round(r["volume"], 2),
                    "panning": round(r["panning"], 2),
                    "devices": [d["name"] for d in r.get("devices", [])],
                    "clips": sum(1 for s in r.get("clip_slots", []) if s.get("has_clip")),
                }
                state["tracks"].append(track)

        return state
