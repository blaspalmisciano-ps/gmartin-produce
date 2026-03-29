"""GMartin Produce — Music production assistant powered by Claude + Ableton Live."""

import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ableton_client import AbletonClient
from claude_session import ClaudeSession
from presets import list_presets

app = FastAPI(title="GMartin Produce")
ableton = AbletonClient()

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/presets")
async def get_presets():
    return list_presets()


@app.get("/api/ableton/state")
async def get_ableton_state():
    return ableton.get_state()


@app.get("/api/ableton/connected")
async def ableton_connected():
    return {"connected": ableton.is_connected()}


@app.get("/api/key-status")
async def key_status():
    return {"has_key": bool(os.environ.get("ANTHROPIC_API_KEY"))}


@app.post("/api/set-key")
async def set_key(request: Request):
    data = await request.json()
    key = data.get("key", "")
    if not key.startswith("sk-ant-"):
        return {"error": "Invalid key format. Must start with sk-ant-"}
    os.environ["ANTHROPIC_API_KEY"] = key
    # Also save to .env for persistence
    env_path = Path(__file__).parent / ".env"
    env_path.write_text(f"ANTHROPIC_API_KEY={key}\n")
    return {"ok": True}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    session = ClaudeSession(ableton)

    # Send initial state
    state = ableton.get_state()
    await ws.send_json({"type": "ableton_state", "data": state})

    # Background task to poll Ableton state
    async def poll_state():
        while True:
            await asyncio.sleep(3)
            try:
                state = ableton.get_state()
                await ws.send_json({"type": "ableton_state", "data": state})
            except Exception:
                break

    poll_task = asyncio.create_task(poll_state())

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)

            if msg.get("type") == "chat":
                user_text = msg["content"]

                async for chunk in session.chat(user_text):
                    await ws.send_json(chunk)

                    # After tool execution, push updated state
                    if chunk.get("type") == "tool_result":
                        state = ableton.get_state()
                        await ws.send_json({"type": "ableton_state", "data": state})

            elif msg.get("type") == "reset":
                session.reset()
                await ws.send_json({"type": "text", "content": "Conversation reset. How can I help?"})
                await ws.send_json({"type": "done"})

    except WebSocketDisconnect:
        pass
    finally:
        poll_task.cancel()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8877)
