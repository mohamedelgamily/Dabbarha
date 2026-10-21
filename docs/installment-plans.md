# Installment plans — Phase 2c.1

## Behavior and compatibility

`POST /obligations` and the existing obligation routes retain their legacy request
and calculation behavior. A legacy obligation has no `purchase_price` and no
stored installment rows; forecasts continue to apply its existing
`monthly_installment_amount` for the old term. Existing rows are never backfilled
or reinterpreted.

New plans are created through `POST /obligations/installment-plans`. The separate
`purchase_price` is the authoritative calculation input. `total_amount` is
retained as a compatibility snapshot equal to that purchase price, and
`monthly_installment_amount` is retained as the first scheduled payment for
clients that still read the old field. Forecasts use the persisted schedule, not
that scalar. The response adds plan metadata and a `schedule_version`.

`GET /obligations/{id}/installments` returns the owned plan's exact schedule.
`PUT /obligations/{id}/installment-plan` replaces calculation inputs and schedule
atomically and requires the current `schedule_version`; stale writes receive 409.
The legacy PUT route cannot change calculation fields on an opted-in plan.
`POST /obligations/{id}/convert-to-installment-plan` is an explicit conversion
flow. It requires the reviewed plan values and `confirm_conversion: true`,
preserves user ownership, and refuses concurrent or repeated conversions.
Schedule reads and writes use the existing user-scoped ownership checks.

The schedule table stores installment number, exact due date, scheduled amount,
and optional principal and interest components. Manual schedules have null
components because the app does not estimate provider interest. The table can
store variable manual schedules in a future phase, while v1.0 stores the simple
recurring provider amount for each month.

## Calculation policy

Money inputs use the existing `Numeric(12,2)` supported range and at most two
fractional digits. Calculations convert money to integer cents and use Decimal
rates with deterministic `ROUND_HALF_UP` rounding. The term is 1–1,200 months.
Rates range from 0% through 100%, with up to four fractional digits. Non-finite,
negative, over-limit and over-precision rates are rejected. An annual rate is a
nominal annual rate used to form monthly calculations; it is not APR and does not
include fees the user has not entered.

- **Automatic, no interest:** divide financed cents across the term and assign
  remaining cents to earliest installments. Principal and scheduled amounts sum
  exactly to purchase price minus down payment.
- **Automatic, flat:** total interest is the original financed balance × nominal
  annual rate × term / 12, rounded once to cents. Divide principal and interest
  cents across regular installments and assign each division remainder to the
  final row. Every row's components equal its amount and the schedule totals
  exactly to financed principal plus rounded interest. The final payment may be
  a few cents higher than regular installments.
- **Automatic, reducing balance:** use monthly rate `annual_rate / 1200` and
  unrounded payment `B × i / (1 − (1 + i)^−n)`. Round the regular payment to
  cents. Each month rounds interest on opening principal to cents and subtracts
  it from the payment. The final payment is exact remaining principal plus that
  month's rounded interest. This final-row adjustment clears principal; it does
  not invent a fee or extend the term. Non-amortizing or out-of-range schedules
  are rejected.
- **Manual:** repeat the provider's actual amount for the supplied term. Never
  replace it with a calculated estimate. Optional disclosed interest metadata is
  informational and does not change this schedule. Fees are not inferred.

For every automatic schedule, stored principal totals equal financed principal,
stored interest totals equal calculated interest, and installment amounts
reconcile to those totals. The manual method has no estimated principal or
interest components.

## Down payments and projections

A positive down payment requires its exact date and must be less than
`purchase_price`; otherwise the request returns 422. A zero amount cannot carry
a date or paid flag. A paid down payment is excluded from projected expenses.
An unpaid payment is attributed to its exact date's calendar month. If its exact
date is earlier than the forecast's requested start date, including an earlier
day in the same aggregated month, the forecast includes it once in its first
month and includes its original date and overdue breakdown in the response. The
stored date is not rewritten.

Forecast and dashboard retain `obligation_payments` and
`current_month_obligation_payments`, respectively, and add installment,
down-payment, and overdue-down-payment breakdown fields. Additive payment-detail
items include the obligation ID, original exact date, amount and overdue flag.
These totals include the actual stored scheduled rows. Legacy obligations
continue to use their original scalar calculation. Existing affordability input continues to work;
plan-aware requests can include purchase price, payment method, rate and down
payment, and affordability evaluates that exact generated schedule without
persisting it.

## Validation and transactions

All calculations validate the merged inputs before database writes. Plan
creation and schedule persistence share a transaction. Schedule edits use an
atomic compare-and-swap against `schedule_version`; a competing edit returns
409, and a failed write rolls back both obligation changes and schedule rows.
SQLite foreign keys are enabled by the application's connection factory.
PostgreSQL uses its native exact NUMERIC type; SQLite's NUMERIC affinity does
not guarantee identical internal decimal storage, so financial math is done in
Python integer cents and integration parity checks are required.

Revision `2c1a00000001` is additive. It adds nullable plan metadata, safe defaults
for down-payment state/version, and the schedule table without touching legacy
values. Its downgrade drops all Phase 2c.1 plan data. Upgrade, downgrade and
re-upgrade must only be tested on disposable SQLite/PostgreSQL databases. No
persistent database migration is part of this phase.

## Frontend handoff for Jomana

Keep the first decision simple: **“Do you already know your monthly payment?”**
 / **«إنت عارف قيمة القسط الشهري؟»**

- Yes: **“Enter the provider's actual monthly payment”** / **«أيوه، اكتب قيمة
  القسط الفعلي زي ما في العقد»**. Short helper: **“We keep this amount as
  provided; we do not recalculate it.”** / **«هنسجل القسط زي ما هو، ومش هنحسبه
  أو نغيّره تلقائي.»**
- No: **“Calculate it for me”** / **«لأ، احسبهولي»**. Then choose **“No
  interest”** / **«من غير فوائد»**, **“Flat interest”** / **«فائدة ثابتة»**, or
  **“Reducing-balance interest”** / **«فائدة على الرصيد المتناقص»**.

Fields and labels:

| English | Egyptian Arabic | Behavior |
|---|---|---|
| Purchase price | سعر الشراء | Required for a new plan; source for calculation |
| Monthly payment | القسط الشهري | Provider amount only in manual mode |
| Down payment | الدفعة المقدمة | Optional; must be less than purchase price |
| Down-payment date | تاريخ الدفعة المقدمة | Exact date required for a positive amount |
| Already paid | مدفوعة بالفعل | Hides that payment from future expense projections |
| Nominal annual interest rate (%) | نسبة الفائدة السنوية الاسمية (%) | 0–100%, up to four decimals; show only for automatic interest |

Short rate disclosure: **“This is not APR and excludes fees you have not
entered.”** / **«دي نسبة سنوية اسمية، مش APR، ومش شاملة أي رسوم ما دخلتهاش.»**
Show a schedule preview before saving, including dates, payments and the final
rounded amount. For legacy edits, distinguish explicit conversion from ordinary
editing, show the proposed purchase price/payment method/rate/down payment and
require a clear confirmation before calling the conversion endpoint. Send and
retain `schedule_version` when editing a plan; reload after HTTP 409.

## Verification

The checked-in fail-fast runner `scripts/run-phase-2c1-verification.sh` requires
an existing CPython 3.12 environment, actual disposable Redis and PostgreSQL
server binaries, and an existing pip-audit executable. It does not install or
upgrade pip or application packages. It checks every exact
`constraints-python312.txt` pin before testing, then sets `REQUIRE_REDIS_TESTS=1`
and `REQUIRE_POSTGRES_TESTS=1`, so missing integration runtimes fail instead of
silently skipping. It runs `pip check`, the advisory scan, SQLite/PostgreSQL
migration upgrade/downgrade/re-upgrade tests, and the complete suite. Output is
shown live and saved to the `VERIFY_LOG` path (or a timestamped temporary log by
default). It finishes with `git diff --check` and Git status. No secrets or
production database URLs are needed.

Example invocation (replace every path with the isolated verification tools on
the machine running it):

```sh
VERIFY_PYTHON=/path/to/clean-venv/bin/python \
REDIS_SERVER_BINARY=/path/to/redis-server \
POSTGRES_TEST_BIN=/path/to/postgresql/bin \
PIP_AUDIT_BIN=/path/to/audit-venv/bin/pip-audit \
bash scripts/run-phase-2c1-verification.sh
```

The audit tool can live in a separate environment and scans the verifier's
site-packages path. The runner verifies the existing interpreter and
application/test package pins without changing either environment.
