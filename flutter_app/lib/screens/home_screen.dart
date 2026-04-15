import 'dart:async';

import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../widgets/progress_card.dart';
import 'viewer_screen.dart';

enum _State { idle, processing, done, error }

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _urlCtrl = TextEditingController();
  final _api = ApiService.instance;

  _State _state = _State.idle;
  String _jobId = '';
  String _statusMsg = '';
  int _progress = 0;
  String _pdfPath = '';
  String _errorMsg = '';
  Timer? _pollTimer;

  @override
  void dispose() {
    _urlCtrl.dispose();
    _pollTimer?.cancel();
    super.dispose();
  }

  // ── Actions ───────────────────────────────────────────────────────────────

  Future<void> _generate() async {
    final url = _urlCtrl.text.trim();
    if (url.isEmpty) {
      _snack('Please enter a YouTube URL');
      return;
    }

    setState(() {
      _state = _State.processing;
      _progress = 0;
      _statusMsg = 'Starting...';
      _errorMsg = '';
    });

    try {
      _jobId = await _api.generateDoc(url);
      _startPolling();
    } catch (e) {
      _setError(e.toString().replaceAll('Exception: ', ''));
    }
  }

  void _startPolling() {
    _pollTimer?.cancel();
    _pollTimer = Timer.periodic(const Duration(seconds: 2), (_) async {
      try {
        final status = await _api.pollStatus(_jobId);
        if (!mounted) return;

        setState(() {
          _progress = status['progress'] as int;
          _statusMsg = status['message'] as String;
        });

        final st = status['status'] as String;
        if (st == 'done') {
          _pollTimer?.cancel();
          await _handleDone();
        } else if (st == 'error') {
          _pollTimer?.cancel();
          _setError(status['message'] as String);
        }
      } catch (_) {
        // transient network error — keep polling
      }
    });
  }

  Future<void> _handleDone() async {
    try {
      final path = await _api.downloadPdf(_jobId);
      if (!mounted) return;
      setState(() {
        _state = _State.done;
        _pdfPath = path;
        _progress = 100;
        _statusMsg = 'Your notebook is ready!';
      });
    } catch (e) {
      _setError('Failed to download PDF: $e');
    }
  }

  void _setError(String msg) {
    setState(() {
      _state = _State.error;
      _errorMsg = msg;
    });
  }

  void _reset() {
    _pollTimer?.cancel();
    setState(() {
      _state = _State.idle;
      _urlCtrl.clear();
      _progress = 0;
      _statusMsg = '';
      _pdfPath = '';
      _errorMsg = '';
    });
  }

  void _snack(String msg) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  // ── Build ─────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('YouTube Doc Agent'), centerTitle: true),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _buildHeader(),
              const SizedBox(height: 32),
              _buildUrlField(),
              const SizedBox(height: 16),
              _buildGenerateButton(),
              const SizedBox(height: 24),
              if (_state == _State.processing)
                ProgressCard(progress: _progress, message: _statusMsg),
              if (_state == _State.done) _buildSuccessCard(),
              if (_state == _State.error) _buildErrorCard(),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildHeader() {
    return Column(
      children: [
        const Icon(Icons.auto_stories, size: 64, color: Color(0xFF1A535C)),
        const SizedBox(height: 12),
        Text(
          'Paste a YouTube link',
          style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                fontWeight: FontWeight.bold,
                color: const Color(0xFF1A535C),
              ),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 8),
        Text(
          'Get a beautiful storybook-style notebook\nof everything discussed in the video.',
          style: Theme.of(context)
              .textTheme
              .bodyMedium
              ?.copyWith(color: Colors.black54),
          textAlign: TextAlign.center,
        ),
      ],
    );
  }

  Widget _buildUrlField() {
    final editable = _state == _State.idle || _state == _State.error;
    return TextField(
      controller: _urlCtrl,
      enabled: editable,
      keyboardType: TextInputType.url,
      decoration: InputDecoration(
        hintText: 'https://youtube.com/watch?v=...',
        prefixIcon: const Icon(Icons.link, color: Color(0xFF1A535C)),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Color(0xFF1A535C), width: 2),
        ),
        filled: true,
        fillColor: Colors.white,
      ),
      onSubmitted: (_) => _generate(),
    );
  }

  Widget _buildGenerateButton() {
    final loading = _state == _State.processing;
    return ElevatedButton.icon(
      onPressed: loading ? null : _generate,
      icon: loading
          ? const SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
            )
          : const Icon(Icons.auto_awesome),
      label: Text(loading ? 'Generating...' : 'Generate Notebook'),
      style: ElevatedButton.styleFrom(
        backgroundColor: const Color(0xFF1A535C),
        foregroundColor: Colors.white,
        disabledBackgroundColor: const Color(0xFF1A535C).withOpacity(0.6),
        padding: const EdgeInsets.symmetric(vertical: 16),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
      ),
    );
  }

  Widget _buildSuccessCard() {
    return Card(
      color: const Color(0xFFE8F5E9),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          children: [
            const Icon(Icons.check_circle, color: Color(0xFF2E7D32), size: 52),
            const SizedBox(height: 12),
            const Text(
              'Your Notebook is Ready! 🎉',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
                color: Color(0xFF2E7D32),
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 20),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: () => Navigator.push(
                      context,
                      MaterialPageRoute(
                        builder: (_) => ViewerScreen(pdfPath: _pdfPath),
                      ),
                    ),
                    icon: const Icon(Icons.picture_as_pdf),
                    label: const Text('View PDF'),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: const Color(0xFF1A535C),
                      side: const BorderSide(color: Color(0xFF1A535C)),
                      padding: const EdgeInsets.symmetric(vertical: 12),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(8)),
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: ElevatedButton.icon(
                    onPressed: _reset,
                    icon: const Icon(Icons.add),
                    label: const Text('New Doc'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF1A535C),
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 12),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(8)),
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildErrorCard() {
    return Card(
      color: const Color(0xFFFFEBEE),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          children: [
            const Icon(Icons.error_outline, color: Color(0xFFC62828), size: 52),
            const SizedBox(height: 12),
            Text(
              _errorMsg,
              style: const TextStyle(fontSize: 14, color: Color(0xFFC62828)),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 16),
            ElevatedButton.icon(
              onPressed: _reset,
              icon: const Icon(Icons.refresh),
              label: const Text('Try Again'),
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFFC62828),
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8)),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
