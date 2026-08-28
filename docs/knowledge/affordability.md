# Dabbarha Affordability Classification

Dabbarha evaluates whether a user can afford a proposed financial commitment by projecting their budget across the entire commitment period.

## Classification Thresholds

The overall classification is based on the worst projected buffer month:

- **Comfortable**: remaining buffer is greater than or equal to 40% of monthly income
- **Manageable**: remaining buffer is greater than or equal to 20% and less than 40% of monthly income
- **Risky**: remaining buffer is greater than or equal to 0% and less than 20% of monthly income
- **Not Affordable**: remaining buffer is less than 0% of monthly income

Exactly 0% buffer is classified as Risky.

## How It Works

1. The user's existing obligations and fixed expenses are combined with the proposed commitment.
2. Each month in the commitment period is projected.
3. The worst projected buffer month determines the overall classification.
4. The buffer is calculated as: monthly income minus fixed expenses minus obligation payments minus proposed commitment amount.

## Example

If a user has monthly income of 10,000 EGP, fixed expenses of 2,000 EGP, and existing obligation payments of 1,000 EGP, their base buffer is 7,000 EGP (70%).

If they propose a new commitment of 3,000 EGP per month, the new buffer would be 4,000 EGP (40%), which is Comfortable.

If they propose a new commitment of 5,000 EGP per month, the new buffer would be 2,000 EGP (20%), which is Manageable.

If they propose a new commitment of 7,500 EGP per month, the new buffer would be -500 EGP (-5%), which is Not Affordable.