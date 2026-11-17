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
    .refine(value => Array.from(value).length <= 120, 'Name cannot exceed 120 characters'),
  email: z
    .string()
    .trim()
    .min(1, 'Email is required')
    .email('Please enter a valid email address'),
  password: z
    .string()
    .refine(value => Array.from(value).length >= 8, 'Password must be at least 8 characters')
    .refine(value => Array.from(value).length <= 128, 'Password cannot exceed 128 characters')
    // Python str.strip() whitespace used by the backend; do not trim the password.
    .refine(value => /[^\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]/u.test(value), 'Password must contain non-whitespace text')
    .refine(value => !Array.from(value).some(char => {
      const point = char.codePointAt(0)!;
      return point >= 0xd800 && point <= 0xdfff;
    }), 'Password must contain valid Unicode'),
});

export type RegisterFormData = z.infer<typeof registerSchema>;
