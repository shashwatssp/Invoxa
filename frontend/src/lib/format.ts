export type ConfidenceBand = 'high' | 'medium' | 'low';

export function confidenceBand(value: number | null | undefined): ConfidenceBand {
  if (value == null) return 'low';
  if (value >= 0.85) return 'high';
  if (value >= 0.7) return 'medium';
  return 'low';
}

export function formatINR(value: number | null | undefined): string {
  if (value == null) return '-';
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(value);
}

/** Map an invoice status to a badge tone. */
export function statusTone(status: string): 'high' | 'medium' | 'low' | 'primary' {
  switch (status) {
    case 'auto_approved':
    case 'reviewed':
      return 'high';
    case 'flagged':
    case 'pending':
      return 'medium';
    case 'exported':
      return 'primary';
    default:
      return 'low';
  }
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}
