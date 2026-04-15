import 'package:flutter/material.dart';

class ProgressCard extends StatelessWidget {
  final int progress;
  final String message;

  const ProgressCard({super.key, required this.progress, required this.message});

  String get _stageLabel {
    if (progress <= 10) return 'Fetching transcript...';
    if (progress <= 30) return 'Chunking content...';
    if (progress <= 79) return 'AI processing (parallel)...';
    if (progress <= 89) return 'Assembling notebook...';
    if (progress <= 99) return 'Generating PDF...';
    return 'Done!';
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(
                    strokeWidth: 2.5,
                    valueColor: AlwaysStoppedAnimation<Color>(Color(0xFF1A535C)),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    _stageLabel,
                    style: const TextStyle(
                      fontWeight: FontWeight.bold,
                      fontSize: 14,
                      color: Color(0xFF1A535C),
                    ),
                  ),
                ),
                Text(
                  '$progress%',
                  style: const TextStyle(
                    fontWeight: FontWeight.bold,
                    color: Color(0xFF1A535C),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: LinearProgressIndicator(
                value: progress / 100,
                minHeight: 8,
                backgroundColor: const Color(0xFFE0E0E0),
                valueColor: const AlwaysStoppedAnimation<Color>(Color(0xFF4ECDC4)),
              ),
            ),
            const SizedBox(height: 10),
            Text(
              message,
              style: const TextStyle(fontSize: 12, color: Colors.black54),
            ),
          ],
        ),
      ),
    );
  }
}
