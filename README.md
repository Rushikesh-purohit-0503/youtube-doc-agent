# YouTube Doc Agent

Paste a YouTube URL → get a storybook-style PDF notebook of everything discussed in the video.

## Stack
- **Backend** — Python FastAPI (Docker), Ollama `qwen2.5:14b`, ReportLab PDF
- **Frontend** — Flutter (iOS + Android)

---

## Prerequisites

1. **Docker Desktop** running
2. **Ollama** installed and running on your machine
3. Pull the model (one-time, ~8 GB):
   ```bash
   ollama pull qwen2.5:14b
   ```
4. **Flutter SDK** ≥ 3.0

---

## Backend — Quick Start

```bash
cd backend
docker-compose up --build
# API available at http://localhost:8000
# Docs at http://localhost:8000/docs
```

Volumes:
- `backend/pdfs/` — generated PDFs
- `backend/db/` — SQLite history

---

## Flutter App — Quick Start

```bash
cd flutter_app

# 1. Create the flutter project shell (first time only)
flutter create --project-name youtube_doc_agent --org com.example .

# 2. Install deps
flutter pub get

# 3. Set your machine's LAN IP in lib/config/api_config.dart
#    e.g.  static const String baseUrl = 'http://192.168.1.42:8000';

# 4. Run
flutter run
```

> **Android emulator**: use `http://10.0.2.2:8000`
> **iOS simulator**: use `http://127.0.0.1:8000`
> **Real device**: use your machine's LAN IP (same WiFi)

---

## How it works

```
YouTube URL
    → youtube-transcript-api (captions, fast path)
    → if private   → error shown to user
    → if no captions → yt-dlp + faster-whisper (audio transcription)
    → chunker splits transcript into 10 equal parts
    → 10 parallel Ollama calls (qwen2.5:14b)
    → assembler adds Introduction + Key Takeaways
    → ReportLab generates storybook PDF
    → saved to /app/pdfs + SQLite history
```

Target: **under 60 seconds** for a 1.5-hour video.

---

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/generate` | Start a job |
| GET | `/status/{job_id}` | Poll progress |
| GET | `/download/{job_id}` | Download PDF |
| GET | `/history` | List past docs |
| DELETE | `/history/{id}` | Delete a doc |
| GET | `/health` | Health check |
