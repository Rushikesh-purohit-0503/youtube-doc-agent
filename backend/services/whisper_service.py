import asyncio
import os
import tempfile

import yt_dlp

_model = None  # module-level cache — loaded once per worker process


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        model_size = os.getenv("WHISPER_MODEL", "tiny")
        _model = WhisperModel(model_size, device="cpu", compute_type="int8")
    return _model


_COOKIES_FILE = os.path.join(os.path.dirname(__file__), '..', 'cookies.txt')


def _download_audio(url: str, output_dir: str) -> str:
    output_template = os.path.join(output_dir, '%(id)s.%(ext)s')
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best[ext=mp4]/best',
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'extractor_args': {'youtube': {'player_client': ['tv_embedded', 'android']}},
        **({"cookiefile": _COOKIES_FILE} if os.path.exists(_COOKIES_FILE) else {}),
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        video_id = info['id']
        ext = info.get('ext', 'm4a')

    audio_path = os.path.join(output_dir, f'{video_id}.{ext}')
    if not os.path.exists(audio_path):
        for fname in os.listdir(output_dir):
            if fname.startswith(video_id):
                return os.path.join(output_dir, fname)
        raise FileNotFoundError(f"Downloaded audio not found for video {video_id}")
    return audio_path


def _transcribe_sync(youtube_url: str) -> str:
    model = _get_model()
    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = _download_audio(youtube_url, tmpdir)
        segments, _ = model.transcribe(
            audio_path,
            beam_size=1,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        return ' '.join(seg.text.strip() for seg in segments)


async def transcribe_audio(youtube_url: str) -> str:
    """Download and transcribe audio using faster-whisper (CPU, int8)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _transcribe_sync, youtube_url)
