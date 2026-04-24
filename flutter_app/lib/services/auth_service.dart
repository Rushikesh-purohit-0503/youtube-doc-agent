import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

import '../config/api_config.dart';

class AuthService {
  AuthService._();
  static final AuthService instance = AuthService._();

  static const _storage = FlutterSecureStorage();
  static const _tokenKey = 'jwt_token';
  static const _userIdKey = 'user_id';
  static const _emailKey = 'email';
  static const _planKey = 'plan';
  static const _limitKey = 'monthly_limit';
  static const _usedKey = 'monthly_used';

  String? _token;
  String? _userId;
  String? _email;
  String? _plan;
  int _monthlyLimit = 1;
  int _monthlyUsed = 0;

  String? get token => _token;
  String? get userId => _userId;
  String? get email => _email;
  String? get plan => _plan;
  int get monthlyLimit => _monthlyLimit;
  int get monthlyUsed => _monthlyUsed;
  bool get isLoggedIn => _token != null;

  /// Call once at app startup to restore persisted session.
  Future<void> init() async {
    _token = await _storage.read(key: _tokenKey);
    _userId = await _storage.read(key: _userIdKey);
    _email = await _storage.read(key: _emailKey);
    _plan = await _storage.read(key: _planKey);
    _monthlyLimit = int.tryParse(await _storage.read(key: _limitKey) ?? '1') ?? 1;
    _monthlyUsed = int.tryParse(await _storage.read(key: _usedKey) ?? '0') ?? 0;
  }

  Future<void> register(String email, String password) async {
    final resp = await http.post(
      Uri.parse('${ApiConfig.baseUrl}/auth/register'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'email': email, 'password': password}),
    ).timeout(const Duration(seconds: 15));

    if (resp.statusCode == 200) {
      await _persist(jsonDecode(resp.body) as Map<String, dynamic>);
      return;
    }
    throw Exception(_extractDetail(resp));
  }

  Future<void> login(String email, String password) async {
    final resp = await http.post(
      Uri.parse('${ApiConfig.baseUrl}/auth/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'email': email, 'password': password}),
    ).timeout(const Duration(seconds: 15));

    if (resp.statusCode == 200) {
      await _persist(jsonDecode(resp.body) as Map<String, dynamic>);
      return;
    }
    throw Exception(_extractDetail(resp));
  }

  /// Fetches fresh profile from server (plan + usage). Call on Account tab open.
  Future<void> refreshProfile() async {
    final resp = await http.get(
      Uri.parse('${ApiConfig.baseUrl}/auth/me'),
      headers: authHeaders,
    ).timeout(const Duration(seconds: 10));

    if (resp.statusCode == 200) {
      await _persist(jsonDecode(resp.body) as Map<String, dynamic>);
      return;
    }
    if (resp.statusCode == 401) {
      await logout();
      throw Exception('Session expired. Please log in again.');
    }
    throw Exception('Failed to fetch profile');
  }

  Future<void> logout() async {
    _token = null;
    _userId = null;
    _email = null;
    _plan = null;
    _monthlyLimit = 1;
    _monthlyUsed = 0;
    await _storage.deleteAll();
  }

  Map<String, String> get authHeaders => {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer $_token',
  };

  Future<void> _persist(Map<String, dynamic> data) async {
    _token = data['token'] as String;
    _userId = data['user_id'] as String;
    _email = data['email'] as String;
    _plan = data['plan'] as String;
    _monthlyLimit = data['monthly_limit'] as int? ?? 1;
    _monthlyUsed = data['monthly_used'] as int? ?? 0;
    await _storage.write(key: _tokenKey, value: _token!);
    await _storage.write(key: _userIdKey, value: _userId!);
    await _storage.write(key: _emailKey, value: _email!);
    await _storage.write(key: _planKey, value: _plan!);
    await _storage.write(key: _limitKey, value: _monthlyLimit.toString());
    await _storage.write(key: _usedKey, value: _monthlyUsed.toString());
  }

  String _extractDetail(http.Response resp) {
    try {
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      return (body['detail'] as String?) ?? 'Request failed';
    } catch (_) {
      return 'Request failed (${resp.statusCode})';
    }
  }
}
