import 'package:purchases_flutter/purchases_flutter.dart';

import '../config/api_config.dart';
import 'auth_service.dart';

/// Maps internal plan IDs → RevenueCat entitlement identifiers.
const _entitlements = {
  'basic': 'basic',
  'unlimited': 'unlimited',
};

class PurchaseService {
  PurchaseService._();
  static final PurchaseService instance = PurchaseService._();

  bool _configured = false;

  /// Call once after AuthService.init() — sets RevenueCat user ID.
  Future<void> init() async {
    if (_isPlaceholderKey) return; // skip until real key is set
    try {
      await Purchases.setLogLevel(LogLevel.error);
      final config = PurchasesConfiguration(ApiConfig.revenueCatApiKey);
      await Purchases.configure(config);
      _configured = true;
      final userId = AuthService.instance.userId;
      if (userId != null) {
        await Purchases.logIn(userId);
      }
    } catch (_) {
      // Non-fatal — purchase features unavailable until key is set
    }
  }

  bool get _isPlaceholderKey =>
      ApiConfig.revenueCatApiKey.contains('REPLACE_WITH');

  /// Log in RevenueCat with current user after auth.
  Future<void> login(String userId) async {
    if (!_configured) return;
    try { await Purchases.logIn(userId); } catch (_) {}
  }

  Future<void> logout() async {
    if (!_configured) return;
    try { await Purchases.logOut(); } catch (_) {}
  }

  /// Fetches available offerings from RevenueCat.
  Future<Offerings?> getOfferings() async {
    if (!_configured) return null;
    try {
      return await Purchases.getOfferings();
    } catch (_) {
      return null;
    }
  }

  /// Purchase a package. Returns updated plan on success, throws on failure.
  Future<String> purchase(Package package) async {
    final result = await Purchases.purchasePackage(package);
    // Find which entitlement is now active
    for (final entry in _entitlements.entries) {
      if (result.entitlements.active.containsKey(entry.value)) {
        return entry.key; // 'basic' or 'unlimited'
      }
    }
    return 'free';
  }

  /// Restore previous purchases (required by App Store guidelines).
  Future<String> restorePurchases() async {
    final info = await Purchases.restorePurchases();
    for (final entry in _entitlements.entries) {
      if (info.entitlements.active.containsKey(entry.value)) {
        return entry.key;
      }
    }
    return 'free';
  }
}
