import { normalizeNumericInput } from '@/i18n';

// Shared Money and TermMonths limits in the audited backend request contract.
export const MAX_MONEY = 9999999999.99;
export const MAX_TERM_MONTHS = 1200;
export function monetaryText(value: string | number): string {
  return normalizeNumericInput(String(value)).trim();
}
export function validMoney(value: unknown, positive = false): boolean {
  if (typeof value !== 'string' && typeof value !== 'number') return false;
  const text = monetaryText(value);
  const amount = Number(text);
  return /^\d+(\.\d{1,2})?$/.test(text) && Number.isFinite(amount) &&
    amount <= MAX_MONEY && (positive ? amount > 0 : amount >= 0);
}
export function validDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split('-').map(Number);
  if (year < 1 || month < 1 || month > 12 || day < 1) return false;
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  return day <= [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1];
}
export function validTerm(value: unknown): boolean {
  return (typeof value === 'string' || typeof value === 'number') &&
    /^\d+$/.test(String(value)) && Number.isSafeInteger(Number(value)) &&
    Number(value) >= 1 && Number(value) <= MAX_TERM_MONTHS;
}
export function validObligationCalendar(start: string, months: number): boolean {
  const [year, month] = start.split('-').map(Number);
  return year * 12 + month - 1 + months - 1 <= 9999 * 12 + 11;
}
