# Controlled financial support access (Phase 2f.3)

This backend-only API supports a documented customer-support or security case.
It does not add a browser interface. Superadmin status grants no standing access
to financial records, and these routes provide no impersonation or write action.

## Authorization and grant lifecycle

Every route requires the admin API to be enabled, a valid short-lived admin
step-up token, a currently provisioned `superadmin` role, and a live durable v2
device session. Legacy access tokens and operational `admin` accounts are
rejected. Role, session and target ownership are rechecked while database rows
are locked before grant changes and each sensitive read.

`POST /admin/support-grants` creates a pending grant for one existing account.
The caller supplies a bounded case reference, a reason code, and one or more
scopes from the fixed allowlist. The reference accepts only 3–64 ASCII letters,
digits, `.`, `_`, `/` and `-`; do not put names, email addresses or financial
details in it. Reason codes are `account_support`, `payment_question`,
`security_review` and `data_accuracy`. Scopes are `financial_profile`,
`obligations`, `installments` and `payment_statuses`.

```json
{
  "target_user_id": 123,
  "support_case_reference": "CASE-2026-123",
  "reason_code": "payment_question",
  "scopes": ["obligations", "installments", "payment_statuses"]
}
```

The grant expires exactly 15 minutes after it is requested. Approval does not
restart or extend that clock; a fresh grant is required after expiry. Pending
grants expire too. `POST /admin/support-grants/{grant_id}/approve` permits any
current superadmin to approve. An independent approver leaves `self_approval`
false (the default). If the requester approves their own grant, they must send
`{"self_approval": true}` explicitly. A self-approved grant creates both the
normal approval audit event and a separate `support_grant_self_approval` event.
The approval response exposes the `self_approved` flag so later security
reviews can identify the exception. A different superadmin may independently
approve from their own v2 session; financial reads remain bound to the original
requesting session.

`GET /admin/support-grants/{grant_id}` returns only grant metadata and is
available to its requester or approver. `POST /admin/support-grants/{grant_id}/revoke`
revokes a pending or active grant immediately and is similarly limited to its
requester or approver. A grant cannot be renewed by changing its expiration.
Expiration is persisted and audited on the first subsequent inspection,
approval/revocation attempt, financial read, or replacement-grant request after
the deadline; no background cleanup worker is required. A revoke request after
expiry records the expiration and a failed revoke attempt and returns the
`expired` state.

## Financial read contracts

Every financial read must include a newly generated six-digit code in
`X-Admin-TOTP`. It is checked against the admin's enrolled TOTP factor and
consumed atomically; replaying the same time-step code fails, including across
concurrent requests. The read also checks the active grant, exact target, scope,
requesting session, current superadmin role, target account and grant expiry
inside the same transaction. The existing admin step-up token must also still
be valid. Each response has `Cache-Control: no-store` and is not placed in an
application cache.

| Method and path | Required scope | Response |
| --- | --- | --- |
| `GET /admin/support-grants/{grant_id}/users/{target_id}/financial-profile` | `financial_profile` | Target ID, monthly income, fixed expenses and currency only |
| `GET /admin/support-grants/{grant_id}/users/{target_id}/obligations?limit=50&offset=0` | `obligations` | Existing obligation response fields, including purchase/legacy amount semantics |
| `GET /admin/support-grants/{grant_id}/users/{target_id}/obligations/{obligation_id}/installments?limit=50&offset=0` | `installments` | Persisted schedule rows for an obligation owned by this target |
| `GET /admin/support-grants/{grant_id}/users/{target_id}/payment-statuses?limit=50&offset=0` | `payment_statuses` | Persisted due date, scheduled amount, state and paid timestamp |

Page size is 1–50 and offset is 0–1,000. Responses use the established ORM
financial values and schedule rows; the API does not recalculate, synthesize,
or mutate financial information. There is no wildcard user lookup through this
surface, cross-user query, bulk export, notification-body view, payment action,
or financial mutation endpoint. A target/obligation mismatch returns 404.
Missing or invalid MFA, scope, role, session, grant or expiry returns a safe
401/403/404/409/422 response as appropriate. Redis or database unavailability
fails closed with 503; clients should honor `Retry-After` for 429/503.

## Audit and privacy

Successful requests, approvals, self-approval, revocations, inspections,
financial reads, authorization denials and observed expirations write bounded
events to `admin_audit_events`. Each support event can reference the grant ID
and target account while active. Events contain action, outcome, actor/target
IDs, grant ID, a one-way source fingerprint and timestamp. They never contain
case-reference text, MFA codes, tokens, credentials, or financial values.
Grant rows cascade-delete with the target account; audit foreign keys become
null when a user or grant is deleted. Thus deleting the account does not leave
a user-linked support grant or an identifying audit reference. Existing admin
audit records have an approved 12-month retention target, but production
retention and alerting are not configured by this code change and still require
deployment and privacy/legal review.

The grant record includes the case reference and the requested scope so the
authorized requester/approver can inspect the reason for access. Keep this
reference non-identifying and store the detailed support case in the separately
authorized support system, if one exists. The API does not create or claim that
such a system exists.

## Production requirements and limitations

- Apply migration `2f3a00000001` using the reviewed production migration process;
  this implementation and its tests use disposable SQLite/PostgreSQL databases.
- Keep `ADMIN_API_ENABLED` off until the production session, TOTP-key, private
  Redis and operational-admin prerequisites documented in
  `docs/admin-security.md` and `docs/admin-operations.md` are met.
- Configure shared private Redis, database timeouts, trusted-proxy handling,
  monitoring and the 12-month audit retention/alert policy in deployment.
- Exclude `Authorization` and `X-Admin-TOTP` from reverse-proxy, tracing,
  analytics and application logs. Never send these values to browser telemetry.
- Alert on self-approved grants, failed support reads, unusual read volume and
  failed audit/storage operations. Alerting is a deployment requirement, not
  implemented here.
- Enforce account deletion and database backup-restoration safeguards from
  Phase 2e. Deleted users' grants and linked audit references are removed by
  foreign-key behavior; an old backup must not be restored directly to service.

The endpoints expose personal financial information to an authorized
superadmin during a narrowly scoped support case. Access remains sensitive even
when audited; production access policy, support-case handling, retention and
legal disclosures still require operational review.
