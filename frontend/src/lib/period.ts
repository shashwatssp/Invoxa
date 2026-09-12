/** Period presets for the Export Center (single period model, all formats). */
export type PeriodPreset =
  | '7d'
  | '14d'
  | 'this_month'
  | 'last_month'
  | 'everything'
  | 'custom';

export type CustomUnit = 'days' | 'weeks' | 'months';

export interface DateRange {
  from: string | null; // ISO yyyy-mm-dd
  to: string | null; // ISO yyyy-mm-dd
}

export interface CustomPeriod {
  count: number;
  unit: CustomUnit;
  /** Optional explicit bounds; when present they win over count+unit. */
  from?: string | null;
  to?: string | null;
}

function toISO(date: Date): string {
  const y = date.getFullYear();
  const m = `${date.getMonth() + 1}`.padStart(2, '0');
  const d = `${date.getDate()}`.padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function addMonths(date: Date, months: number): Date {
  const copy = new Date(date.getTime());
  const day = copy.getDate();
  copy.setMonth(copy.getMonth() + months);
  // Clamp when the month is shorter (e.g. Jan 31 -> Feb 28).
  if (copy.getDate() < day) copy.setDate(0);
  return copy;
}

/** Resolve a preset (and its custom payload) into a concrete date range. */
export function resolvePeriod(
  preset: PeriodPreset,
  custom: CustomPeriod = { count: 1, unit: 'days' },
  today: Date = new Date(),
): DateRange {
  switch (preset) {
    case '7d':
      return { from: toISO(new Date(today.getTime() - 6 * 86400_000)), to: toISO(today) };
    case '14d':
      return { from: toISO(new Date(today.getTime() - 13 * 86400_000)), to: toISO(today) };
    case 'this_month':
      return {
        from: toISO(new Date(today.getFullYear(), today.getMonth(), 1)),
        to: toISO(today),
      };
    case 'last_month': {
      const first = new Date(today.getFullYear(), today.getMonth() - 1, 1);
      const last = new Date(today.getFullYear(), today.getMonth(), 0);
      return { from: toISO(first), to: toISO(last) };
    }
    case 'everything':
      return { from: null, to: null };
    case 'custom': {
      // Explicit bounds win; otherwise count+unit counted back from today.
      if (custom.from || custom.to) {
        return { from: custom.from || null, to: custom.to || null };
      }
      const count = Math.max(1, Math.floor(custom.count || 1));
      if (custom.unit === 'months') {
        return { from: toISO(addMonths(today, -count)), to: toISO(today) };
      }
      const days = custom.unit === 'weeks' ? count * 7 : count;
      return {
        from: toISO(new Date(today.getTime() - (days - 1) * 86400_000)),
        to: toISO(today),
      };
    }
    default:
      return { from: null, to: null };
  }
}

/** Human caption for the resolved range, e.g. "04 Sep - 10 Sep 2026". */
export function describeRange(range: DateRange): string {
  if (!range.from && !range.to) return 'All time';
  const fmt = (iso: string | null, fallback: string) => {
    if (!iso) return fallback;
    const parsed = new Date(`${iso}T00:00:00`);
    return Number.isNaN(parsed.getTime())
      ? iso
      : parsed.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' });
  };
  if (range.from && range.to) return `${fmt(range.from, 'beginning')} - ${fmt(range.to, 'today')}`;
  if (range.from) return `From ${fmt(range.from, 'beginning')}`;
  return `Until ${fmt(range.to ?? '', 'today')}`;
}
