import asyncio
import os
import re
import ssl
import tempfile
import warnings

import requests
import urllib3
import yt_dlp

# Bypass self-signed proxy certs on corporate/VPN networks
ssl._create_default_https_context = ssl._create_unverified_context  # noqa: SLF001
warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)

# Patch requests so all requests skip SSL verification
_orig_send = requests.Session.send


def _no_verify_send(self, request, **kwargs):
    kwargs["verify"] = False
    return _orig_send(self, request, **kwargs)


requests.Session.send = _no_verify_send  # type: ignore[method-assign]

_YDL_BASE_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'nocheckcertificate': True,
    'extractor_args': {'youtube': {'player_client': ['tv_embedded', 'android']}},
}


class PrivateVideoError(Exception):
    pass


class NoTranscriptError(Exception):
    pass


def _extract_video_id(url: str) -> str:
    pattern = r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)([^&\n?#\s]+)'
    match = re.search(pattern, url)
    if match:
        return match.group(1)
    raise ValueError(f"Could not extract video ID from URL: {url}")


def get_video_duration_sec(url: str) -> int:
    """Fetch only metadata (no download) and return duration in seconds. Returns 0 on failure."""
    opts = {**_YDL_BASE_OPTS, 'skip_download': True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return int(info.get('duration') or 0)
    except Exception:
        return 0


def _parse_vtt(vtt_path: str) -> str:
    """Convert a YouTube VTT subtitle file into plain text."""
    with open(vtt_path, encoding='utf-8') as f:
        content = f.read()

    text_lines = []
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        # Skip VTT header lines
        if line.startswith(('WEBVTT', 'Kind:', 'Language:', 'NOTE')):
            continue
        # Skip timestamp lines (e.g. "00:00:01.000 --> 00:00:04.000 align:start")
        if re.match(r'^\d{2}:\d{2}', line) and '-->' in line:
            continue
        # Skip bare numeric cue IDs
        if re.match(r'^\d+$', line):
            continue
        # Strip inline timestamps <00:00:01.500> and tags <c> </c>
        line = re.sub(r'<[^>]+>', '', line).strip()
        if line:
            text_lines.append(line)

    # Remove consecutive duplicate lines (VTT often repeats partial cues)
    unique: list[str] = []
    prev = None
    for line in text_lines:
        if line != prev:
            unique.append(line)
            prev = line

    return ' '.join(unique)


def _get_transcript_sync(video_id: str) -> str:
    url = f'https://www.youtube.com/watch?v={video_id}'

    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = {
            **_YDL_BASE_OPTS,
            'skip_download': True,
            'writeautomaticsub': True,
            'writesubtitles': True,
            'subtitleslangs': ['en', 'en-US', 'en-GB', 'en-IN'],
            'subtitlesformat': 'vtt',
            'outtmpl': os.path.join(tmpdir, '%(id)s'),
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except yt_dlp.utils.DownloadError as exc:
            msg = str(exc).lower()
            if 'private' in msg or 'unavailable' in msg:
                raise PrivateVideoError("This video is private or unavailable")
            raise NoTranscriptError(f"Could not fetch subtitles: {exc}")

        vtt_files = [
            os.path.join(tmpdir, f)
            for f in os.listdir(tmpdir)
            if f.endswith('.vtt')
        ]
        if not vtt_files:
            raise NoTranscriptError("No captions available for this video")

        return _parse_vtt(vtt_files[0])


def _get_video_info_sync(url: str) -> dict:
    """Standalone info fetch — used only in the Whisper fallback path."""
    video_id = _extract_video_id(url)
    ydl_opts = {**_YDL_BASE_OPTS, 'skip_download': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                'title': info.get('title', 'Unknown Video'),
                'thumbnail': f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg',
            }
    except Exception:
        return {
            'title': 'Unknown Video',
            'thumbnail': f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg',
        }


def _get_transcript_and_info_sync(url: str) -> tuple[str, dict]:
    """Single yt-dlp call that returns both transcript and video metadata.
    Saves one full YouTube round-trip vs calling info + transcript separately."""
    video_id = _extract_video_id(url)

    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = {
            **_YDL_BASE_OPTS,
            'skip_download': True,
            'writeautomaticsub': True,
            'writesubtitles': True,
            'subtitleslangs': ['en', 'en-US', 'en-GB', 'en-IN'],
            'subtitlesformat': 'vtt',
            'outtmpl': os.path.join(tmpdir, '%(id)s'),
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                video_info = {
                    'title': info.get('title', 'Unknown Video'),
                    # hqdefault is always available for public videos; maxresdefault often 404s
                    'thumbnail': f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg',
                }
        except yt_dlp.utils.DownloadError as exc:
            msg = str(exc).lower()
            if 'private' in msg or 'unavailable' in msg:
                raise PrivateVideoError("This video is private or unavailable")
            raise NoTranscriptError(f"Could not fetch subtitles: {exc}")

        vtt_files = [
            os.path.join(tmpdir, f)
            for f in os.listdir(tmpdir)
            if f.endswith('.vtt')
        ]
        if not vtt_files:
            raise NoTranscriptError("No captions available for this video")

        return _parse_vtt(vtt_files[0]), video_info


async def get_transcript_and_info(youtube_url: str) -> tuple[str, dict]:
    """Preferred entry point — one yt-dlp call for both transcript and metadata."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _get_transcript_and_info_sync, youtube_url)


async def get_video_info(youtube_url: str) -> dict:
    """Fallback-only — used when captions are unavailable and Whisper is needed."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _get_video_info_sync, youtube_url)
