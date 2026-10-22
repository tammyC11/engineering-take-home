const _weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const _months = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];

DateTime dayOf(DateTime value) {
  final local = value.toLocal();
  return DateTime(local.year, local.month, local.day);
}

String formatTime(DateTime value) {
  final local = value.toLocal();
  return '${local.hour.toString().padLeft(2, '0')}:${local.minute.toString().padLeft(2, '0')}';
}

/// "Tuesday, 13 October"
String formatLongDate(DateTime day) =>
    '${_weekdays[day.weekday - 1]}, ${day.day} ${_months[day.month - 1]}';

/// "10 Oct"
String formatShortDate(DateTime day) => '${day.day} ${_months[day.month - 1].substring(0, 3)}';

/// "1 Oct – 7 Oct", or "1 Oct" for a single day.
String formatPeriod(DateTime from, DateTime to) =>
    from == to ? formatShortDate(from) : '${formatShortDate(from)} – ${formatShortDate(to)}';

/// "10 Oct at 09:03", in local time.
String formatDateTime(DateTime value) => '${formatShortDate(dayOf(value))} at ${formatTime(value)}';

/// "Today", "Yesterday" or "Sat 10 Oct"
String formatDayHeading(DateTime day, DateTime today) {
  final daysAgo = dayOf(today).difference(day).inDays;
  if (daysAgo == 0) return 'Today';
  if (daysAgo == 1) return 'Yesterday';
  return '${_weekdays[day.weekday - 1].substring(0, 3)} ${day.day} '
      '${_months[day.month - 1].substring(0, 3)}';
}
