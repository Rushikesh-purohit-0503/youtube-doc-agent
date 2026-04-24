import 'dart:io';

/// Base URL of the Python FastAPI backend.
///
/// When running on a real device, replace with your machine's LAN IP:
///   e.g. 'http://192.168.1.42:8000'
///
/// When running on an Android emulator use: 'http://10.0.2.2:8000'
/// When running on an iOS simulator use:    'http://127.0.0.1:8000'
class ApiConfig {
  static const String baseUrl = 'http://127.0.0.1:8000';

  /// RevenueCat public SDK keys — one per platform.
  /// Get from RevenueCat dashboard → Project → Apps.
  static String get revenueCatApiKey => Platform.isIOS
      ? 'appl_REPLACE_WITH_IOS_KEY'
      : 'goog_REPLACE_WITH_ANDROID_KEY';

  /// Populated at startup from GET /config. False until fetched.
  static bool isDev = false;
}
