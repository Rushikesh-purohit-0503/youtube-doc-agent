import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:purchases_flutter/purchases_flutter.dart';

import '../config/api_config.dart';
import '../services/auth_service.dart';
import '../services/purchase_service.dart';
import '../widgets/toast.dart';

class AccountScreen extends StatefulWidget {
  final VoidCallback onLogout;
  const AccountScreen({super.key, required this.onLogout});

  @override
  State<AccountScreen> createState() => _AccountScreenState();
}

class _AccountScreenState extends State<AccountScreen> {
  bool _loading = true;
  String _error = '';

  // Plan definitions for the upgrade cards
  static const _plans = [
    {
      'id': 'free',
      'label': 'Free',
      'price': 'Free forever',
      'pdfs': '1 PDF / day',
      'color': Color(0xFF607D8B),
      'icon': Icons.article_outlined,
    },
    {
      'id': 'basic',
      'label': 'Basic',
      'price': '\$10 / year',
      'pdfs': '50 PDFs / month',
      'color': Color(0xFF1A535C),
      'icon': Icons.workspace_premium_outlined,
    },
    {
      'id': 'unlimited',
      'label': 'Unlimited',
      'price': '\$100 / year',
      'pdfs': 'Unlimited PDFs',
      'color': Color(0xFFC9A227),
      'icon': Icons.all_inclusive,
    },
  ];

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    setState(() {
      _loading = true;
      _error = '';
    });
    try {
      await AuthService.instance.refreshProfile();
      if (mounted) setState(() => _loading = false);
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString().replaceAll('Exception: ', '');
          _loading = false;
        });
      }
    }
  }

  Future<void> _logout() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Log Out'),
        content: const Text('Are you sure you want to log out?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Log Out', style: TextStyle(color: Colors.red)),
          ),
        ],
      ),
    );
    if (confirmed == true) {
      await Future.wait([
        AuthService.instance.logout(),
        PurchaseService.instance.logout(),
      ]);
      widget.onLogout();
    }
  }

  void _onUpgradeTap(String planId) {
    if (planId == AuthService.instance.plan) return;
    if (ApiConfig.isDev) {
      _devSetPlan(planId);
      return;
    }
    _showUpgradeSheet(planId);
  }

  Future<void> _showUpgradeSheet(String planId) async {
    // Fetch real price from RevenueCat before showing sheet
    final offerings = await PurchaseService.instance.getOfferings();
    final suffix = planId == 'basic' ? 'basic_yearly' : 'unlimited_yearly';
    Package? package;
    try {
      package = offerings?.current?.availablePackages.firstWhere(
        (p) => p.storeProduct.identifier.contains(suffix),
      );
    } catch (_) {}

    if (!mounted) return;

    final planMeta = _plans.firstWhere((p) => p['id'] == planId);
    final color = planMeta['color'] as Color;
    final label = planMeta['label'] as String;
    final pdfs = planMeta['pdfs'] as String;
    final displayPrice =
        package?.storeProduct.priceString ?? planMeta['price'] as String;

    await showModalBottomSheet(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (_) => Padding(
        padding: const EdgeInsets.fromLTRB(24, 20, 24, 36),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: Colors.black12,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const SizedBox(height: 20),
            Icon(planMeta['icon'] as IconData, color: color, size: 40),
            const SizedBox(height: 12),
            Text(
              'Upgrade to $label',
              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 6),
            Text(
              pdfs,
              style: const TextStyle(fontSize: 14, color: Colors.black54),
            ),
            const SizedBox(height: 24),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: package == null
                    ? null
                    : () {
                        Navigator.pop(context);
                        _executePurchase(package!);
                      },
                style: ElevatedButton.styleFrom(
                  backgroundColor: color,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(14)),
                ),
                child: Text(
                  package == null
                      ? 'Unavailable'
                      : 'Subscribe for $displayPrice / year',
                  style: const TextStyle(
                      fontSize: 16, fontWeight: FontWeight.w700),
                ),
              ),
            ),
            const SizedBox(height: 12),
            const Text(
              'Auto-renews yearly. Cancel anytime in App Store settings.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 11, color: Colors.black38),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _executePurchase(Package package) async {
    setState(() => _loading = true);
    try {
      await PurchaseService.instance.purchase(package);
      await _refresh();
      if (mounted) Toast.show(context, 'Purchase successful! Plan updated.', type: ToastType.success);
    } on PurchasesErrorCode catch (e) {
      if (e == PurchasesErrorCode.purchaseCancelledError) {
        setState(() => _loading = false);
        return;
      }
      if (mounted) Toast.show(context, 'Purchase failed: ${e.name}', type: ToastType.error);
    } catch (e) {
      if (mounted) Toast.show(context, e.toString().replaceAll('Exception: ', ''), type: ToastType.error);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _restorePurchases() async {
    setState(() => _loading = true);
    try {
      final plan = await PurchaseService.instance.restorePurchases();
      await _refresh();
      if (mounted) {
        Toast.show(
          context,
          plan == 'free' ? 'No active subscriptions found.' : 'Purchases restored.',
          type: plan == 'free' ? ToastType.info : ToastType.success,
        );
      }
    } catch (e) {
      if (mounted) Toast.show(context, 'Restore failed: $e', type: ToastType.error);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _devSetPlan(String plan) async {
    try {
      final resp = await http
          .post(
            Uri.parse('${ApiConfig.baseUrl}/dev/set-plan'),
            headers: AuthService.instance.authHeaders,
            body: jsonEncode({'plan': plan}),
          )
          .timeout(const Duration(seconds: 10));
      if (resp.statusCode == 200) {
        await _refresh();
        if (mounted) Toast.show(context, 'Plan set to $plan', type: ToastType.success);
      }
    } catch (_) {}
  }

  Future<void> _devResetUsage() async {
    try {
      await http
          .post(
            Uri.parse('${ApiConfig.baseUrl}/dev/reset-usage'),
            headers: AuthService.instance.authHeaders,
          )
          .timeout(const Duration(seconds: 10));
      await _refresh();
      if (mounted) Toast.show(context, 'Usage reset to 0', type: ToastType.success);
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Account'),
        centerTitle: true,
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loading ? null : _refresh,
          ),
        ],
      ),
      body: _loading
          ? const Center(
              child: CircularProgressIndicator(color: Color(0xFF1A535C)),
            )
          : _error.isNotEmpty
              ? _buildError()
              : _buildContent(),
    );
  }

  Widget _buildError() {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(_error, style: const TextStyle(color: Colors.red)),
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

  Widget _buildContent() {
    final auth = AuthService.instance;
    final currentPlan = auth.plan ?? 'free';
    final used = auth.monthlyUsed;
    final limit = auth.monthlyLimit;
    final isUnlimited = limit == -1;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // User info
          Card(
            shape:
                RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Row(
                children: [
                  CircleAvatar(
                    radius: 26,
                    backgroundColor: const Color(0xFF1A535C),
                    child: Text(
                      (auth.email ?? '?')[0].toUpperCase(),
                      style: const TextStyle(
                        fontSize: 22,
                        fontWeight: FontWeight.bold,
                        color: Colors.white,
                      ),
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          auth.email ?? '',
                          style: const TextStyle(
                            fontWeight: FontWeight.w600,
                            fontSize: 14,
                          ),
                          overflow: TextOverflow.ellipsis,
                        ),
                        const SizedBox(height: 4),
                        _planBadge(currentPlan),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),

          // Usage card
          Card(
            shape:
                RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Monthly Usage',
                    style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
                  ),
                  const SizedBox(height: 14),
                  if (isUnlimited)
                    const Row(
                      children: [
                        Icon(Icons.all_inclusive, color: Color(0xFF1A535C)),
                        SizedBox(width: 8),
                        Text(
                          'Unlimited PDFs',
                          style: TextStyle(fontSize: 14, color: Colors.black54),
                        ),
                      ],
                    )
                  else ...[
                    ClipRRect(
                      borderRadius: BorderRadius.circular(6),
                      child: LinearProgressIndicator(
                        value: limit > 0 ? (used / limit).clamp(0.0, 1.0) : 0,
                        minHeight: 10,
                        backgroundColor: Colors.grey[200],
                        valueColor: AlwaysStoppedAnimation<Color>(
                          used >= limit
                              ? const Color(0xFFC62828)
                              : const Color(0xFF4ECDC4),
                        ),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      currentPlan == 'free'
                          ? '$used of $limit PDFs used today'
                          : '$used of $limit PDFs used this month',
                      style:
                          const TextStyle(fontSize: 13, color: Colors.black54),
                    ),
                  ],
                ],
              ),
            ),
          ),
          const SizedBox(height: 24),

          const Text(
            'Plans',
            style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
          ),
          const SizedBox(height: 12),

          // Plan cards
          ..._plans.map((p) {
            final planId = p['id'] as String;
            final isCurrent = planId == currentPlan;
            final color = p['color'] as Color;
            return Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: isCurrent ? color : Colors.white,
                  border: Border.all(
                    color: isCurrent ? color : Colors.black12,
                    width: isCurrent ? 2 : 1,
                  ),
                  borderRadius: BorderRadius.circular(14),
                  boxShadow: isCurrent
                      ? [
                          BoxShadow(
                              color: color.withOpacity(0.2),
                              blurRadius: 8,
                              offset: const Offset(0, 3))
                        ]
                      : [],
                ),
                child: Row(
                  children: [
                    Icon(p['icon'] as IconData,
                        color: isCurrent ? Colors.white : color, size: 28),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            p['label'] as String,
                            style: TextStyle(
                              fontWeight: FontWeight.w700,
                              fontSize: 15,
                              color: isCurrent ? Colors.white : Colors.black87,
                            ),
                          ),
                          Text(
                            p['pdfs'] as String,
                            style: TextStyle(
                              fontSize: 12,
                              color:
                                  isCurrent ? Colors.white70 : Colors.black54,
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (isCurrent) ...[
                      Text(
                        p['price'] as String,
                        style: const TextStyle(
                          fontWeight: FontWeight.w600,
                          fontSize: 13,
                          color: Colors.white,
                        ),
                      ),
                      const SizedBox(width: 8),
                      const Icon(Icons.check_circle,
                          color: Colors.white, size: 18),
                    ] else if (planId != 'free') ...[
                      ElevatedButton(
                        onPressed: () => _onUpgradeTap(planId),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: color,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(
                              horizontal: 14, vertical: 8),
                          minimumSize: Size.zero,
                          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                          shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(8)),
                          textStyle: const TextStyle(
                              fontSize: 12, fontWeight: FontWeight.w700),
                        ),
                        child: const Text('Upgrade'),
                      ),
                    ],
                  ],
                ),
              ),
            );
          }),
          const SizedBox(height: 32),

          // Dev payment panel — only visible when ApiConfig.isDev == true
          if (ApiConfig.isDev) _buildDevPanel(),
          if (ApiConfig.isDev) const SizedBox(height: 24),

          // Restore purchases (required by App Store)
          if (!ApiConfig.isDev) ...[
            TextButton(
              onPressed: _loading ? null : _restorePurchases,
              child: const Text(
                'Restore Purchases',
                style: TextStyle(color: Colors.black45, fontSize: 13),
              ),
            ),
            const SizedBox(height: 8),
          ],

          // Logout
          OutlinedButton.icon(
            onPressed: _logout,
            icon: const Icon(Icons.logout),
            label: const Text('Log Out'),
            style: OutlinedButton.styleFrom(
              foregroundColor: Colors.red,
              side: const BorderSide(color: Colors.red),
              padding: const EdgeInsets.symmetric(vertical: 14),
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12)),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDevPanel() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF3E0),
        border: Border.all(color: Colors.orange.shade300),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.construction, size: 16, color: Colors.orange),
              SizedBox(width: 6),
              Text(
                'Dev Payment Simulator',
                style: TextStyle(
                  fontWeight: FontWeight.w700,
                  fontSize: 13,
                  color: Colors.orange,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _devBtn('→ Free', () => _devSetPlan('free'), Colors.grey),
              _devBtn('→ Basic', () => _devSetPlan('basic'),
                  const Color(0xFF1A535C)),
              _devBtn('→ Unlimited', () => _devSetPlan('unlimited'),
                  const Color(0xFFC9A227)),
              _devBtn('Reset Usage', _devResetUsage, Colors.red),
            ],
          ),
        ],
      ),
    );
  }

  Widget _devBtn(String label, VoidCallback onTap, Color color) {
    return OutlinedButton(
      onPressed: onTap,
      style: OutlinedButton.styleFrom(
        foregroundColor: color,
        side: BorderSide(color: color),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        minimumSize: Size.zero,
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        textStyle: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
      ),
      child: Text(label),
    );
  }

  Widget _planBadge(String plan) {
    final (label, color) = switch (plan) {
      'basic' => ('Basic', const Color(0xFF1A535C)),
      'unlimited' => ('Unlimited', const Color(0xFFC9A227)),
      _ => ('Free', const Color(0xFF607D8B)),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withOpacity(0.12),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        label,
        style:
            TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: color),
      ),
    );
  }
}
