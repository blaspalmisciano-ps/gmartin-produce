# GMartin Produce

A music production assistant powered by Claude + Ableton Live. Named after George Martin.

Dark-themed web app where you chat with Claude to control Ableton Live in real-time.

## Setup

```bash
pip3 install -r requirements.txt
python3 app.py
```

Open http://localhost:8877 — enter your Anthropic API key on first visit.

## Requirements

- Python 3.9+
- Ableton Live with AbletonMCP remote script (patched)
- Anthropic API key

## Features

- Chat with Claude to control Ableton Live
- Real-time Ableton state display (tracks, tempo, devices)
- Song style presets (Indie Rock, Blues)
- Tool execution visualization
- WebSocket streaming responses
