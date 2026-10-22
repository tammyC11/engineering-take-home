class DiaryEntry {
  const DiaryEntry({
    this.id,
    required this.recordedAt,
    required this.mood,
    this.symptoms = const [],
    this.note,
  });

  final int? id;
  final DateTime recordedAt;
  final int mood;
  final List<String> symptoms;
  final String? note;

  factory DiaryEntry.fromJson(Map<String, dynamic> json) => DiaryEntry(
    id: json['id'] as int,
    recordedAt: DateTime.parse(json['recorded_at'] as String),
    mood: json['mood'] as int,
    symptoms: List<String>.from(json['symptoms'] as List),
    note: json['note'] as String?,
  );

  Map<String, dynamic> toJson() => {
    'recorded_at': recordedAt.toUtc().toIso8601String(),
    'mood': mood,
    'symptoms': symptoms,
    'note': note,
  };
}

class Clinician {
  const Clinician({required this.id, required this.name, required this.practice});

  final int id;
  final String name;
  final String practice;

  factory Clinician.fromJson(Map<String, dynamic> json) => Clinician(
    id: json['id'] as int,
    name: json['name'] as String,
    practice: json['practice'] as String,
  );
}

/// The patient's consent for one doctor to read the diary for a period of days.
class Share {
  const Share({
    required this.id,
    required this.clinicianId,
    required this.from,
    required this.to,
    required this.includeNotes,
    required this.createdAt,
    this.revokedAt,
  });

  final int id;
  final int clinicianId;

  /// Inclusive calendar days, as the patient sees them in their diary.
  final DateTime from;
  final DateTime to;
  final bool includeNotes;
  final DateTime createdAt;
  final DateTime? revokedAt;

  bool get isActive => revokedAt == null;

  /// The days this share has in common with [otherFrom]–[otherTo], or null if none.
  ({DateTime from, DateTime to})? overlap(DateTime otherFrom, DateTime otherTo) {
    final start = from.isAfter(otherFrom) ? from : otherFrom;
    final end = to.isBefore(otherTo) ? to : otherTo;
    return start.isAfter(end) ? null : (from: start, to: end);
  }

  factory Share.fromJson(Map<String, dynamic> json) => Share(
    id: json['id'] as int,
    clinicianId: json['clinician_id'] as int,
    from: parseDate(json['from_date'] as String),
    to: parseDate(json['to_date'] as String),
    includeNotes: json['include_notes'] as bool,
    createdAt: DateTime.parse(json['created_at'] as String),
    revokedAt: json['revoked_at'] == null ? null : DateTime.parse(json['revoked_at'] as String),
  );
}

/// One time a doctor opened the diary.
class AccessRecord {
  const AccessRecord({
    required this.clinicianName,
    required this.accessedAt,
    required this.entryCount,
  });

  final String clinicianName;
  final DateTime accessedAt;
  final int entryCount;

  factory AccessRecord.fromJson(Map<String, dynamic> json) => AccessRecord(
    clinicianName: json['clinician_name'] as String,
    accessedAt: DateTime.parse(json['accessed_at'] as String),
    entryCount: (json['entry_ids'] as List).length,
  );
}

/// "2026-10-01" as a local calendar day.
DateTime parseDate(String value) {
  final parts = value.split('-').map(int.parse).toList();
  return DateTime(parts[0], parts[1], parts[2]);
}

/// A local calendar day as "2026-10-01".
String formatIsoDate(DateTime day) =>
    '${day.year.toString().padLeft(4, '0')}-${day.month.toString().padLeft(2, '0')}-'
    '${day.day.toString().padLeft(2, '0')}';
