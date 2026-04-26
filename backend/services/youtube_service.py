import asyncio
import os
import re
import ssl
import tempfile
import warnings

import requests
import urllib3
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi

# Bypass self-signed proxy certs on corporate/VPN networks
ssl._create_default_https_context = ssl._create_unverified_context  # noqa: SLF001
warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)

# Patch requests so all requests skip SSL verification
_orig_send = requests.Session.send


def _no_verify_send(self, request, **kwargs):
    kwargs["verify"] = False
    return _orig_send(self, request, **kwargs)


requests.Session.send = _no_verify_send  # type: ignore[method-assign]

_COOKIES_FILE = os.path.join(os.path.dirname(__file__), '..', 'cookies.txt')

_PROXY = os.environ.get('YTDLP_PROXY')  # e.g. "socks5://user:pass@host:port"

_YDL_BASE_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'nocheckcertificate': True,
    'extractor_args': {'youtube': {'player_client': ['web', 'tv_embedded', 'android']}},
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    },
    **({"cookiefile": _COOKIES_FILE, "cookiesfrombrowser": None} if os.path.exists(_COOKIES_FILE) else {}),
    **({"proxy": _PROXY} if _PROXY else {}),
    'no_color': True,
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
    """Fetch transcript and video metadata.
    Tries youtube-transcript-api first (more reliable on cloud IPs), falls back to yt-dlp."""
    video_id = _extract_video_id(url)
    video_info = {
        'title': 'Unknown Video',
        'thumbnail': f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg',
    }

    # --- Attempt 1: YouTube Data API v3 (works from any IP) ---
    youtube_api_key = os.environ.get('YOUTUBE_API_KEY')
    if youtube_api_key:
        try:
            import logging
            # Get captions list
            captions_url = (
                f'https://www.googleapis.com/youtube/v3/captions'
                f'?part=snippet&videoId={video_id}&key={youtube_api_key}'
            )
            resp = requests.get(captions_url, timeout=10)
            captions_data = resp.json()
            caption_id = None
            for item in captions_data.get('items', []):
                lang = item['snippet']['language']
                if lang.startswith('en'):
                    caption_id = item['id']
                    video_info['title'] = item['snippet'].get('videoId', 'Unknown Video')
                    break

            # Get video title separately
            video_url = (
                f'https://www.googleapis.com/youtube/v3/videos'
                f'?part=snippet&id={video_id}&key={youtube_api_key}'
            )
            vresp = requests.get(video_url, timeout=10)
            vdata = vresp.json()
            if vdata.get('items'):
                video_info['title'] = vdata['items'][0]['snippet']['title']

            if caption_id:
                # Download caption track
                track_url = (
                    f'https://www.googleapis.com/youtube/v3/captions/{caption_id}'
                    f'?tfmt=srt&key={youtube_api_key}'
                )
                track_resp = requests.get(track_url, timeout=30)
                if track_resp.status_code == 200:
                    # Strip SRT timestamps and return plain text
                    import re as _re
                    srt_text = track_resp.text
                    lines = srt_text.splitlines()
                    text_lines = [
                        l for l in lines
                        if l.strip()
                        and not l.strip().isdigit()
                        and '-->' not in l
                    ]
                    transcript_text = ' '.join(text_lines)
                    return transcript_text, video_info
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("YouTube Data API failed: %s", e)

    # --- Attempt 2: youtube-transcript-api (no bot detection issues) ---
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(
            video_id, languages=['en', 'en-US', 'en-GB', 'en-IN']
        )
        transcript_text = ' '.join(entry['text'] for entry in transcript_list)

        # Fetch title via yt-dlp metadata only (no download)
        try:
            with yt_dlp.YoutubeDL({**_YDL_BASE_OPTS, 'skip_download': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                video_info['title'] = info.get('title', 'Unknown Video')
        except Exception:
            pass

        return transcript_text, video_info
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("youtube-transcript-api failed: %s", e)

    # --- Attempt 2: yt-dlp subtitles fallback ---
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
                video_info['title'] = info.get('title', 'Unknown Video')
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
