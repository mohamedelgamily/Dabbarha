import { getLocale, t } from '@/i18n';

export function formatCurrency(
  value: string | number | null | undefined,
  currency: string = 'EGP',
  options: { showSymbol?: boolean; minimumFractionDigits?: number; maximumFractionDigits?: number } = {},
): string {
  const { showSymbol = true, minimumFractionDigits = 2, maximumFractionDigits = 2 } = options;
  const num = value === null || value === undefined || value === '' ? 0 : Number(value);
  if (!Number.isFinite(num)) {
    return showSymbol ? `${value} ${currency}` : String(value);
  }
  const formatted = num.toLocaleString(getLocale(), {
    minimumFractionDigits,
    maximumFractionDigits,
  });
  // Isolate the numeric run so minus signs and currency codes remain in order in RTL prose.
  return showSymbol ? `\u2066${formatted} ${currency}\u2069` : `\u2066${formatted}\u2069`;
}

export function formatMonthLabel(monthStr: string, monthOnly = false): string {
  const parts = monthStr.split('-');
  if (parts.length < 2) return monthStr;
  const year = Number(parts[0]);
  const month = Number(parts[1]);
  if (!Number.isInteger(year) || !Number.isInteger(month) || month < 1 || month > 12) return monthStr;
  const date = new Date(year, month - 1, 1);
  return date.toLocaleDateString(getLocale(), { calendar: 'gregory', month: 'short', ...(monthOnly ? {} : { year: 'numeric' as const }) });
}

export function formatDate(isoString?: string | null): string {
  if (!isoString) return t('N/A');
  try {
    const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoString);
    // Date-only values are calendar dates, not UTC timestamps.
    const d = dateOnly ? new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3])) : new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    if (dateOnly && (d.getFullYear() !== Number(dateOnly[1]) || d.getMonth() !== Number(dateOnly[2]) - 1 || d.getDate() !== Number(dateOnly[3]))) return isoString;
    return d.toLocaleDateString(getLocale(), {
      calendar: 'gregory',
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return isoString;
  }
}

export function formatPercent(value: string | number): string {
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  return new Intl.NumberFormat(getLocale(), { style: 'percent', maximumFractionDigits: 2 }).format(number / 100);
}

export function getTodayDateString(): string {
  const d = new Date();
  return formatYmd(d);
}

export function getCurrentMonthStartDate(): string {
  const d = new Date();
  return formatYmd(d, true);
}

function formatYmd(d: Date, firstOfMonth = false): string {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(firstOfMonth ? 1 : d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}
