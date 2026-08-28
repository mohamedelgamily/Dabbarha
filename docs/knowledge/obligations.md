# Dabbarha Obligations

Obligations are financial commitments that Dabbarha tracks and includes in budget projections.

## Obligation Properties

Each obligation has:
- **provider**: the source or vendor name
- **item_name**: a short description of the item or service
- **category**: the type of obligation (e.g., loan, subscription, utility)
- **total_amount**: the total cost of the obligation
- **monthly_installment_amount**: the monthly payment amount
- **start_date**: when the obligation begins
- **term_months**: how many months the obligation lasts
- **due_day_of_month**: which day of the month the payment is due
- **status**: current state (active, completed, late, defaulted)

## Obligation Statuses

- **active**: the obligation is currently being paid
- **completed**: the obligation has been fully paid
- **late**: the obligation payment is overdue
- **defaulted**: the obligation has defaulted

## Ownership

Obligations are strictly owned by the authenticated user. Users can only see and manage their own obligations. The backend enforces this boundary at the query level.

## Creating Obligations

Users can create obligations through the chatbot or directly via the API. Write operations require explicit backend confirmation before execution.