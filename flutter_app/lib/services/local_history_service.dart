import 'dart:io';

import 'package:path/path.dart';
import 'package:sqflite/sqflite.dart';

import '../models/doc_history.dart';

class LocalHistoryService {
  LocalHistoryService._();
  static final LocalHistoryService instance = LocalHistoryService._();

  Database? _db;

  Future<Database> get _database async {
    _db ??= await _initDb();
    return _db!;
  }

  Future<Database> _initDb() async {
    final dbPath = join(await getDatabasesPath(), 'local_history.db');
    return openDatabase(
      dbPath,
      version: 2,
      onCreate: (db, _) => db.execute('''
        CREATE TABLE history (
          id                    TEXT PRIMARY KEY,
          job_id                TEXT NOT NULL,
          title                 TEXT NOT NULL,
          thumbnail_url         TEXT,
          local_pdf_path        TEXT,
          local_thumbnail_path  TEXT,
          created_at            TEXT NOT NULL
        )
      '''),
      onUpgrade: (db, oldVersion, newVersion) async {
        if (oldVersion < 2) {
          // Check if column already exists before adding it
          final cols = await db.rawQuery('PRAGMA table_info(history)');
          final names = cols.map((c) => c['name'] as String).toSet();
          if (!names.contains('local_thumbnail_path')) {
            await db.execute(
              'ALTER TABLE history ADD COLUMN local_thumbnail_path TEXT',
            );
          }
        }
      },
    );
  }

  Future<void> save(DocHistory item) async {
    final db = await _database;
    await db.insert(
      'history',
      item.toMap(),
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<List<DocHistory>> getAll() async {
    final db = await _database;
    final rows = await db.query('history', orderBy: 'created_at DESC');
    return rows.map(DocHistory.fromMap).toList();
  }

  Future<void> delete(String id) async {
    final db = await _database;
    final rows = await db.query('history', where: 'id = ?', whereArgs: [id]);
    if (rows.isNotEmpty) {
      final pdfPath = rows.first['local_pdf_path'] as String?;
      if (pdfPath != null && pdfPath.isNotEmpty) {
        final file = File(pdfPath);
        if (await file.exists()) await file.delete();
      }
      final thumbPath = rows.first['local_thumbnail_path'] as String?;
      if (thumbPath != null && thumbPath.isNotEmpty) {
        final file = File(thumbPath);
        if (await file.exists()) await file.delete();
      }
    }
    await db.delete('history', where: 'id = ?', whereArgs: [id]);
  }
}
