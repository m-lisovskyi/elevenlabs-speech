import os
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

API_BASE = "https://api.elevenlabs.io"
STT_MODEL_ID = os.environ.get("ELEVENLABS_STT_MODEL", "scribe_v2")
BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
ENV_FILE = BASE_DIR / ".env"

TTS_MODELS = [
    {"model_id": "eleven_multilingual_v2", "name": "Multilingual v2 (most natural)"},
    {"model_id": "eleven_v3", "name": "v3 (most expressive)"},
    {"model_id": "eleven_flash_v2_5", "name": "Flash v2.5 (fastest)"},
    {"model_id": "eleven_turbo_v2_5", "name": "Turbo v2.5 (fast, high quality)"},
]

# Premade voices available on every account. Used when the API key lacks the voices_read permission.
DEFAULT_VOICES = [
    {"voice_id": "JBFqnCBsd6RMkjVDRZzb", "name": "George"},
    {"voice_id": "EXAVITQu4vr4xnSDxMaL", "name": "Sarah"},
    {"voice_id": "CwhRBWXzGAHq8TQ4Fs17", "name": "Roger"},
    {"voice_id": "FGY2WhTYpPnrIDTdsKH5", "name": "Laura"},
    {"voice_id": "IKne3meq5aSn9XLyUdCD", "name": "Charlie"},
    {"voice_id": "N2lVS1w4EtoT3dr4eOWO", "name": "Callum"},
    {"voice_id": "SAz9YHcvj6GT2YYXdXww", "name": "River"},
    {"voice_id": "TX3LPaxmHKxFdv7VOQHJ", "name": "Liam"},
    {"voice_id": "Xb7hH8MSUJpSbSDYk0k2", "name": "Alice"},
    {"voice_id": "XrExE9yKIg1WjnnlVkGX", "name": "Matilda"},
    {"voice_id": "bIHbv24MWmeRgasZH58o", "name": "Will"},
    {"voice_id": "cgSgspJ2msm6clMCkdW9", "name": "Jessica"},
    {"voice_id": "cjVigY5qzO86Huf0OWal", "name": "Eric"},
    {"voice_id": "iP95p4xoKVk53GoZ742B", "name": "Chris"},
    {"voice_id": "nPczCjzI2devNBz1zQrb", "name": "Brian"},
    {"voice_id": "onwK4e9ZLuTAKqWW03F9", "name": "Daniel"},
    {"voice_id": "pFZP5JQG7iQjIQuC4Bku", "name": "Lily"},
]

app = FastAPI(title="ElevenLabs Speech App")


def _key_from_env_file() -> str:
    if not ENV_FILE.exists():
        return ""
    for line in ENV_FILE.read_text().splitlines():
        name, sep, value = line.partition("=")
        if sep and name.strip() == "ELEVENLABS_API_KEY":
            return value.strip().strip("'\"")
    return ""


def _api_key() -> str:
    # Re-read .env on every call so the key can be added without restarting the server
    key = os.environ.get("ELEVENLABS_API_KEY") or _key_from_env_file()
    if not key or key == "your-key-here":
        raise HTTPException(500, "ELEVENLABS_API_KEY is not set (export it or put it in .env)")
    return key


def _raise_upstream_error(resp: httpx.Response):
    try:
        detail = resp.json().get("detail", resp.text)
    except ValueError:
        detail = resp.text
    raise HTTPException(resp.status_code, detail)


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


# ---------- Speech-to-text ----------


@app.post("/api/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    language_code: str = Form(""),
    diarize: bool = Form(False),
    tag_audio_events: bool = Form(True),
):
    audio = await file.read()
    if not audio:
        raise HTTPException(400, "Empty audio file")

    data = {
        "model_id": STT_MODEL_ID,
        "diarize": str(diarize).lower(),
        "tag_audio_events": str(tag_audio_events).lower(),
        "timestamps_granularity": "word",
    }
    # Empty means auto-detect; ElevenLabs rejects an empty language_code
    if language_code.strip():
        data["language_code"] = language_code.strip()

    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"{API_BASE}/v1/speech-to-text",
            headers={"xi-api-key": _api_key()},
            data=data,
            files={"file": (file.filename or "audio", audio, file.content_type or "application/octet-stream")},
        )

    if resp.status_code != 200:
        _raise_upstream_error(resp)

    return resp.json()


@app.post("/api/realtime-token")
async def realtime_token():
    """Single-use token (valid 15 min) so the browser can open the realtime WebSocket without the API key."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{API_BASE}/v1/single-use-token/realtime_scribe", headers={"xi-api-key": _api_key()}
        )

    if resp.status_code != 200:
        _raise_upstream_error(resp)

    return {"token": resp.json()["token"]}


# ---------- Text-to-speech ----------


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    voice_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9]+$")
    model_id: str = TTS_MODELS[0]["model_id"]
    speed: float = Field(1.0, ge=0.7, le=1.2)
    stability: float = Field(0.5, ge=0, le=1)


@app.get("/api/tts/options")
async def tts_options():
    """Voices from the account library, falling back to premade voices if the key can't read voices."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{API_BASE}/v2/voices", params={"page_size": 100}, headers={"xi-api-key": _api_key()}
        )

    if resp.status_code == 200:
        voices = [
            {"voice_id": v["voice_id"], "name": v["name"], "category": v.get("category")}
            for v in resp.json().get("voices", [])
        ]
        source = "account"
    elif resp.status_code in (401, 403):
        voices, source = DEFAULT_VOICES, "defaults"
    else:
        _raise_upstream_error(resp)

    return {"voices": voices, "voices_source": source, "models": TTS_MODELS}


@app.post("/api/tts")
async def tts(req: TTSRequest):
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{API_BASE}/v1/text-to-speech/{req.voice_id}",
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": _api_key()},
            json={
                "text": req.text,
                "model_id": req.model_id,
                "voice_settings": {"stability": req.stability, "similarity_boost": 0.75, "speed": req.speed},
            },
        )

    if resp.status_code != 200:
        _raise_upstream_error(resp)

    return Response(resp.content, media_type="audio/mpeg")
