# DF-003 — Staging transaction providers are not configured

- Status: Blocked — test-mode credentials required.
- Classification: Test data/configuration.
- Severity: High for transaction-suite coverage; repair priority: P1.
- Owner: Unassigned (credential/configuration owner needed).
- Verified: November 7, 2026, read-only inspection.
- Environment: Staging API task definition `valueai-staging-api:22`.
- Affected cases: QA-042, QA-044–QA-049 and transaction-dependent workflows.

## Observed

The staging ECS API container has no explicit Stripe/Shippo environment or secret
injections. A one-off task using that same task definition loaded application
settings and reported:

- `stripe_secret_key`: missing.
- `stripe_publishable_key`: missing.
- `shippo_api_key`: missing.
- Shippo flat-rate quoting enabled; that does not supply a Shippo token or enable label purchase.

[Sanitized evidence](../evidence/configuration/staging-payment-shipping.json).
No keys were printed, credentials changed, labels purchased or payments initiated.

## Expected / next action

Supply dedicated Stripe test-mode secret/publishable keys and a Shippo test token
through the approved staging configuration mechanism. Confirm webhook/test plan
configuration where relevant, deploy the scoped staging configuration, then verify
actual runtime test modes before enabling controlled transaction recipes.

Credential storage location alone does not determine provider mode. Missing
credentials are not sandbox credentials. Do not copy production/live transaction
keys into staging to unblock this suite. Production configuration was not changed.

## Retest acceptance

1. Runtime keys identify Stripe test mode and Shippo test mode without exposing values.
2. Read-only provider probes authenticate successfully in test mode.
3. Controlled payment setup and shipping quote/label cases pass using test data.
4. Record configuration revision, device run IDs and sandbox evidence; only then enable the transaction gate.

Related suite prerequisite: second account `rajesh_mid@yahoo.co.in` selected by user;
its password must be supplied through Secrets Manager. Real-email verification, if
requested by Clerk, needs a supported flow; the reserved test OTP is not valid for
this address. No password or account security settings were changed.


November 9 recheck: the running staging API remains revision 22 with Stripe secret,
publishable key and Shippo token missing. Local test-mode provider credentials
were found and authenticated successfully (Stripe balance `livemode=false`, Shippo
HTTP 200 with a test-prefixed token), but they have not been injected into staging.
No live or production credentials were substituted. Dedicated account B credentials
and observer authentication are separate missing test prerequisites. This report
remains Blocked; local provider-key validity does not mean staging is configured.
