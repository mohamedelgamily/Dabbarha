# Dabbarha administrator sign-in

This server-rendered browser foundation runs on Node with native TypeScript stripping (tested with Node 26.0.0). It uses only Node built-ins. No npm install, dotenv loader or signing/encryption keys are required by the BFF.

## Verify and run locally

From the backend checkout:

```sh
node --version
node --test admin-dashboard/server.test.mts
ADMIN_ORIGIN=https://localhost:8443 API_ORIGIN=http://127.0.0.1:8000 node admin-dashboard/server.mts
```

Use a disposable, migrated development API with durable sessions enabled, legacy issuance disabled, admin API enabled and an offline-enrolled test administrator. Follow docs/admin-security.md for factor setup. Keep backend-only keys in the API environment. Do not pass them to Node. The BFF accepts an HTTPS upstream or HTTP on numeric IPv4 loopback only. Only the two origins are configured here.

For a real browser smoke, put a local TLS proxy on loopback with a locally trusted development certificate. Example site block for Caddy, in a separate local configuration:

```caddyfile
https://localhost:8443 {
    bind 127.0.0.1
    tls internal
    reverse_proxy 127.0.0.1:8787
}
```

Visit https://localhost:8443 with the certificate trusted. Preserve the original Host including port. Sign in, verify a fresh TOTP, inspect the first 50 own sessions, revoke a disposable owned session with its password, and sign out. Verify a normal account cannot enter. Repeat after a server restart and after MFA expiry. Automated tests run the real HTTP handler with a controlled upstream and exercise the cookie contract; native browser cookie policy and actual TLS require the smoke above.

## Session boundary

Run one instance, one process, fixed loopback port, one host. A cluster worker or WEB_CONCURRENCY other than 1 is rejected. Deployment must enforce one replica across hosts. The in-memory store caps all sessions, including anonymous entries, at 128. Admission returns 503 when full. Per-session requests serialize by rejecting overlaps. A five-minute absolute deadline starts at the first form, shortened by upstream token lifetimes. Reauthenticate on expiry. This intentionally short flow does not refresh bearer tokens. Credentials and TOTP codes are never rendered. The refresh token is used only for upstream logout.

Logout drops the browser handle before contacting the API. Upstream outages produce an unconfirmed-revocation message. Expiry sweeps attempt remote logout; graceful shutdown drains then attempts retirement. Crash, network loss after session creation or failed upstream retirement may leave a durable upstream session. Use account-owned password-confirmed device revocation after reauthentication. The active opaque cookie is a bearer credential until invalidation or expiry; MFA and CSRF do not make a copied current cookie replay-proof. Use managed devices and restricted ingress.

Before shared deployment, verify private operator ingress, edge rate limits and trusted proxy topology. The BFF does not forward caller-supplied IP headers; upstream per-IP budgets can be shared across operators. Ensure both proxy hops suppress queries, headers and bodies in logs. Disable core dumps, restrict process access and use a supported patched Node runtime. The server renders operations, exact account lookup, redacted delivery diagnostics and case-bound support forms. All dashboard actions require current upstream MFA and session authorization. Each financial page requires its own fresh TOTP. Audit history and administrator provisioning remain offline. See docs/admin-dashboard-plan.md for the API matrix and docs/jomana-release-handoff.md for ingress requirements.
