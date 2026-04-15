class DocHistory {
  final String id;
  final String jobId;
  final String title;
  final String thumbnailUrl;
  final String createdAt;

  const DocHistory({
    required this.id,
    required this.jobId,
    required this.title,
    required this.thumbnailUrl,
    required this.createdAt,
  });

  factory DocHistory.fromJson(Map<String, dynamic> json) {
    return DocHistory(
      id: json['id'] as String,
      jobId: json['job_id'] as String,
      title: json['title'] as String,
      thumbnailUrl: (json['thumbnail_url'] as String?) ?? '',
      createdAt: json['created_at'] as String,
    );
  }

  String get formattedDate {
    try {
      final dt = DateTime.parse(createdAt).toLocal();
      return '${dt.day}/${dt.month}/${dt.year}';
    } catch (_) {
      return createdAt;
    }
  }
}
