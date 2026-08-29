import { z } from 'zod';

export const loginSchema = z.object({
  email: z
    .string()
    .trim()
    .min(1, 'Email is required')
    .email('Please enter a valid email address'),
  password: z
    .string()
    .min(1, 'Password is required'),
});

export type LoginFormData = z.infer<typeof loginSchema>;

export const registerSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, 'Full name is required')
    .max(120, 'Name cannot exceed 120 characters'),
  email: z
    .string()
    .trim()
    .min(1, 'Email is required')
    .email('Please enter a valid email address'),
  password: z
    .string()
    .min(6, 'Password must be at least 6 characters'),
  monthly_income: z
    .string()
    .optional()
    .refine((val) => !val || (!isNaN(Number(val)) && Number(val) >= 0), {
      message: 'Monthly income must be a non-negative number',
    }),
  fixed_expenses: z
    .string()
    .optional()
    .refine((val) => !val || (!isNaN(Number(val)) && Number(val) >= 0), {
      message: 'Fixed expenses must be a non-negative number',
    }),
  currency: z
    .string()
    .trim()
    .min(1, 'Currency code is required')
    .max(3, 'Currency code cannot exceed 3 characters'),
});

export type RegisterFormData = z.infer<typeof registerSchema>;
