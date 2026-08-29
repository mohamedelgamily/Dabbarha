import { z } from 'zod';

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
    .trim()
    .min(1, 'Total amount is required')
    .refine((val) => !isNaN(Number(val)) && Number(val) >= 0, {
      message: 'Total amount must be a non-negative number',
    }),
  monthly_installment_amount: z
    .string()
    .trim()
    .min(1, 'Monthly installment is required')
    .refine((val) => !isNaN(Number(val)) && Number(val) >= 0, {
      message: 'Monthly installment must be a non-negative number',
    }),
  start_date: z
    .string()
    .trim()
    .min(1, 'Start date is required')
    .regex(/^\d{4}-\d{2}-\d{2}$/, 'Start date must be in YYYY-MM-DD format'),
  term_months: z
    .string()
    .trim()
    .min(1, 'Term in months is required')
    .refine((val) => Number.isInteger(Number(val)) && Number(val) > 0, {
      message: 'Term must be a positive whole number',
    }),
  due_day_of_month: z
    .string()
    .trim()
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
  status: z.enum(['active', 'completed', 'late', 'defaulted']),
});

export type ObligationFormData = z.infer<typeof obligationSchema>;
