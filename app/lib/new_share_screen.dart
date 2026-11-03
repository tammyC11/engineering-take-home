import 'package:flutter/material.dart';

import 'api.dart';
import 'format.dart';
import 'models.dart';
import 'theme.dart';
import 'widgets.dart';

const _presets = [7, 14, 30];

/// Step 1: choose a doctor, the days and whether notes are included.
class NewShareScreen extends StatefulWidget {
  const NewShareScreen({
    super.key,
    required this.api,
    required this.clinicians,
    required this.shares,
  });

  final ApiClient api;
  final List<Clinician> clinicians;

  /// The patient's existing shares, to warn when a new one overlaps.
  final List<Share> shares;

  @override
  State<NewShareScreen> createState() => _NewShareScreenState();
}

class _NewShareScreenState extends State<NewShareScreen> {
  Clinician? _clinician;
  int? _lastDays = _presets.first; // null once the patient picks their own dates
  late DateTime _from = _daysBack(_presets.first);
  late DateTime _to = dayOf(DateTime.now());
  bool _includeNotes = false;

  /// The last [days] days, today included.
  static DateTime _daysBack(int days) {
    final today = dayOf(DateTime.now());
    return DateTime(today.year, today.month, today.day - (days - 1));
  }

  void _choosePreset(int days) {
    setState(() {
      _lastDays = days;
      _from = _daysBack(days);
      _to = dayOf(DateTime.now());
    });
  }

  Future<void> _chooseDates() async {
    final today = dayOf(DateTime.now());
    final picked = await showDateRangePicker(
      context: context,
      firstDate: DateTime(today.year - 5),
      lastDate: DateTime(today.year + 1, today.month, today.day),
      initialDateRange: DateTimeRange(start: _from, end: _to),
      helpText: 'Which days?',
    );
    if (picked == null) return;
    setState(() {
      _lastDays = null;
      _from = dayOf(picked.start);
      _to = dayOf(picked.end);
    });
  }

  Future<void> _continue() async {
    final shared = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => ConfirmShareScreen(
          api: widget.api,
          clinician: _clinician!,
          from: _from,
          to: _to,
          includeNotes: _includeNotes,
          shares: widget.shares,
        ),
      ),
    );
    if (shared == true && mounted) Navigator.of(context).pop(true);
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Share your diary')),
      bottomNavigationBar: SafeArea(
        child: ContentColumn(
          child: Padding(
            padding: const EdgeInsets.all(Space.m),
            child: FilledButton(
              onPressed: _clinician == null ? null : _continue,
              child: const Text('Continue'),
            ),
          ),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.all(Space.m),
        children: [
          ContentColumn(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text('Your doctor', style: text.titleMedium),
                const SizedBox(height: Space.s),
                for (final clinician in widget.clinicians)
                  _DoctorOption(
                    clinician: clinician,
                    selected: clinician == _clinician,
                    onTap: () => setState(() => _clinician = clinician),
                  ),
                const SizedBox(height: Space.xl),
                Text('Which days', style: text.titleMedium),
                const SizedBox(height: Space.s),
                Wrap(
                  spacing: Space.s,
                  runSpacing: Space.s,
                  children: [
                    for (final days in _presets)
                      ChoiceChip(
                        label: Text('Last $days days'),
                        selected: _lastDays == days,
                        onSelected: (_) => _choosePreset(days),
                      ),
                    ChoiceChip(
                      label: const Text('Choose dates'),
                      selected: _lastDays == null,
                      onSelected: (_) => _chooseDates(),
                    ),
                  ],
                ),
                const SizedBox(height: Space.m),
                Text(formatPeriod(_from, _to), style: text.bodyLarge),
                const SizedBox(height: Space.xl),
                Text('What your doctor sees', style: text.titleMedium),
                const SizedBox(height: Space.s),
                Text('Your mood and symptoms on these days.', style: text.bodyLarge),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Also share my notes'),
                  subtitle: const Text('Your notes stay private unless you turn this on.'),
                  value: _includeNotes,
                  onChanged: (on) => setState(() => _includeNotes = on),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Step 2: show exactly who, what and which days before the patient agrees (O.Purp_1).
///
/// Changing this wording? Bump CONSENT_VERSION in backend/app/api.py and add the new wording
/// to consent_texts in a migration.
class ConfirmShareScreen extends StatefulWidget {
  const ConfirmShareScreen({
    super.key,
    required this.api,
    required this.clinician,
    required this.from,
    required this.to,
    required this.includeNotes,
    required this.shares,
  });

  final ApiClient api;
  final Clinician clinician;
  final DateTime from;
  final DateTime to;
  final bool includeNotes;
  final List<Share> shares;

  @override
  State<ConfirmShareScreen> createState() => _ConfirmShareScreenState();
}

class _ConfirmShareScreenState extends State<ConfirmShareScreen> {
  bool _saving = false;

  Future<void> _share() async {
    setState(() => _saving = true);
    try {
      await widget.api.createShare(
        clinicianId: widget.clinician.id,
        from: widget.from,
        to: widget.to,
        includeNotes: widget.includeNotes,
      );
      widget.api.track('share_created');
      if (mounted) Navigator.of(context).pop(true);
    } on Exception {
      if (!mounted) return;
      setState(() => _saving = false);
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text("Couldn't share your diary. Try again.")));
    }
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final warnings = overlapWarnings(
      widget.clinician,
      widget.shares,
      widget.from,
      widget.to,
      widget.includeNotes,
    );
    return Scaffold(
      appBar: AppBar(title: const Text('Check before you share')),
      bottomNavigationBar: SafeArea(
        child: ContentColumn(
          child: Padding(
            padding: const EdgeInsets.all(Space.m),
            child: FilledButton(
              onPressed: _saving ? null : _share,
              child: const Text('Share my diary'),
            ),
          ),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.all(Space.m),
        children: [
          ContentColumn(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Who', style: text.titleMedium),
                const SizedBox(height: Space.xs),
                Text(widget.clinician.name, style: text.bodyLarge),
                Text(widget.clinician.practice, style: text.bodyMedium),
                const SizedBox(height: Space.l),
                Text('What', style: text.titleMedium),
                const SizedBox(height: Space.xs),
                Text(
                  widget.includeNotes
                      ? 'Your mood, symptoms and notes'
                      : 'Your mood and symptoms. Your notes stay private.',
                  style: text.bodyLarge,
                ),
                const SizedBox(height: Space.l),
                Text('Which days', style: text.titleMedium),
                const SizedBox(height: Space.xs),
                Text(formatPeriod(widget.from, widget.to), style: text.bodyLarge),
                for (final warning in warnings) ...[
                  const SizedBox(height: Space.m),
                  _Notice(warning),
                ],
                const SizedBox(height: Space.l),
                Text(
                  "You can stop sharing at any time. Each time your doctor opens your diary, "
                  "you'll see it under \"Who saw your diary\".",
                  style: text.bodyMedium,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// What changes for this doctor when the new share overlaps one they already have.
List<String> overlapWarnings(
  Clinician clinician,
  List<Share> shares,
  DateTime from,
  DateTime to,
  bool includeNotes,
) {
  final warnings = <String>[];
  for (final share in shares) {
    if (!share.isActive || share.clinicianId != clinician.id) continue;
    final overlap = share.overlap(from, to);
    if (overlap == null) continue;
    final days = formatPeriod(overlap.from, overlap.to);
    if (includeNotes && !share.includeNotes) {
      warnings.add(
        "${clinician.name} will also see your notes for $days, "
        "which your earlier share didn't include.",
      );
    } else if (!includeNotes && share.includeNotes) {
      warnings.add(
        '${clinician.name} can still see your notes for $days because of your earlier share. '
        "Stop that share if you don't want this.",
      );
    } else {
      warnings.add('You already share $days with ${clinician.name}.');
    }
  }
  return warnings;
}

class _DoctorOption extends StatelessWidget {
  const _DoctorOption({required this.clinician, required this.selected, required this.onTap});

  final Clinician clinician;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: Space.s),
      child: Semantics(
        button: true,
        selected: selected,
        child: Material(
          color: AppColors.surface,
          shape: RoundedRectangleBorder(
            borderRadius: Radii.card,
            side: BorderSide(color: selected ? AppColors.ink : Colors.transparent, width: 2),
          ),
          child: InkWell(
            borderRadius: Radii.card,
            onTap: onTap,
            child: Padding(
              padding: const EdgeInsets.all(Space.m),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(clinician.name, style: text.labelLarge),
                        const SizedBox(height: Space.xs),
                        Text(clinician.practice, style: text.labelMedium),
                      ],
                    ),
                  ),
                  Icon(
                    selected ? Icons.check_circle : Icons.circle_outlined,
                    color: selected ? AppColors.ink : AppColors.line,
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// A neutral notice; not an error, so no error colour (DESIGN.md).
class _Notice extends StatelessWidget {
  const _Notice(this.message);

  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(Space.m),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: Radii.card,
        border: Border.all(color: AppColors.line),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.info_outline, color: AppColors.ink),
          const SizedBox(width: Space.s),
          Expanded(child: Text(message, style: Theme.of(context).textTheme.bodyLarge)),
        ],
      ),
    );
  }
}
