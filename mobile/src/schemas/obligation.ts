import { z } from 'zod';
import { normalizeNumericInput } from '@/i18n';
import { validMoney, validDate, validTerm, validObligationCalendar } from '@/utils/financialValidation';

export const obligationSchema = z.object({
  provider: z
    .string()
    .trim()
    .min(1, 'Provider is required')
    .max(120, 'Provider cannot exceed 120 characters'),
  item_name: z
    .string()
    .trim()
    .min(1, 'Item name is required')
    .max(160, 'Item name cannot exceed 160 characters'),
  category: z
    .string()
    .trim()
    .min(1, 'Category is required')
    .max(80, 'Category cannot exceed 80 characters'),
  total_amount: z
    .string()
    .overwrite(value => normalizeNumericInput(value).trim())
    .min(1, 'Total amount is required')
    .refine((val) => validMoney(val), {
      message: 'Enter an amount from zero to 9,999,999,999.99, with at most two decimal places.',
    }),
  monthly_installment_amount: z
    .string()
    .overwrite(value => normalizeNumericInput(value).trim())
    .min(1, 'Monthly installment is required')
    .refine((val) => validMoney(val), {
      message: 'Enter an amount from zero to 9,999,999,999.99, with at most two decimal places.',
    }),
  start_date: z
    .string()
    .overwrite(value => normalizeNumericInput(value).trim())
    .min(1, 'Start date is required')
    .refine(validDate, 'Enter a real date in YYYY-MM-DD format.'),
  term_months: z
    .string()
    .overwrite(value => normalizeNumericInput(value).trim())
    .min(1, 'Term in months is required')
    .refine(validTerm, {
      message: 'Choose a whole number from 1 to 1,200 months.',
    }),
  due_day_of_month: z
    .string()
    .overwrite(value => normalizeNumericInput(value).trim())
    .min(1, 'Due day of month is required')
    .refine(
      (val) => {
        const num = Number(val);
        return Number.isInteger(num) && num >= 1 && num <= 31;
      },
      {
        message: 'Due day must be a day between 1 and 31',
      }
    ),
  status: z.enum(['active', 'completed', 'late', 'defaulted'], { error: 'Select a valid status' }),
}).refine(data => !validDate(data.start_date) || !validTerm(data.term_months) || validObligationCalendar(data.start_date, Number(data.term_months)), {
  path: ['term_months'], message: 'This payment period is outside the supported calendar.',
});

export type ObligationFormData = z.infer<typeof obligationSchema>;
