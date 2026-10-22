import 'package:flutter/material.dart';

import 'add_entry_screen.dart';
import 'api.dart';
import 'format.dart';
import 'models.dart';
import 'sharing_screen.dart';
import 'theme.dart';
import 'widgets.dart';

class DiaryScreen extends StatefulWidget {
  const DiaryScreen({super.key, required this.api});

  final ApiClient api;

  @override
  State<DiaryScreen> createState() => _DiaryScreenState();
}

class _DiaryScreenState extends State<DiaryScreen> {
  late Future<List<DiaryEntry>> _entries = widget.api.listEntries();

  void _reload() {
    setState(() {
      _entries = widget.api.listEntries();
    });
  }

  Future<void> _addEntry() async {
    final saved = await Navigator.of(
      context,
    ).push<bool>(MaterialPageRoute(builder: (_) => AddEntryScreen(api: widget.api)));
    if (saved == true) _reload();
  }

  void _openSharing() {
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => SharingScreen(api: widget.api)));
  }

  @override
  Widget build(BuildContext context) {
    final today = dayOf(DateTime.now());
    return Scaffold(
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _addEntry,
        icon: const Icon(Icons.add),
        label: const Text('New entry'),
      ),
      body: SafeArea(
        child: FutureBuilder(
          future: _entries,
          builder: (context, snapshot) {
            final entries = snapshot.data;
            return RefreshIndicator(
              onRefresh: () async => _reload(),
              child: ListView(
                padding: const EdgeInsets.fromLTRB(Space.m, Space.l, Space.m, 96),
                children: [
                  ContentColumn(
                    child: _Header(
                      today: today,
                      entries: entries ?? const [],
                      onShare: _openSharing,
                    ),
                  ),
                  const SizedBox(height: Space.l),
                  if (snapshot.hasError)
                    _Message(
                      title: "Couldn't load your diary",
                      body: 'Check your connection and try again.',
                      action: TextButton(onPressed: _reload, child: const Text('Try again')),
                    )
                  else if (entries == null)
                    const Center(child: CircularProgressIndicator())
                  else if (entries.isEmpty)
                    const _Message(
                      title: 'Your diary is empty',
                      body: 'Note how you feel today. It takes less than a minute.',
                    )
                  else
                    for (final day in _groupByDay(entries))
                      ContentColumn(
                        child: _DaySection(day: day, today: today),
                      ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}

typedef _Day = ({DateTime date, List<DiaryEntry> entries});

/// Entries arrive newest first, so days come out newest first too.
List<_Day> _groupByDay(List<DiaryEntry> entries) {
  final days = <_Day>[];
  for (final entry in entries) {
    final date = dayOf(entry.recordedAt);
    if (days.isEmpty || days.last.date != date) days.add((date: date, entries: []));
    days.last.entries.add(entry);
  }
  return days;
}

class _Header extends StatelessWidget {
  const _Header({required this.today, required this.entries, required this.onShare});

  final DateTime today;
  final List<DiaryEntry> entries;
  final VoidCallback onShare;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('My diary', style: text.headlineMedium),
        const SizedBox(height: Space.xs),
        Text(formatLongDate(today), style: text.bodyMedium),
        const SizedBox(height: Space.s),
        Align(
          alignment: Alignment.centerLeft,
          child: TextButton.icon(
            onPressed: onShare,
            icon: const Icon(Icons.share_outlined),
            label: const Text('Share with your doctor'),
          ),
        ),
        const SizedBox(height: Space.m),
        _MoodStrip(today: today, entries: entries),
      ],
    );
  }
}

/// The last 14 days, one block per day in that day's latest mood colour.
class _MoodStrip extends StatelessWidget {
  const _MoodStrip({required this.today, required this.entries});

  static const days = 14;

  final DateTime today;
  final List<DiaryEntry> entries;

  @override
  Widget build(BuildContext context) {
    final latestMood = <DateTime, int>{};
    for (final entry in entries) {
      latestMood.putIfAbsent(dayOf(entry.recordedAt), () => entry.mood);
    }
    return Semantics(
      label: 'Mood over the last $days days',
      child: Row(
        children: [
          for (var i = days - 1; i >= 0; i--)
            Expanded(
              child: Container(
                height: 36,
                margin: const EdgeInsets.symmetric(horizontal: 2),
                decoration: _block(latestMood[DateTime(today.year, today.month, today.day - i)]),
              ),
            ),
        ],
      ),
    );
  }

  BoxDecoration _block(int? mood) => BoxDecoration(
    color: mood == null ? null : Mood.color(mood),
    border: mood == null ? Border.all(color: AppColors.line, width: 1.5) : null,
    borderRadius: const BorderRadius.all(Radius.circular(6)),
  );
}

class _DaySection extends StatelessWidget {
  const _DaySection({required this.day, required this.today});

  final _Day day;
  final DateTime today;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: Space.l),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(formatDayHeading(day.date, today), style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: Space.s),
          for (final entry in day.entries) EntryCard(entry),
        ],
      ),
    );
  }
}

class EntryCard extends StatelessWidget {
  const EntryCard(this.entry, {super.key});

  final DiaryEntry entry;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return Container(
      margin: const EdgeInsets.only(bottom: Space.s),
      clipBehavior: Clip.antiAlias,
      decoration: const BoxDecoration(color: AppColors.surface, borderRadius: Radii.card),
      child: IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(width: 6, color: Mood.color(entry.mood)),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.all(Space.m),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text(Mood.label(entry.mood), style: text.labelLarge),
                        const Spacer(),
                        Text(formatTime(entry.recordedAt), style: text.labelMedium),
                      ],
                    ),
                    if (entry.symptoms.isNotEmpty) ...[
                      const SizedBox(height: Space.s),
                      Wrap(
                        spacing: Space.xs,
                        runSpacing: Space.xs,
                        children: [for (final s in entry.symptoms) SymptomTag(s)],
                      ),
                    ],
                    if (entry.note != null) ...[
                      const SizedBox(height: Space.s),
                      Text(entry.note!, style: text.bodyLarge),
                    ],
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
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
    return ContentColumn(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: Space.xl),
        child: Column(
          children: [
            Text(title, style: text.titleMedium),
            const SizedBox(height: Space.xs),
            Text(body, style: text.bodyMedium, textAlign: TextAlign.center),
            ?action,
          ],
        ),
      ),
    );
  }
}
