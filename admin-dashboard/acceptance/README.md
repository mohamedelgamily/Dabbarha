# Linux administrator browser acceptance

After the workflow, the dashboard files and the test fixture have been reviewed and pushed to mohamed/backend, a matching push triggers **Admin browser acceptance**. Check the run's commit SHA. Manual dispatch also works once GitHub recognizes the workflow on the default branch:

```sh
gh workflow run admin-browser-acceptance.yml --ref mohamed/backend
gh run list --workflow admin-browser-acceptance.yml --branch mohamed/backend
```

Use the run's **chromium** job. A successful run reports the Chromium version, ordinary-account denial, admin login and MFA, protected device list, logout, actual history traversal, direct navigation and reload. Require the final browser PASS line, successful process exit and successful cleanup. A green dependency installation or HTTP test alone cannot establish browser acceptance.

The job installs locked Python wheels and a separately pinned test-only Playwright Chromium. Only setup needs external networking. The real API, dashboard, TLS proxy and browser run as an unprivileged user in a loopback-only network namespace. A private temporary home holds the SQLite database, Chromium profile and an NSS trust store for the generated CA. Certificate verification and Chromium sandboxing stay enabled. The browser also exercises overview, readiness, exact lookup, delivery diagnostics, exceptional self-approval, a fresh-TOTP financial read and grant revocation. The run exercises the ordinary registration and session APIs; encrypted TOTP enrollment is seeded directly for one disposable fixture account. The browser submits an actual six-digit code to the existing MFA endpoint.

Review the first failing step. For setup failures inspect the lock installation, browser revision, Ubuntu AppArmor profile load, network namespace and NSS setup. For browser failures inspect the last fixed stage label. A history failure can indicate protected content was restored, or the expected navigation did not occur. Investigate before approval. Keep tracing, screenshots, video, form logging, browser debugging and artifact uploads disabled. Use disposable synthetic data for reproduction. This job checks the current device-session screen; there is no financial dashboard screen in this phase.
