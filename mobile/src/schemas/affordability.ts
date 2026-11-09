import { z } from 'zod';
import { normalizeNumericInput } from '@/i18n';
import type { AffordabilityRequest } from '@/types/affordability';

const numeric = z.string().transform(value => normalizeNumericInput(value).trim());
function validDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split('-').map(Number);
  if (year < 1 || month < 1 || month > 12 || day < 1) return false;
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  return day <= [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1];
}
function monthIndex(value: string) { const [y, m] = value.split('-').map(Number); return y * 12 + m - 1; }
function money(value: string, positive = false) {
  return /^\d+(\.\d{1,2})?$/.test(value) && Number(value) <= 9999999999.99 && (positive ? Number(value) > 0 : Number(value) >= 0);
}
export const affordabilitySchema = z.object({
  purchase_price: numeric,
  payment_method: z.enum(['automatic', 'manual']),
  interest_method: z.enum(['none', 'flat', 'reducing_balance']),
  nominal_annual_interest_rate: numeric,
  monthly_installment_amount: numeric,
  start_date: numeric,
  term_months: numeric,
  due_day_of_month: numeric,
  down_payment_amount: numeric,
  down_payment_date: numeric,
  down_payment_paid: z.boolean(),
}).superRefine((data, ctx) => {
  const issue = (field: keyof typeof data, message: string) => ctx.addIssue({ code: 'custom', path: [field], message });
  if (!money(data.purchase_price, true)) issue('purchase_price', 'Enter an amount above zero, up to 9,999,999,999.99, with at most two decimal places.');
  if (!money(data.down_payment_amount || '0') || Number(data.down_payment_amount || 0) >= Number(data.purchase_price)) issue('down_payment_amount', 'Enter a down payment below the purchase price, with at most two decimal places.');
  const term = Number(data.term_months);
  if (!/^\d+$/.test(data.term_months) || term < 1 || term > 1200) issue('term_months', 'Choose a whole number from 1 to 1,200 months.');
  if (!/^\d+$/.test(data.due_day_of_month) || Number(data.due_day_of_month) < 1 || Number(data.due_day_of_month) > 31) issue('due_day_of_month', 'Due day must be a day between 1 and 31');
  if (!validDate(data.start_date)) issue('start_date', 'Enter a real date in YYYY-MM-DD format.');
  else if (monthIndex(data.start_date) + term > 9999 * 12 + 11) issue('term_months', 'This payment period is outside the supported calendar.');
  if (Number(data.down_payment_amount) > 0) {
    if (!validDate(data.down_payment_date)) issue('down_payment_date', 'Enter a real date in YYYY-MM-DD format.');
    else if (!data.down_payment_paid && validDate(data.start_date)) {
      const first = Math.min(monthIndex(data.start_date), monthIndex(data.down_payment_date));
      const last = Math.max(monthIndex(data.start_date) + term - 1, monthIndex(data.down_payment_date));
      if (last - first + 1 > 1200) issue('down_payment_date', 'The full payment period must not exceed 1,200 months.');
    }
  }
  if (data.payment_method === 'manual' && !money(data.monthly_installment_amount, true)) issue('monthly_installment_amount', 'Enter an amount above zero, up to 9,999,999,999.99, with at most two decimal places.');
  if (data.payment_method === 'automatic' && data.interest_method !== 'none' &&
    (!/^\d+(\.\d{1,4})?$/.test(data.nominal_annual_interest_rate) || Number(data.nominal_annual_interest_rate) > 100)) issue('nominal_annual_interest_rate', 'Enter a yearly rate from 0 to 100, with at most four decimal places.');
});

export type AffordabilityFormData = z.infer<typeof affordabilitySchema>;
export function purchasePlanRequest(input: AffordabilityFormData): AffordabilityRequest {
  const data = affordabilitySchema.parse(input);
  const hasDownPayment = Number(data.down_payment_amount) > 0;
  return {
    purchase_price: data.purchase_price,
    payment_method: data.payment_method,
    interest_method: data.payment_method === 'manual' ? 'none' : data.interest_method,
    ...(data.payment_method === 'manual' ? { monthly_installment_amount: data.monthly_installment_amount }
      : data.interest_method !== 'none' ? { nominal_annual_interest_rate: data.nominal_annual_interest_rate } : {}),
    start_date: data.start_date,
    term_months: Number(data.term_months),
    due_day_of_month: Number(data.due_day_of_month),
    down_payment_amount: data.down_payment_amount || '0',
    ...(hasDownPayment ? { down_payment_date: data.down_payment_date } : {}),
    down_payment_paid: hasDownPayment && data.down_payment_paid,
  };
}

export function currentAffordabilityResult<T>(result: T | undefined, submitted: AffordabilityFormData | undefined, current: AffordabilityFormData, pending: boolean, failed: boolean): T | undefined {
  const parsed = affordabilitySchema.safeParse(current);
  return !pending && !failed && parsed.success && JSON.stringify(submitted) === JSON.stringify(parsed.data) ? result : undefined;
}
