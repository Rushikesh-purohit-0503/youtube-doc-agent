import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';

import '../config/api_config.dart';
import 'auth_service.dart';

class ApiService {
  ApiService._();
  static final ApiService instance = ApiService._();

  // ── Config ────────────────────────────────────────────────────────────────

  Future<void> fetchConfig() async {
    try {
      final response = await http
          .get(Uri.parse('${ApiConfig.baseUrl}/config'))
          .timeout(const Duration(seconds: 5));
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        ApiConfig.isDev = (data['is_dev'] as bool?) ?? false;
      }
    } catch (_) {
      // Non-fatal — isDev stays false (safe default)
    }
  }

  // ── Generate ──────────────────────────────────────────────────────────────

  Future<String> generateDoc(String youtubeUrl, {String template = 'storybook'}) async {
    // Try to fetch transcript from YouTube using the user's IP (avoids server IP blocks)
    final prefetched = await _fetchTranscriptFromClient(youtubeUrl);

    final payload = <String, dynamic>{
      'youtube_url': youtubeUrl,
      'template': template,
      ...prefetched,
    };

    final response = await http
        .post(
          Uri.parse('${ApiConfig.baseUrl}/generate'),
          headers: AuthService.instance.authHeaders,
          body: jsonEncode(payload),
        )
        .timeout(const Duration(seconds: 15));

    if (response.statusCode == 200) {
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      return data['job_id'] as String;
    }

    String detail = 'Failed to start generation';
    try {
      final body = jsonDecode(response.body) as Map<String, dynamic>;
      detail = (body['detail'] as String?) ?? detail;
    } catch (_) {}
    throw Exception(detail);
  }

  /// Attempts to fetch transcript + metadata from YouTube using the user's IP.
  /// Returns a map with transcript/title/thumbnail_url keys, or empty map on failure.
  /// If this succeeds the backend skips yt-dlp entirely.
  Future<Map<String, dynamic>> _fetchTranscriptFromClient(String youtubeUrl) async {
    try {
      final videoId = _extractVideoId(youtubeUrl);
      if (videoId == null) return {};

      // Fetch metadata via oEmbed (no API key needed)
      String title = '';
      String thumbnailUrl = 'https://img.youtube.com/vi/$videoId/hqdefault.jpg';
      try {
        final metaResp = await http
            .get(Uri.parse(
              'https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=$videoId&format=json',
            ))
            .timeout(const Duration(seconds: 8));
        if (metaResp.statusCode == 200) {
          final meta = jsonDecode(metaResp.body) as Map<String, dynamic>;
          title = (meta['title'] as String?) ?? '';
          thumbnailUrl = (meta['thumbnail_url'] as String?) ?? thumbnailUrl;
        }
      } catch (_) {}

      // Try simple timedtext first (manually-uploaded captions)
      final simpleResp = await http
          .get(Uri.parse(
            'https://www.youtube.com/api/timedtext?v=$videoId&lang=en&fmt=json3',
          ))
          .timeout(const Duration(seconds: 10));
      // ignore: avoid_print
      print('[transcript] timedtext status=${simpleResp.statusCode} len=${simpleResp.body.length}');
      if (simpleResp.statusCode == 200 && simpleResp.body.trim().isNotEmpty) {
        final t = _parseTimedtextJson(simpleResp.body);
        // ignore: avoid_print
        print('[transcript] timedtext parsed len=${t.length}');
        if (t.isNotEmpty) {
          return {
            'transcript': t,
            if (title.isNotEmpty) 'title': title,
            'thumbnail_url': thumbnailUrl,
          };
        }
      }

      // Fetch video page to get auto-generated caption track URL + session cookies
      final browserHeaders = {
        'User-Agent':
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
      };
      final pageResp = await http
          .get(Uri.parse('https://www.youtube.com/watch?v=$videoId'), headers: browserHeaders)
          .timeout(const Duration(seconds: 15));
      // ignore: avoid_print
      print('[transcript] page status=${pageResp.statusCode} len=${pageResp.body.length}');
      if (pageResp.statusCode != 200) return {};

      // Forward session cookies YouTube set during the page load
      final pageCookies = pageResp.headers['set-cookie'] ?? '';

      final captionUrl = _extractCaptionUrl(pageResp.body);
      // ignore: avoid_print
      print('[transcript] captionUrl=$captionUrl');
      if (captionUrl == null) return {};

      final captionHeaders = {
        ...browserHeaders,
        'Referer': 'https://www.youtube.com/watch?v=$videoId',
        'Origin': 'https://www.youtube.com',
        if (pageCookies.isNotEmpty) 'Cookie': pageCookies,
      };

      http.Response captionResp = await http
          .get(Uri.parse('$captionUrl&fmt=json3'), headers: captionHeaders)
          .timeout(const Duration(seconds: 15));
      if (captionResp.statusCode == 200 && captionResp.body.trim().isEmpty) {
        captionResp = await http
            .get(Uri.parse(captionUrl), headers: captionHeaders)
            .timeout(const Duration(seconds: 15));
      }
      // ignore: avoid_print
      print('[transcript] caption status=${captionResp.statusCode} len=${captionResp.body.length} start=${captionResp.body.substring(0, captionResp.body.length.clamp(0, 100))}');
      if (captionResp.statusCode != 200) return {};

      final transcript = captionResp.body.trimLeft().startsWith('{')
          ? _parseTimedtextJson(captionResp.body)
          : _parseTimedtextXml(captionResp.body);
      // ignore: avoid_print
      print('[transcript] final transcript len=${transcript.length}');
      if (transcript.isEmpty) return {};

      return {
        'transcript': transcript,
        if (title.isNotEmpty) 'title': title,
        'thumbnail_url': thumbnailUrl,
      };
    } catch (_) {
      return {};
    }
  }

  String? _extractCaptionUrl(String html) {
    final regex = RegExp(r'"baseUrl":"(https://www\.youtube\.com/api/timedtext[^"]+)"');
    final matches = regex.allMatches(html).toList();

    String? manualEnglish;
    String? asrEnglish;
    String? anyManual;
    String? anyCaption;

    for (final m in matches) {
      final url = m.group(1)!.replaceAll(r'\u0026', '&');
      final isAsr = url.contains('caps=asr');
      final isEnglish = url.contains('lang=en');

      if (isEnglish && !isAsr) manualEnglish ??= url;
      if (isEnglish && isAsr) asrEnglish ??= url;
      if (!isAsr) anyManual ??= url;
      anyCaption ??= url;
    }

    final chosen = manualEnglish ?? asrEnglish ?? anyManual ?? anyCaption;
    // ignore: avoid_print
    print('[transcript] chosen url type: manualEn=${manualEnglish != null} asrEn=${asrEnglish != null}');
    return chosen;
  }

  String _parseTimedtextJson(String body) {
    try {
      final data = jsonDecode(body) as Map<String, dynamic>;
      final events = data['events'] as List<dynamic>? ?? [];
      final words = <String>[];
      for (final event in events) {
        final segs = (event as Map<String, dynamic>)['segs'] as List<dynamic>? ?? [];
        for (final seg in segs) {
          final text = ((seg as Map<String, dynamic>)['utf8'] as String? ?? '').trim();
          if (text.isNotEmpty && text != '\n') words.add(text);
        }
      }
      return words.join(' ').trim();
    } catch (_) {
      return '';
    }
  }

  String _parseTimedtextXml(String body) {
    try {
      return body
          .replaceAll(RegExp(r'<[^>]+>'), ' ')
          .replaceAll('&amp;', '&')
          .replaceAll('&lt;', '<')
          .replaceAll('&gt;', '>')
          .replaceAll('&quot;', '"')
          .replaceAll('&#39;', "'")
          .replaceAll(RegExp(r'\s+'), ' ')
          .trim();
    } catch (_) {
      return '';
    }
  }

  String? _extractVideoId(String url) {
    final patterns = [
      RegExp(r'youtube\.com/watch\?v=([^&\n?#\s]+)'),
      RegExp(r'youtu\.be/([^&\n?#\s]+)'),
      RegExp(r'youtube\.com/shorts/([^&\n?#\s]+)'),
      RegExp(r'youtube\.com/embed/([^&\n?#\s]+)'),
    ];
    for (final pattern in patterns) {
      final match = pattern.firstMatch(url);
      if (match != null) return match.group(1);
    }
    return null;
  }

  // ── Status polling ────────────────────────────────────────────────────────

  Future<Map<String, dynamic>> pollStatus(String jobId) async {
    final response = await http
        .get(Uri.parse('${ApiConfig.baseUrl}/status/$jobId'))
        .timeout(const Duration(seconds: 10));

    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw Exception('Failed to get status: ${response.statusCode}');
  }

  // ── Download PDF then delete from server ─────────────────────────────────

  Future<String> downloadPdf(String jobId) async {
    final response = await http
        .get(Uri.parse('${ApiConfig.baseUrl}/download/$jobId'))
        .timeout(const Duration(minutes: 2));

    if (response.statusCode == 200) {
      if (response.bodyBytes.isEmpty) {
        throw Exception('Server returned an empty PDF');
      }
      final dir = await _getPdfSaveDir();
      final filePath = '${dir.path}/notebook_$jobId.pdf';
      final file = File(filePath);
      await file.writeAsBytes(response.bodyBytes);
      if (!file.existsSync()) {
        throw Exception('PDF could not be saved to device');
      }
      await deletePdfFromServer(jobId);
      return filePath;
    }
    throw Exception('Failed to download PDF: ${response.statusCode}');
  }

  Future<Directory> _getPdfSaveDir() async {
    if (Platform.isAndroid) {
      // Request storage permission on Android < 13
      final status = await Permission.storage.request();
      if (status.isGranted) {
        final downloads = await getExternalStorageDirectory();
        if (downloads != null) return downloads;
      }
      // Fallback to app documents if permission denied
      return getApplicationDocumentsDirectory();
    }
    // iOS: Documents dir is now visible in Files app via Info.plist
    return getApplicationDocumentsDirectory();
  }

  /// Downloads a thumbnail from [url] and saves it next to the PDF.
  /// Returns the local file path, or empty string on failure.
  Future<String> downloadThumbnail(String url, String jobId) async {
    if (url.isEmpty) return '';
    try {
      final response = await http
          .get(Uri.parse(url))
          .timeout(const Duration(seconds: 15));
      if (response.statusCode == 200 && response.bodyBytes.isNotEmpty) {
        final dir = await getApplicationDocumentsDirectory();
        final filePath = '${dir.path}/thumb_$jobId.jpg';
        await File(filePath).writeAsBytes(response.bodyBytes);
        return filePath;
      }
    } catch (_) {}
    return '';
  }

  Future<void> deletePdfFromServer(String jobId) async {
    try {
      await http
          .delete(Uri.parse('${ApiConfig.baseUrl}/pdf/$jobId'))
          .timeout(const Duration(seconds: 10));
    } catch (_) {
      // Non-fatal — PDF was already saved to device
    }
  }
}
