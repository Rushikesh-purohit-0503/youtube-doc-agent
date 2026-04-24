class DocHistory {
  final String id;
  final String jobId;
  final String title;
  final String thumbnailUrl;
  final String createdAt;
  final String localPdfPath;
  final String localThumbnailPath;

  const DocHistory({
    required this.id,
    required this.jobId,
    required this.title,
    required this.thumbnailUrl,
    required this.createdAt,
    this.localPdfPath = '',
    this.localThumbnailPath = '',
  });

  factory DocHistory.fromJson(Map<String, dynamic> json) {
    return DocHistory(
      id: json['id'] as String,
      jobId: json['job_id'] as String,
      title: json['title'] as String,
      thumbnailUrl: (json['thumbnail_url'] as String?) ?? '',
      createdAt: json['created_at'] as String,
      localPdfPath: (json['local_pdf_path'] as String?) ?? '',
      localThumbnailPath: (json['local_thumbnail_path'] as String?) ?? '',
    );
  }

  factory DocHistory.fromMap(Map<String, dynamic> map) {
    return DocHistory(
      id: map['id'] as String,
      jobId: map['job_id'] as String,
      title: map['title'] as String,
      thumbnailUrl: (map['thumbnail_url'] as String?) ?? '',
      createdAt: map['created_at'] as String,
      localPdfPath: (map['local_pdf_path'] as String?) ?? '',
      localThumbnailPath: (map['local_thumbnail_path'] as String?) ?? '',
    );
  }

  Map<String, dynamic> toMap() => {
        'id': id,
        'job_id': jobId,
        'title': title,
        'thumbnail_url': thumbnailUrl,
        'created_at': createdAt,
        'local_pdf_path': localPdfPath,
        'local_thumbnail_path': localThumbnailPath,
      };

  String get formattedDate {
    try {
      final dt = DateTime.parse(createdAt).toLocal();
      return '${dt.day}/${dt.month}/${dt.year}';
    } catch (_) {
      return createdAt;
    }
  }
}
