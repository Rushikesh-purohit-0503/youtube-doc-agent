import 'package:flutter/material.dart';

import 'screens/account_screen.dart';
import 'screens/auth_screen.dart';
import 'screens/history_screen.dart';
import 'screens/home_screen.dart';
import 'services/api_service.dart';
import 'services/auth_service.dart';
import 'services/purchase_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Future.wait([
    AuthService.instance.init(),
    ApiService.instance.fetchConfig(),
  ]);
  await PurchaseService.instance.init();
  runApp(const YoutubeDocApp());
}

class YoutubeDocApp extends StatelessWidget {
  const YoutubeDocApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'DocTube',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF1A535C),
          brightness: Brightness.light,
        ),
        useMaterial3: true,
        scaffoldBackgroundColor: const Color(0xFFFFF8E7),
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xFF1A535C),
          foregroundColor: Colors.white,
          elevation: 0,
        ),
        cardTheme: const CardThemeData(
          color: Colors.white,
          elevation: 1,
        ),
      ),
      home: const _AppRoot(),
    );
  }
}

class _AppRoot extends StatefulWidget {
  const _AppRoot();

  @override
  State<_AppRoot> createState() => _AppRootState();
}

class _AppRootState extends State<_AppRoot> {
  @override
  Widget build(BuildContext context) {
    if (!AuthService.instance.isLoggedIn) {
      return AuthScreen(onAuthenticated: () => setState(() {}));
    }
    return _MainNav(onLogout: () => setState(() {}));
  }
}

class _MainNav extends StatefulWidget {
  final VoidCallback onLogout;
  const _MainNav({required this.onLogout});

  @override
  State<_MainNav> createState() => _MainNavState();
}

class _MainNavState extends State<_MainNav> {
  int _idx = 0;
  int _historyRebuildKey = 0;
  int _accountRebuildKey = 0;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(
        index: _idx,
        children: [
          const HomeScreen(),
          HistoryScreen(key: ValueKey(_historyRebuildKey)),
          AccountScreen(
            key: ValueKey(_accountRebuildKey),
            onLogout: widget.onLogout,
          ),
        ],
      ),
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _idx,
        onTap: (i) {
          if (i == 1) _historyRebuildKey++;
          if (i == 2) _accountRebuildKey++;
          setState(() => _idx = i);
        },
        backgroundColor: const Color(0xFF1A535C),
        selectedItemColor: const Color(0xFF4ECDC4),
        unselectedItemColor: Colors.white54,
        items: const [
          BottomNavigationBarItem(icon: Icon(Icons.auto_awesome), label: 'Generate'),
          BottomNavigationBarItem(icon: Icon(Icons.history), label: 'History'),
          BottomNavigationBarItem(icon: Icon(Icons.person_outline), label: 'Account'),
        ],
      ),
    );
  }
}
