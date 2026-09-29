import { ar, en, type Language, type TranslationKey } from './dictionaries';

let language: Language = 'en';
export function setTranslationLanguage(value: Language) { language = value; }
export function getLanguage(): Language { return language; }
export function getLocale(): string { return language === 'ar' ? 'ar-EG' : 'en-US'; }
export function isArabic(): boolean { return language === 'ar'; }

export function t(key: TranslationKey, values: Record<string, string | number> = {}): string {
  const template = (language === 'ar' ? ar : en)[key];
  return template.replace(/\{(\w+)\}/g, (match, name: string) => String(values[name] ?? match));
}

/** Only use for known UI/error keys, never arbitrary user or assistant content. */
export function translateMessage(message: string | null | undefined): string {
  if (!message) return '';
  return Object.prototype.hasOwnProperty.call(en, message) ? t(message as TranslationKey) : message;
}

export function statusLabel(value: string): string {
  const keys: Record<string, TranslationKey> = { active: 'Active', completed: 'Completed', late: 'Late', defaulted: 'Defaulted' };
  return Object.prototype.hasOwnProperty.call(keys, value) ? t(keys[value]) : value;
}
export function classificationLabel(value: string): string {
  const keys: Record<string, TranslationKey> = { Comfortable: 'Comfortable', Manageable: 'Manageable', Risky: 'Risky', 'Not Affordable': 'Not Affordable' };
  return Object.prototype.hasOwnProperty.call(keys, value) ? t(keys[value]) : value;
}
export function categoryLabel(value: string): string {
  const keys: Record<string, TranslationKey> = { Electronics: 'Electronics', Vehicle: 'Vehicle', Housing: 'Housing', Education: 'Education', Personal: 'Personal' };
  return Object.prototype.hasOwnProperty.call(keys, value) ? t(keys[value]) : value;
}
export function sourceLabel(value: string): string {
  const keys: Record<string, TranslationKey> = { manual_entry: 'Manual entry', chatbot_entry: 'Chat', chat: 'Chat' };
  return Object.prototype.hasOwnProperty.call(keys, value) ? t(keys[value]) : value;
}

export function formatCount(value: number | string): string {
  return new Intl.NumberFormat(getLocale(), { useGrouping: false }).format(Number(value));
}
export function monthCount(value: number | string): string {
  const count = Number(value);
  const number = formatCount(count);
  if (language === 'en') return `${number} ${count === 1 ? 'month' : 'months'}`;
  switch (new Intl.PluralRules('ar-EG').select(count)) {
    case 'one': return 'شهر واحد';
    case 'two': return 'شهران';
    case 'few': return `${number} أشهر`;
    case 'many': return `${number} شهرًا`;
    default: return `${number} شهر`;
  }
}

/** Numeric fields only. Never normalize passwords, names or chat messages. */
export function normalizeNumericInput(value: string): string {
  return value.replace(/[٠-٩]/g, digit => String(digit.charCodeAt(0) - 0x660))
    .replace(/[۰-۹]/g, digit => String(digit.charCodeAt(0) - 0x6f0))
    .replace(/٫/g, '.').replace(/٬/g, '').replace(/[\u200e\u200f\u061c]/g, '');
}
