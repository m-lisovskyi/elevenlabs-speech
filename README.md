# ElevenLabs Speech ⇄ Text

A small web app that uses [ElevenLabs](https://elevenlabs.io) in both directions.

**Speech → Text**
- **Live:** you see the text while you speak. The browser streams mic audio straight to [Scribe v2 Realtime](https://elevenlabs.io/docs/api-reference/speech-to-text/v-1-speech-to-text-realtime) using a single-use token from the server.
- **Record or upload:** the more accurate option. It uses [Scribe v2](https://elevenlabs.io/docs/api-reference/speech-to-text/convert) and can label speakers and tag sounds such as laughter.

**Text → Speech**
- Generate speech with a choice of voice, model, speed and stability, then play or download the MP3.
- If your API key can read voices, the app lists your account's voice library. Otherwise it falls back to the built-in default voices.

Your API key stays on the server and never reaches the browser.

## Run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                    # then put your key in .env
uvicorn app:app --reload
```

Open http://localhost:8000. Browsers allow microphone access on `localhost` without HTTPS.

Get a key at https://elevenlabs.io/app/settings/api-keys. A restricted key needs the **Speech to Text** and **Text to Speech** permissions. **Voices read** is optional.

The server reads `ELEVENLABS_API_KEY` from the environment, or from `.env` on every request. Optional: set `ELEVENLABS_STT_MODEL` to override the batch model (default `scribe_v2`).

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/transcribe` | multipart `file`, plus optional `language_code`, `diarize`, `tag_audio_events` |
| `POST /api/realtime-token` | single-use token for the realtime WebSocket |
| `GET /api/tts/options` | voices and models |
| `POST /api/tts` | JSON `{text, voice_id, model_id?, speed?, stability?}` → `audio/mpeg` |

```bash
curl -X POST localhost:8000/api/tts -H 'Content-Type: application/json' \
  -d '{"text":"Hello world","voice_id":"JBFqnCBsd6RMkjVDRZzb"}' -o hello.mp3
curl -F file=@hello.mp3 localhost:8000/api/transcribe | jq .text
```
