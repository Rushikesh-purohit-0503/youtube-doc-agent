import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

import '../config/api_config.dart';
import '../models/doc_history.dart';

class ApiService {
  ApiService._();
  static final ApiService instance = ApiService._();

  // ── Generate ──────────────────────────────────────────────────────────────

  Future<String> generateDoc(String youtubeUrl) async {
    final response = await http
        .post(
          Uri.parse('${ApiConfig.baseUrl}/generate'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({'youtube_url': youtubeUrl}),
        )
        .timeout(const Duration(seconds: 15));

    if (response.statusCode == 200) {
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      return data['job_id'] as String;
    }

    // Surface backend error messages (e.g. private video)
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

  // ── Download PDF ──────────────────────────────────────────────────────────

  Future<String> downloadPdf(String jobId) async {
    final response = await http
        .get(Uri.parse('${ApiConfig.baseUrl}/download/$jobId'))
        .timeout(const Duration(minutes: 2));

    if (response.statusCode == 200) {
      final dir = await getApplicationDocumentsDirectory();
      final filePath = '${dir.path}/notebook_$jobId.pdf';
      await File(filePath).writeAsBytes(response.bodyBytes);
      return filePath;
    }
    throw Exception('Failed to download PDF: ${response.statusCode}');
  }

  // ── History ───────────────────────────────────────────────────────────────

  Future<List<DocHistory>> getHistory() async {
    final response = await http
        .get(Uri.parse('${ApiConfig.baseUrl}/history'))
        .timeout(const Duration(seconds: 10));

    if (response.statusCode == 200) {
      final list = jsonDecode(response.body) as List<dynamic>;
      return list
          .map((e) => DocHistory.fromJson(e as Map<String, dynamic>))
          .toList();
    }
    throw Exception('Failed to load history');
  }

  Future<void> deleteDoc(String docId) async {
    final response = await http
        .delete(Uri.parse('${ApiConfig.baseUrl}/history/$docId'))
        .timeout(const Duration(seconds: 10));

    if (response.statusCode != 200) {
      throw Exception('Failed to delete document');
    }
  }
}
