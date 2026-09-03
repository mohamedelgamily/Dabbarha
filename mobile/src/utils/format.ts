export function formatCurrency(
  value: string | number | null | undefined,
  currency: string = 'EGP',
  options: { showSymbol?: boolean; minimumFractionDigits?: number; maximumFractionDigits?: number } = {},
): string {
  const { showSymbol = true, minimumFractionDigits = 2, maximumFractionDigits = 2 } = options;
  if (value === null || value === undefined || value === '') {
    return showSymbol ? `0.00 ${currency}` : '0.00';
  }
  const num = typeof value === 'number' ? value : parseFloat(String(value));
  if (isNaN(num)) {
    return showSymbol ? `${value} ${currency}` : String(value);
  }
  const formatted = num.toLocaleString('en-US', {
    minimumFractionDigits,
    maximumFractionDigits,
  });
  return showSymbol ? `${formatted} ${currency}` : formatted;
}

export function formatMonthLabel(monthStr: string): string {
  const parts = monthStr.split('-');
  if (parts.length < 2) return monthStr;
  const year = Number(parts[0]);
  const month = Number(parts[1]);
  if (isNaN(year) || isNaN(month)) return monthStr;
  const date = new Date(year, month - 1, 1);
  return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
}

export function formatDate(isoString?: string | null): string {
  if (!isoString) return 'N/A';
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return d.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return isoString;
  }
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
