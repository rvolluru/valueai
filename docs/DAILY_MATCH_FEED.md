# Daily marketplace match feed

Implemented and deployed November 2, 2026 to **staging and production**. Migration
`0011_daily_match_feed` succeeded in both environments. Unsubscribe confirmation,
one-click opt-out and SES mailbox-simulator delivery passed in both. Initial
baseline scans sent zero user emails and reported zero failures. Worker activation
is configured at 14:00 UTC daily (09:00 EST / 10:00 EDT).

The feature was isolated from unrelated local changes: staging image
`valueai-staging-api:daily-feed-7bb7910` builds on `ec13811`; production image
`valueai-mvp-api:daily-feed-68f54db` builds on `5932db5`. Source and persistent
rollout configuration are committed in `8ce1a8d`. The initial feed rollout used staging API revision 11 /
worker revision 5 and production API revision 186 / worker revision 57. Subsequent
application releases can advance these revisions while preserving feed configuration. Both worker configurations enable the feed; API task flags remain
false because scheduling runs only in the workers. Future deployments inherit
explicit enabled configuration from the staging deployment script / production
workflow. Local `.env.example` remains disabled by default.

The analysis worker observes current matches every five minutes in a separate
thread, using the same preferences, value tolerance, owner exclusion and sent-offer
exclusion as the closet marketplace-matches endpoint. Its existing 5,000-active-item
marketplace scan bound applies here too. Only Active source and target listings qualify.
All owner listing pages and matching result pages are scanned within those rules.

The first scan for each account establishes a baseline without emailing historical
matches. Subsequent unseen source/target pairs receive a durable first-observed
timestamp. This is observation time, not the exact time a model, price or publication
change caused the match. Previously observed pairs do not become new again after
disappearing and returning. Matching and scanning make no AI calls or listing changes.

At/after 14:00 UTC daily (configurable), each address with new matches gets one email
covering the preceding 24 hours **ending at that day's configured UTC cutoff**.
Fixed windows avoid overlapping daily feeds. Only pairs still matching when scanned
are included. No new matches means no email. Duplicate profile addresses are combined;
recipients come from saved profile email addresses, never shipping contact addresses.
The digest lists the target item, the owner's matching item and a marketplace link.

Every message includes text and HTML bodies, an unsubscribe footer and one-click
unsubscribe headers. Addresses default to subscribed until opted out. The preference
is address-level: duplicate accounts sharing the same address share its opt-out;
changing a profile to a different address uses that address's preference. Profile →
General in the web app provides subscribe/unsubscribe controls. Account settings
require authentication and resolve the saved email server-side. Mobile can use the
same API; a native settings control is not implemented in this change.

Tokenized unsubscribe GET requests display confirmation without changing preferences
(safe for link scanners); POST opts out idempotently. One-click email clients POST
to the same token URL. Tokens are bearer credentials: do not log or share full URLs.
Unsubscribe stops these email updates, not transactional receipts or shipping mail.
Preferences are rechecked just before sending. A request racing with an already
in-flight provider call cannot retract that email.

Delivery uses SES raw email and checks the SES account suppression list first.
Suppression lookup failures prevent delivery. SES subscription management contact
lists were checked in the configured AWS account/us-east-1 and none existed at
implementation time; if external subscriptions are introduced, synchronize their
opt-outs before enabling. SMTP digest delivery is not implemented.

The database claims one delivery per normalized email/day before calling SES,
preventing duplicate sends across worker replicas. A crash or ambiguous provider
failure after claiming is not automatically retried that day; this favors avoiding
duplicates over guaranteed delivery. Inspect `match_feed_deliveries` and aggregate
worker tick logs for failures. Worker downtime can miss a window: this is not a
historical catch-up campaign. The first enabled day is baseline-only.

## Rollout

1. Deploy API and web changes with the feed disabled. Run `python -m app.migrations`
   against the target database before starting API/workers.
2. Apply the SES IAM change granting `ses:GetSuppressedDestination` in addition to
   existing send permissions. Verify the SES sending identity, production access,
   public app/API HTTPS origins and working unsubscribe endpoint.
3. Verify preferences and one controlled test email in staging. Do not use a local
   database containing imported users as a production mailing list.
4. Set `daily_match_feed_enabled=true` in the target Terraform environment (or
   `DAILY_MATCH_FEED_ENABLED=true`) and deploy a running analysis worker. Set
   `daily_match_feed_utc_hour` / `DAILY_MATCH_FEED_UTC_HOUR` (0–23) if changing the
   default 14:00 UTC. Keep that cutoff stable to preserve nonoverlapping windows.
5. Check baseline observations and subsequent tick/delivery results. Disable the
   flag to stop scanning and delivery without deleting unsubscribe preferences.

This rollout used targeted ECS service updates, one-off migration/verification
tasks, and narrowly scoped IAM role policies (`JouftDailyMatchFeed`). No full
Terraform apply was performed. Only mailbox-simulator test messages were sent;
real users receive later scheduled feeds when qualifying new observations exist.

Verification: 17 migration/feed tests passed against each isolated release,
staging-deployment regression tests passed, both web builds succeeded, and public
preference endpoints require authentication. Runtime feed summaries and ECS service
stability were checked after enabling.
