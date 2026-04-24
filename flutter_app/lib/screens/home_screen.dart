import 'dart:async';

import 'package:flutter/material.dart';

import '../models/doc_history.dart';
import '../services/api_service.dart';
import '../services/local_history_service.dart';
import '../widgets/progress_card.dart';
import '../widgets/toast.dart';
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
  String _videoTitle = '';
  String _thumbnailUrl = '';
  int _progress = 0;

  /// Extract video ID and build thumbnail URL client-side so we never depend
  /// on the server polling it through. Falls back to empty string if unknown format.
  static String _thumbnailFromUrl(String youtubeUrl) {
    final patterns = [
      RegExp(r'[?&]v=([^&\n?#\s]+)'),
      RegExp(r'youtu\.be/([^&\n?#\s]+)'),
      RegExp(r'youtube\.com/shorts/([^&\n?#\s]+)'),
      RegExp(r'youtube\.com/embed/([^&\n?#\s]+)'),
    ];
    for (final p in patterns) {
      final m = p.firstMatch(youtubeUrl);
      if (m != null)
        return 'https://img.youtube.com/vi/${m.group(1)}/hqdefault.jpg';
    }
    return '';
  }

  String _pdfPath = '';
  String _errorMsg = '';
  String _selectedTemplate = 'storybook';
  Timer? _pollTimer;

  static const _templates = [
    {
      'id': 'storybook',
      'label': 'Storybook',
      'emoji': '📚',
      'color': Color(0xFF1A535C)
    },
    {
      'id': 'professional',
      'label': 'Professional',
      'emoji': '💼',
      'color': Color(0xFF1B2A4A)
    },
    {
      'id': 'academic',
      'label': 'Academic',
      'emoji': '🎓',
      'color': Color(0xFF5C3317)
    },
    {
      'id': 'minimal',
      'label': 'Minimal',
      'emoji': '◻',
      'color': Color(0xFF444444)
    },
  ];

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

    _thumbnailUrl = _thumbnailFromUrl(url);
    setState(() {
      _state = _State.processing;
      _progress = 0;
      _statusMsg = 'Starting...';
      _errorMsg = '';
    });

    try {
      _jobId = await _api.generateDoc(url, template: _selectedTemplate);
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

        // Capture title/thumbnail as soon as they appear in status
        if (status['title'] != null) _videoTitle = status['title'] as String;
        if (status['thumbnail_url'] != null)
          _thumbnailUrl = status['thumbnail_url'] as String;

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

      // Download thumbnail to device so it renders without network dependency
      final localThumb = await _api.downloadThumbnail(_thumbnailUrl, _jobId);

      // Save to local history so it's accessible offline forever
      await LocalHistoryService.instance.save(DocHistory(
        id: _jobId,
        jobId: _jobId,
        title: _videoTitle.isEmpty ? 'Notebook' : _videoTitle,
        thumbnailUrl: _thumbnailUrl,
        localPdfPath: path,
        localThumbnailPath: localThumb,
        createdAt: DateTime.now().toUtc().toIso8601String(),
      ));

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
    _videoTitle = '';
    _thumbnailUrl = '';
    _jobId = '';
    setState(() {
      _state = _State.idle;
      _urlCtrl.clear();
      _progress = 0;
      _statusMsg = '';
      _pdfPath = '';
      _errorMsg = '';
    });
  }

  void _snack(String msg, {ToastType type = ToastType.info}) {
    Toast.show(context, msg, type: type);
  }

  // ── Build ─────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('DocTube'), centerTitle: true),
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
              _buildTemplatePicker(),
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
      onSubmitted: (_) {
        if (_state == _State.idle || _state == _State.error) _generate();
      },
    );
  }

  Widget _buildTemplatePicker() {
    final enabled = _state == _State.idle || _state == _State.error;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Template',
          style: TextStyle(
              fontWeight: FontWeight.w600, fontSize: 13, color: Colors.black54),
        ),
        const SizedBox(height: 8),
        SizedBox(
          height: 72,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            itemCount: _templates.length,
            separatorBuilder: (_, __) => const SizedBox(width: 10),
            itemBuilder: (_, i) {
              final t = _templates[i];
              final selected = _selectedTemplate == t['id'];
              final color = t['color'] as Color;
              return GestureDetector(
                onTap: enabled
                    ? () =>
                        setState(() => _selectedTemplate = t['id'] as String)
                    : null,
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 180),
                  width: 100,
                  decoration: BoxDecoration(
                    color: selected ? color : Colors.white,
                    border: Border.all(
                      color: selected ? color : Colors.black12,
                      width: selected ? 2 : 1,
                    ),
                    borderRadius: BorderRadius.circular(12),
                    boxShadow: selected
                        ? [
                            BoxShadow(
                                color: color.withOpacity(0.25),
                                blurRadius: 6,
                                offset: const Offset(0, 3))
                          ]
                        : [],
                  ),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(t['emoji'] as String,
                          style: const TextStyle(fontSize: 22)),
                      const SizedBox(height: 4),
                      Text(
                        t['label'] as String,
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                          color: selected ? Colors.white : Colors.black87,
                        ),
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
        ),
      ],
    );
  }

  Widget _buildGenerateButton() {
    final loading = _state == _State.processing;
    final done = _state == _State.done;
    return ElevatedButton.icon(
      onPressed: (loading || done) ? null : _generate,
      icon: const Icon(Icons.auto_awesome),
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
