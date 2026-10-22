import 'dart:convert';

import 'package:diary_app/api.dart';
import 'package:diary_app/format.dart';
import 'package:diary_app/main.dart';
import 'package:diary_app/models.dart';
import 'package:diary_app/new_share_screen.dart';
import 'package:diary_app/sharing_screen.dart';
import 'package:diary_app/theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const hofmann = {'id': 1, 'name': 'Dr. Lena Hofmann', 'practice': 'Praxis Hofmann, München'};
const braun = {'id': 2, 'name': 'Dr. Felix Braun', 'practice': 'Hausarztpraxis Schwabing'};

/// An in-memory stand-in for the sharing API.
class FakeSharingApi {
  FakeSharingApi({List<Map<String, dynamic>>? shares, List<Map<String, dynamic>>? accessLog})
    : shares = shares ?? [],
      accessLog = accessLog ?? [];

  final List<Map<String, dynamic>> shares;
  final List<Map<String, dynamic>> accessLog;
  final requests = <http.Request>[];

  late final api = ApiClient(client: MockClient(_handle));

  Iterable<String> get events => requests
      .where((r) => r.url.path.endsWith('/telemetry'))
      .map((r) => jsonDecode(r.body)['event'] as String);

  Map<String, dynamic> get created => jsonDecode(
    requests.singleWhere((r) => r.method == 'POST' && r.url.path.endsWith('/shares')).body,
  );

  Future<http.Response> _handle(http.Request request) async {
    requests.add(request);
    final path = request.url.path;
    final revoke = RegExp(r'/shares/(\d+)/revoke$').firstMatch(path);
    if (request.method == 'GET' && path.endsWith('/entries')) return _json([]);
    if (request.method == 'GET' && path.endsWith('/clinicians')) return _json([braun, hofmann]);
    if (request.method == 'GET' && path.endsWith('/shares')) return _json(shares);
    if (request.method == 'GET' && path.endsWith('/access-log')) return _json(accessLog);
    if (request.method == 'POST' && path.endsWith('/shares')) {
      final share = {
        ...jsonDecode(request.body) as Map<String, dynamic>,
        'id': shares.length + 1,
        'created_at': '2026-10-08T09:12:00Z',
        'revoked_at': null,
      };
      shares.insert(0, share);
      return _json(share, 201);
    }
    if (request.method == 'POST' && revoke != null) {
      final share = shares.singleWhere((s) => s['id'] == int.parse(revoke.group(1)!));
      share['revoked_at'] = '2026-10-09T10:00:00Z';
      return _json(share);
    }
    if (request.method == 'POST' && path.endsWith('/telemetry')) return http.Response('', 204);
    return http.Response('Not found', 404);
  }

  http.Response _json(Object body, [int status = 200]) =>
      http.Response.bytes(utf8.encode(jsonEncode(body)), status);
}

Map<String, dynamic> shareJson({
  int id = 1,
  int clinicianId = 1,
  required DateTime from,
  required DateTime to,
  bool includeNotes = false,
}) => {
  'id': id,
  'clinician_id': clinicianId,
  'from_date': formatIsoDate(from),
  'to_date': formatIsoDate(to),
  'include_notes': includeNotes,
  'created_at': '2026-10-08T09:12:00Z',
  'revoked_at': null,
};

DateTime get today => dayOf(DateTime.now());
DateTime get sixDaysAgo => DateTime(today.year, today.month, today.day - 6);

Future<void> pumpSharing(WidgetTester tester, FakeSharingApi fake) async {
  tester.view.physicalSize = const Size(800, 2400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      theme: buildTheme(),
      home: SharingScreen(api: fake.api),
    ),
  );
  await tester.pumpAndSettle();
}

/// Walks through the new-share flow up to the confirmation step.
Future<void> startSharingWith(WidgetTester tester, String doctor, {bool notes = false}) async {
  await tester.tap(find.text('Share with a doctor'));
  await tester.pumpAndSettle();
  await tester.tap(find.text(doctor));
  if (notes) await tester.tap(find.text('Also share my notes'));
  await tester.pump();
  await tester.tap(find.text('Continue'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('opens sharing from the diary', (tester) async {
    final fake = FakeSharingApi();
    tester.view.physicalSize = const Size(800, 2400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(DiaryApp(api: fake.api));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Share with your doctor'));
    await tester.pumpAndSettle();

    expect(find.text("You're not sharing your diary"), findsOneWidget);
    expect(find.text('Nobody has opened your diary yet.'), findsOneWidget);
    expect(fake.events, contains('sharing_opened'));
  });

  testWidgets('shares mood and symptoms for the last 7 days after showing what is shared', (
    tester,
  ) async {
    final fake = FakeSharingApi();
    await pumpSharing(tester, fake);

    await tester.tap(find.text('Share with a doctor'));
    await tester.pumpAndSettle();
    final continueButton = find.widgetWithText(FilledButton, 'Continue');
    expect(tester.widget<FilledButton>(continueButton).onPressed, isNull);

    await tester.tap(find.text('Dr. Lena Hofmann'));
    await tester.pump();
    await tester.tap(continueButton);
    await tester.pumpAndSettle();

    expect(find.text('Check before you share'), findsOneWidget);
    expect(find.text('Dr. Lena Hofmann'), findsOneWidget);
    expect(find.text('Your mood and symptoms. Your notes stay private.'), findsOneWidget);
    expect(find.text(formatPeriod(sixDaysAgo, today)), findsOneWidget);

    await tester.tap(find.text('Share my diary'));
    await tester.pumpAndSettle();

    expect(fake.created, {
      'clinician_id': 1,
      'from_date': formatIsoDate(sixDaysAgo),
      'to_date': formatIsoDate(today),
      'include_notes': false,
    });
    expect(fake.events, contains('share_created'));
    expect(find.text('Dr. Lena Hofmann'), findsOneWidget);
    expect(find.text('Mood and symptoms'), findsOneWidget);
    expect(find.text('Shared on 8 Oct'), findsOneWidget);
  });

  testWidgets('includes notes only when the patient turns them on', (tester) async {
    final fake = FakeSharingApi();
    await pumpSharing(tester, fake);

    await startSharingWith(tester, 'Dr. Felix Braun', notes: true);
    expect(find.text('Your mood, symptoms and notes'), findsOneWidget);
    await tester.tap(find.text('Share my diary'));
    await tester.pumpAndSettle();

    expect(fake.created['clinician_id'], 2);
    expect(fake.created['include_notes'], isTrue);
    expect(find.text('Mood, symptoms and notes'), findsOneWidget);
  });

  testWidgets('warns when a new share adds notes to days already shared', (tester) async {
    final fake = FakeSharingApi(
      shares: [shareJson(from: sixDaysAgo, to: today)],
    );
    await pumpSharing(tester, fake);

    await startSharingWith(tester, 'Dr. Lena Hofmann', notes: true);

    expect(find.textContaining('Dr. Lena Hofmann will also see your notes'), findsOneWidget);
  });

  testWidgets('stops sharing only after the patient confirms', (tester) async {
    final fake = FakeSharingApi(
      shares: [shareJson(from: sixDaysAgo, to: today)],
    );
    await pumpSharing(tester, fake);
    bool revoked() => fake.requests.any((r) => r.url.path.endsWith('/revoke'));

    await tester.tap(find.text('Stop sharing'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Keep sharing'));
    await tester.pumpAndSettle();
    expect(revoked(), isFalse);

    await tester.tap(find.text('Stop sharing'));
    await tester.pumpAndSettle();
    expect(find.text('Stop sharing with Dr. Lena Hofmann?'), findsOneWidget);
    await tester.tap(find.text('Stop sharing').last);
    await tester.pumpAndSettle();

    expect(revoked(), isTrue);
    expect(fake.events, contains('share_revoked'));
    expect(find.text("You're not sharing your diary"), findsOneWidget);
    expect(find.text('Past shares'), findsOneWidget);
    expect(find.text('Stopped on 9 Oct'), findsOneWidget);
  });

  testWidgets('shows who saw the diary', (tester) async {
    final fake = FakeSharingApi(
      accessLog: [
        {
          'clinician_id': 1,
          'clinician_name': 'Dr. Lena Hofmann',
          'accessed_at': '2026-10-08T12:00:00Z',
          'entry_ids': [3, 5],
        },
      ],
    );
    await pumpSharing(tester, fake);

    expect(find.text('Dr. Lena Hofmann'), findsOneWidget);
    expect(find.textContaining('Looked at 2 entries on 8 Oct at'), findsOneWidget);
  });

  group('overlapWarnings', () {
    final doctor = Clinician.fromJson(hofmann);
    final from = DateTime(2026, 10, 1);
    final to = DateTime(2026, 10, 7);
    Share existing({bool notes = false, int clinicianId = 1}) => Share.fromJson(
      shareJson(
        clinicianId: clinicianId,
        from: DateTime(2026, 10, 5),
        to: DateTime(2026, 10, 14),
        includeNotes: notes,
      ),
    );

    test('says when notes become visible', () {
      expect(overlapWarnings(doctor, [existing()], from, to, true), [
        "Dr. Lena Hofmann will also see your notes for 5 Oct – 7 Oct, "
            "which your earlier share didn't include.",
      ]);
    });

    test('says when notes stay visible through an earlier share', () {
      expect(
        overlapWarnings(doctor, [existing(notes: true)], from, to, false).single,
        startsWith('Dr. Lena Hofmann can still see your notes for 5 Oct – 7 Oct'),
      );
    });

    test('ignores other doctors and days that do not overlap', () {
      expect(overlapWarnings(doctor, [existing(clinicianId: 2)], from, to, true), isEmpty);
      expect(overlapWarnings(doctor, [existing()], from, DateTime(2026, 10, 4), true), isEmpty);
    });
  });
}
