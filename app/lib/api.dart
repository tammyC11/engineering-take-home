import 'dart:convert';

import 'package:http/http.dart' as http;

import 'models.dart';

/// Talks to the diary API. In the browser the API is served under /api on the
/// same origin; elsewhere pass --dart-define=API_URL=http://localhost:28000/
class ApiClient {
  ApiClient({http.Client? client, this.token = 'patient-1'}) : _client = client ?? http.Client();

  final http.Client _client;

  /// Auth stub: the app always acts as patient 1.
  final String token;

  static final Uri baseUrl = const String.fromEnvironment('API_URL').isEmpty
      ? Uri.base.resolve('/api/')
      : Uri.parse(const String.fromEnvironment('API_URL'));

  Map<String, String> get _headers => {
    'Authorization': 'Bearer $token',
    'Content-Type': 'application/json',
  };

  Future<List<DiaryEntry>> listEntries() async {
    final response = await _client.get(baseUrl.resolve('entries'), headers: _headers);
    final List<dynamic> json = _decode(response, 200);
    return json.map((e) => DiaryEntry.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<DiaryEntry> createEntry(DiaryEntry entry) async {
    final response = await _client.post(
      baseUrl.resolve('entries'),
      headers: _headers,
      body: jsonEncode(entry.toJson()),
    );
    return DiaryEntry.fromJson(_decode(response, 201));
  }

  Future<List<Clinician>> listClinicians() async {
    final response = await _client.get(baseUrl.resolve('clinicians'), headers: _headers);
    final List<dynamic> json = _decode(response, 200);
    return json.map((c) => Clinician.fromJson(c as Map<String, dynamic>)).toList();
  }

  /// The patient's shares, newest first.
  Future<List<Share>> listShares() async {
    final response = await _client.get(baseUrl.resolve('shares'), headers: _headers);
    final List<dynamic> json = _decode(response, 200);
    return json.map((s) => Share.fromJson(s as Map<String, dynamic>)).toList();
  }

  Future<Share> createShare({
    required int clinicianId,
    required DateTime from,
    required DateTime to,
    required bool includeNotes,
  }) async {
    final response = await _client.post(
      baseUrl.resolve('shares'),
      headers: _headers,
      body: jsonEncode({
        'clinician_id': clinicianId,
        'from_date': formatIsoDate(from),
        'to_date': formatIsoDate(to),
        'include_notes': includeNotes,
      }),
    );
    return Share.fromJson(_decode(response, 201));
  }

  Future<Share> revokeShare(int id) async {
    final response = await _client.post(baseUrl.resolve('shares/$id/revoke'), headers: _headers);
    return Share.fromJson(_decode(response, 200));
  }

  /// Who read the diary, newest first.
  Future<List<AccessRecord>> accessLog() async {
    final response = await _client.get(baseUrl.resolve('access-log'), headers: _headers);
    final List<dynamic> json = _decode(response, 200);
    return json.map((r) => AccessRecord.fromJson(r as Map<String, dynamic>)).toList();
  }

  /// Counts a product event such as `entry_created` (only the name is sent). Failures are ignored:
  /// telemetry must never get in the patient's way.
  Future<void> track(String event) async {
    try {
      await _client.post(
        baseUrl.resolve('telemetry'),
        headers: _headers,
        body: jsonEncode({'event': event}),
      );
    } on Exception {
      // Best effort only.
    }
  }

  dynamic _decode(http.Response response, int expectedStatus) {
    if (response.statusCode != expectedStatus) {
      throw ApiException(response.statusCode, response.body);
    }
    return jsonDecode(utf8.decode(response.bodyBytes));
  }
}

class ApiException implements Exception {
  ApiException(this.statusCode, this.body);

  final int statusCode;
  final String body;

  @override
  String toString() => 'API error $statusCode: $body';
}
