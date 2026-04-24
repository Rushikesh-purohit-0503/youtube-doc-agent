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
    final response = await http
        .post(
          Uri.parse('${ApiConfig.baseUrl}/generate'),
          headers: AuthService.instance.authHeaders,
          body: jsonEncode({'youtube_url': youtubeUrl, 'template': template}),
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
