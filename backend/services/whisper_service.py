import asyncio
import os
import tempfile

import yt_dlp


def _download_audio(url: str, output_dir: str) -> str:
    output_template = os.path.join(output_dir, '%(id)s.%(ext)s')
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio',
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'extractor_args': {'youtube': {'player_client': ['tv_embedded', 'android']}},
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        video_id = info['id']
        ext = info.get('ext', 'm4a')

    audio_path = os.path.join(output_dir, f'{video_id}.{ext}')
    if not os.path.exists(audio_path):
        # Extension may differ from what yt_dlp reports; scan the directory
        for fname in os.listdir(output_dir):
            if fname.startswith(video_id):
                return os.path.join(output_dir, fname)
        raise FileNotFoundError(f"Downloaded audio not found for video {video_id}")
    return audio_path


def _transcribe_sync(youtube_url: str) -> str:
    try:
        from faster_whisper import WhisperModel  # lazy import
    except ImportError:
        raise RuntimeError(
            "faster-whisper is not installed. "
            "Run: pip install faster-whisper  (requires ~1 GB + ffmpeg)"
        )
    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = _download_audio(youtube_url, tmpdir)
        model = WhisperModel("small", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(audio_path, beam_size=5)
        return ' '.join(seg.text.strip() for seg in segments)


async def transcribe_audio(youtube_url: str) -> str:
    """Download and transcribe audio using faster-whisper (CPU, int8)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _transcribe_sync, youtube_url)
