import 'dart:io';

import 'package:flutter/material.dart';

import '../models/doc_history.dart';
import '../services/local_history_service.dart';
import '../widgets/history_tile.dart';
import '../widgets/toast.dart';
import 'viewer_screen.dart';

class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key});

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  final _local = LocalHistoryService.instance;
  late Future<List<DocHistory>> _historyFuture;

  @override
  void initState() {
    super.initState();
    _historyFuture = _local.getAll();
  }

  void _refresh() {
    setState(() { _historyFuture = _local.getAll(); });
  }

  Future<void> _delete(DocHistory item) async {
    await _local.delete(item.id);
    if (!mounted) return;
    Toast.show(context, 'Notebook deleted');
    _refresh();
  }

  void _openPdf(DocHistory item) {
    final path = item.localPdfPath;
    if (path.isEmpty || !File(path).existsSync()) {
      Toast.show(context, 'PDF not found — tap to remove', type: ToastType.error);
      _delete(item);
      return;
    }
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => ViewerScreen(pdfPath: path, title: item.title),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('History'),
        centerTitle: true,
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _refresh),
        ],
      ),
      body: FutureBuilder<List<DocHistory>>(
        future: _historyFuture,
        builder: (context, snap) {
          if (snap.connectionState == ConnectionState.waiting) {
            return const Center(
              child: CircularProgressIndicator(
                valueColor: AlwaysStoppedAnimation<Color>(Color(0xFF1A535C)),
              ),
            );
          }

          if (snap.hasError) {
            return Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.error_outline, size: 48, color: Colors.black26),
                  const SizedBox(height: 12),
                  Text(
                    'Could not load history\n${snap.error}',
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: Colors.black54),
                  ),
                  const SizedBox(height: 16),
                  ElevatedButton(
                    onPressed: _refresh,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF1A535C),
                      foregroundColor: Colors.white,
                    ),
                    child: const Text('Retry'),
                  ),
                ],
              ),
            );
          }

          final items = snap.data ?? [];

          if (items.isEmpty) {
            return const Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.book_outlined, size: 64, color: Colors.black26),
                  SizedBox(height: 16),
                  Text(
                    'No notebooks yet.\nGenerate one from a YouTube link!',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Colors.black54, fontSize: 15),
                  ),
                ],
              ),
            );
          }

          return RefreshIndicator(
            onRefresh: () async => _refresh(),
            color: const Color(0xFF1A535C),
            child: ListView.builder(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              itemCount: items.length,
              itemBuilder: (_, i) => HistoryTile(
                item: items[i],
                onTap: () => _openPdf(items[i]),
                onDelete: () => _delete(items[i]),
              ),
            ),
          );
        },
      ),
    );
  }
}
