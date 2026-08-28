# Dabbarha Forecast

Dabbarha provides monthly cash-flow forecasting to help users understand their projected financial position.

## How Forecasting Works

1. The forecast uses the user's stored monthly income and fixed expenses.
2. It overlays the user's existing obligations on each month.
3. It produces monthly rows containing income, fixed expenses, obligation payments, and projected buffer.
4. The projected buffer is the amount remaining after all obligations and fixed expenses are paid.

## Forecast Window

Users can request a forecast for a specific start month and number of months. The forecast engine handles:
- Calendar year boundaries
- Mid-month start dates
- Obligations that begin before or after the forecast period
- Obligation term windows and payable statuses

## Obligation Status

Only obligations with payable statuses (`active`, `late`) are included in projected payments. Non-payable statuses (`completed`, `defaulted`) are excluded.