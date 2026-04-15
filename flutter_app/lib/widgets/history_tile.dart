import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import '../models/doc_history.dart';

class HistoryTile extends StatelessWidget {
  final DocHistory item;
  final VoidCallback onTap;
  final VoidCallback onDelete;

  const HistoryTile({
    super.key,
    required this.item,
    required this.onTap,
    required this.onDelete,
  });

  @override
  Widget build(BuildContext context) {
    return Dismissible(
      key: Key(item.id),
      direction: DismissDirection.endToStart,
      background: Container(
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.symmetric(horizontal: 20),
        decoration: BoxDecoration(
          color: const Color(0xFFC62828),
          borderRadius: BorderRadius.circular(12),
        ),
        child: const Icon(Icons.delete, color: Colors.white),
      ),
      onDismissed: (_) => onDelete(),
      child: Card(
        margin: const EdgeInsets.symmetric(horizontal: 0, vertical: 6),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        child: ListTile(
          contentPadding: const EdgeInsets.all(12),
          onTap: onTap,
          leading: ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: item.thumbnailUrl.isNotEmpty
                ? CachedNetworkImage(
                    imageUrl: item.thumbnailUrl,
                    width: 72,
                    height: 50,
                    fit: BoxFit.cover,
                    errorWidget: (_, __, ___) => _placeholder(),
                    placeholder: (_, __) => _placeholder(),
                  )
                : _placeholder(),
          ),
          title: Text(
            item.title,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
          ),
          subtitle: Text(
            item.formattedDate,
            style: const TextStyle(fontSize: 11, color: Colors.black54),
          ),
          trailing: const Icon(Icons.picture_as_pdf, color: Color(0xFF1A535C)),
        ),
      ),
    );
  }

  Widget _placeholder() {
    return Container(
      width: 72,
      height: 50,
      color: const Color(0xFFE0E0E0),
      child: const Icon(Icons.play_circle_outline, color: Colors.white54),
    );
  }
}
