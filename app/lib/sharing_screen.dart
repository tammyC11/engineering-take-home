import 'dart:async';

import 'package:flutter/material.dart';

import 'api.dart';
import 'format.dart';
import 'models.dart';
import 'new_share_screen.dart';
import 'theme.dart';
import 'widgets.dart';

typedef _SharingData = ({
  List<Clinician> clinicians,
  List<Share> shares,
  List<AccessRecord> accessLog,
});

/// Who can see the diary, who looked at it, and a way to share it with a doctor.
class SharingScreen extends StatefulWidget {
  const SharingScreen({super.key, required this.api});

  final ApiClient api;

  @override
  State<SharingScreen> createState() => _SharingScreenState();
}

class _SharingScreenState extends State<SharingScreen> {
  late Future<_SharingData> _data = _load();

  @override
  void initState() {
    super.initState();
    widget.api.track('sharing_opened');
  }

  Future<_SharingData> _load() async {
    final (clinicians, shares, accessLog) = await (
      widget.api.listClinicians(),
      widget.api.listShares(),
      widget.api.accessLog(),
    ).wait;
    return (clinicians: clinicians, shares: shares, accessLog: accessLog);
  }

  void _reload() {
    setState(() {
      _data = _load();
    });
  }

  Future<void> _newShare(_SharingData data) async {
    final shared = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) =>
            NewShareScreen(api: widget.api, clinicians: data.clinicians, shares: data.shares),
      ),
    );
    if (shared == true) _reload();
  }

  Future<void> _stopSharing(Clinician clinician, List<Share> shares) async {
    final what = shares.length == 1
        ? 'your diary for ${formatPeriod(shares.single.from, shares.single.to)}'
        : 'your diary';
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Stop sharing with ${clinician.name}?'),
        content: Text("They won't be able to open $what any more."),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Keep sharing'),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Stop sharing'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      for (final share in shares) {
        await widget.api.revokeShare(share.id);
        widget.api.track('share_revoked');
      }
    } on Exception {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text("Couldn't stop sharing. Try again.")));
      }
    }
    if (mounted) _reload();
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder(
      future: _data,
      builder: (context, snapshot) {
        final data = snapshot.data;
        return Scaffold(
          appBar: AppBar(title: const Text('Share your diary')),
          floatingActionButton: data == null
              ? null
              : FloatingActionButton.extended(
                  onPressed: () => _newShare(data),
                  icon: const Icon(Icons.add),
                  label: const Text('Share with a doctor'),
                ),
          body: RefreshIndicator(
            onRefresh: () async => _reload(),
            child: ListView(
              padding: const EdgeInsets.fromLTRB(Space.m, Space.s, Space.m, 96),
              children: [
                if (snapshot.hasError)
                  _Message(
                    title: "Couldn't load your sharing",
                    body: 'Check your connection and try again.',
                    action: TextButton(onPressed: _reload, child: const Text('Try again')),
                  )
                else if (data == null)
                  const Center(child: CircularProgressIndicator())
                else
                  ContentColumn(
                    child: _SharingOverview(data: data, onStop: _stopSharing),
                  ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _SharingOverview extends StatelessWidget {
  const _SharingOverview({required this.data, required this.onStop});

  final _SharingData data;
  final void Function(Clinician clinician, List<Share> shares) onStop;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final clinicians = {for (final c in data.clinicians) c.id: c};
    // Grouped by doctor, so the patient sees everything one doctor can read in one place.
    final active = <Clinician, List<Share>>{};
    for (final share in data.shares.where((s) => s.isActive)) {
      final clinician = clinicians[share.clinicianId];
      if (clinician != null) active.putIfAbsent(clinician, () => []).add(share);
    }
    final past = data.shares.where((s) => !s.isActive).toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Who can see your diary', style: text.titleMedium),
        const SizedBox(height: Space.s),
        if (active.isEmpty)
          const _Message(
            title: "You're not sharing your diary",
            body:
                'Share it with your doctor before your next appointment. You can stop at any time.',
          )
        else
          for (final MapEntry(key: clinician, value: shares) in active.entries)
            _DoctorCard(
              clinician: clinician,
              shares: shares,
              onStop: (shares) => onStop(clinician, shares),
            ),
        const SizedBox(height: Space.xl),
        Text('Who saw your diary', style: text.titleMedium),
        const SizedBox(height: Space.s),
        if (data.accessLog.isEmpty)
          Text('Nobody has opened your diary yet.', style: text.bodyMedium)
        else
          for (final record in data.accessLog) _AccessCard(record),
        if (past.isNotEmpty) ...[
          const SizedBox(height: Space.xl),
          Text('Past shares', style: text.titleMedium),
          const SizedBox(height: Space.s),
          for (final share in past)
            _Card(
              child: _Lines(
                title: clinicians[share.clinicianId]?.name ?? 'A doctor',
                lines: [
                  formatPeriod(share.from, share.to),
                  'Stopped on ${formatShortDate(dayOf(share.revokedAt!))}',
                ],
              ),
            ),
        ],
      ],
    );
  }
}

class _DoctorCard extends StatelessWidget {
  const _DoctorCard({required this.clinician, required this.shares, required this.onStop});

  final Clinician clinician;
  final List<Share> shares;
  final ValueChanged<List<Share>> onStop;

  @override
  Widget build(BuildContext context) {
    return _Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _Lines(title: clinician.name, lines: [clinician.practice]),
          for (final share in shares) ...[
            const Divider(height: Space.l),
            Row(
              children: [
                Expanded(
                  child: _Lines(
                    title: formatPeriod(share.from, share.to),
                    lines: [
                      share.includeNotes ? 'Mood, symptoms and notes' : 'Mood and symptoms',
                      'Shared on ${formatShortDate(dayOf(share.createdAt))}',
                    ],
                  ),
                ),
                TextButton(onPressed: () => onStop([share]), child: const Text('Stop sharing')),
              ],
            ),
          ],
          if (shares.length > 1) ...[
            const Divider(height: Space.l),
            TextButton(
              onPressed: () => onStop(shares),
              child: Text('Stop all sharing with ${clinician.name}'),
            ),
          ],
        ],
      ),
    );
  }
}

class _AccessCard extends StatelessWidget {
  const _AccessCard(this.record);

  final AccessRecord record;

  @override
  Widget build(BuildContext context) {
    final entries = record.entryCount == 1 ? '1 entry' : '${record.entryCount} entries';
    return _Card(
      child: _Lines(
        title: record.clinicianName,
        lines: ['Looked at $entries on ${formatDateTime(record.accessedAt)}'],
      ),
    );
  }
}

/// A white card, as DESIGN.md asks for lists of people or records.
class _Card extends StatelessWidget {
  const _Card({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: Space.s),
      padding: const EdgeInsets.all(Space.m),
      decoration: const BoxDecoration(color: AppColors.surface, borderRadius: Radii.card),
      child: child,
    );
  }
}

class _Lines extends StatelessWidget {
  const _Lines({required this.title, required this.lines});

  final String title;
  final List<String> lines;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title, style: text.labelLarge),
        for (final line in lines) ...[
          const SizedBox(height: Space.xs),
          Text(line, style: text.labelMedium),
        ],
      ],
    );
  }
}

class _Message extends StatelessWidget {
  const _Message({required this.title, required this.body, this.action});

  final String title;
  final String body;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return _Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: text.labelLarge),
          const SizedBox(height: Space.xs),
          Text(body, style: text.bodyMedium),
          ?action,
        ],
      ),
    );
  }
}
