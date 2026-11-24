# Jouft manual QA test plan and results guide

Prepared: November 4, 2026. This is a test specification, **not evidence of a passing run**. Based on repository behavior at preparation time; release owner must identify the deployed build and enabled features before execution.

## 1. Before you start

- Run the full suite on **staging**. Production uses only QA-064 (read-only smoke) unless the release owner explicitly scopes additional cases.
- Obtain the staging web URL and Android/iOS build from the release owner. Record environment, app version/build or web commit, API version if supplied, device model, OS, browser, tester and UTC run times. Do not infer environment from app name alone.
- Obtain two dedicated accounts (A and B), controlled inbox access, and credentials through the approved secret store. Current staging automation account: `leavethemessage+clerk_test@gmail.com`. Never put passwords, OTPs, API keys, full unsubscribe URLs or payment details in a report. Coordinate shared-account use to avoid concurrent edits.
- Prepare permitted product photos: clothes (front, brand label, back, size/material and wear), shoes (side/three-quarter, brand, sole, size and wear), handbag (front, brand, interior), accessory (front, brand), plus one ambiguous/label-only set. Use known items so identification can be compared with actual evidence. Use no personal images.
- Seed distinguishable A/B drafts and active listings, including older items beyond the first page. Keep a listing/offer ID inventory. Use unique test names or descriptions such as `QA-<run ID>-<case ID>` after analysis when editable; filenames alone may not appear in generated titles.
- Confirm sandbox payment and shipping configuration before billing, subscription, acceptance or label tests. If not confirmed, mark those cases **Blocked**. Do not send proposals, email campaigns or social posts to real users.
- Record whether mannequin generation, cleanup, push and assistant features are enabled. Feature unavailable by design = **N/A**, with release-owner confirmation; required feature unexpectedly absent = **Fail** or **Blocked**, with reason.

## 2. Execution and result recording

Copy `MANUAL_QA_RESULTS.csv` for each run. Use one row per case **per platform/device**; duplicate rows to cover Android, iOS and web separately. All rows begin **Not Run**. A test document does not execute tests.

1. Record run metadata and confirm prerequisites. Run P0 cases first, then P1.
2. Execute numbered steps in order. Record actual outcome, IDs and elapsed time, not just “works.”
3. Set **Pass**, **Fail**, **Blocked**, **N/A**, or **Not Run**. Pass only when every expected result was observed. A timeout with no known result is not Pass. For conditional cases, state which branch was exercised.
4. For failure capture a redacted screenshot/video, exact message, UTC time, listing/offer ID, reproducibility (for example 2/3), and defect link. Compare a second device or browser when useful.
5. For analysis, observe for up to 15 minutes, recording intermediate state and elapsed time. This is a QA observation limit, not a contractual SLA. If incomplete, report the state and ask the release owner to inspect the job; do not repeatedly create listings or rerun paid generation.
6. Retest fixes against a new identified build; keep the original failure and link the retest row. Do not overwrite failure evidence.

Platform labels: **All** = execute on Android, iOS and web where that action exists; **Android/iOS** = native apps; **Web** = browser; **Email/Web** = controlled inbox and web confirmation. Labels/navigation can differ by platform. Record absent or different controls instead of inventing a path.

Recommended coverage: one Android phone, one iPhone and desktop web for every release; narrow mobile web and an additional OS/browser for major UI releases. Record exact versions; this plan does not certify any particular device matrix.

## 3. Device Farm troubleshooting

- Record remote session ARN or automated run ARN, device model/OS, fixture names and permission state. A remote session with the same model can be a different physical device from an automated run.
- If touches fail, try app Close and Device Farm Home. If both fail, reconnect the session and record a device/session blocker separately from an app defect.
- If keyboard is absent, test whether a focused field accepts physical-keyboard input. Never reveal the password for a screenshot.
- If the picker says **Unable to Load Photos**, record it verbatim; try Photos directly and inspect the app photo permission. The supplied November 4 device log contains `Unable to launch com.apple.mobileslideshow because it is restricted`. This proves a Photos launch restriction in that run, but does not alone prove the picker root cause.
- An empty Photos-permission list means no apps are listed as requesting access in that session; it does not prove restrictions are absent. Confirm photo fixtures actually exist on the device. Do not call a permission change a fix until selection succeeds.
- Stop remote sessions after testing. Redact credentials and signed URLs from artifacts.

## 4. Test cases

Each case below has a matching row in the results CSV. P0 = core release gate; P1 = regression coverage. Prerequisites apply in addition to section 1.

### QA-001 — Launch and navigate

**Area:** Access · **Priority:** P0 · **Platform:** All

**Preconditions:** Installed staging build or staging web URL supplied by release owner.

**Steps:**

1. Launch app/site
2. Visit Marketplace, Closet, Inbox and Profile
3. Return to Marketplace.

**Expected:** Each available screen responds; no crash, blank screen or stuck overlay.

### QA-002 — Email/password sign-in

**Area:** Access · **Priority:** P0 · **Platform:** All

**Preconditions:** Signed out; account A credentials from approved secret store.

**Steps:**

1. Open Sign In
2. Enter account A email
3. Focus password
4. Type password
5. Submit
6. Complete any verification.

**Expected:** Password field accepts input; submit responds; correct account is signed in. Password remains masked.

### QA-003 — Invalid credentials

**Area:** Access · **Priority:** P1 · **Platform:** All

**Preconditions:** Signed out.

**Steps:**

1. Attempt sign-in using account A with an intentionally incorrect password.

**Expected:** Clear failure; no authenticated screens or account data exposed.

### QA-004 — Required sign-in fields

**Area:** Access · **Priority:** P1 · **Platform:** All

**Preconditions:** Signed out.

**Steps:**

1. Submit with empty fields, then malformed email and empty password.

**Expected:** Validation prevents invalid submission; interface remains responsive.

### QA-005 — Password recovery

**Area:** Access · **Priority:** P1 · **Platform:** All

**Preconditions:** Disposable staging account with accessible inbox; coordinate password change.

**Steps:**

1. Request password reset for a controlled test inbox
2. Follow delivered instructions
3. Sign in with changed password.

**Expected:** Recovery completes without exposing credentials; new password works.

### QA-006 — Sign out and account isolation

**Area:** Access · **Priority:** P0 · **Platform:** All

**Preconditions:** Two staging accounts A and B with distinct listings.

**Steps:**

1. Open A closet
2. Sign out
3. Sign in as B
4. Inspect Closet, Profile and Inbox.

**Expected:** A private data is absent; B sees only its own private data.

### QA-007 — Session restoration

**Area:** Access · **Priority:** P1 · **Platform:** All

**Preconditions:** Signed in as account A on staging.

**Steps:**

1. Sign in
2. Close and reopen app/browser
3. Inspect signed-in identity
4. Sign out and reopen.

**Expected:** Session behavior is consistent; sign-out does not silently restore authenticated access.

### QA-008 — Registration and invite rules

**Area:** Access · **Priority:** P1 · **Platform:** All

**Preconditions:** Release owner supplies current invite policy and disposable inbox.

**Steps:**

1. Use Create Account with a new controlled email
2. Follow invite/verification prompts
3. Test invalid or missing invite when required.

**Expected:** Configured access rules enforced; valid registration completes; invalid input has useful feedback.

### QA-009 — Create clothing draft

**Area:** Create listing · **Priority:** P0 · **Platform:** All

**Preconditions:** A has clothing fixture set and known condition/size.

**Steps:**

1. Create listing
2. Select clothing front, brand label and back photos
3. Continue
4. Choose condition and size
5. Create once
6. Open Closet.

**Expected:** One draft appears as analyzing or ready; photos, condition and size belong to this item.

### QA-010 — Create shoe draft

**Area:** Create listing · **Priority:** P0 · **Platform:** All

**Preconditions:** A has shoe fixture set including complete footwear.

**Steps:**

1. Select shoe side/three-quarter, brand label and sole photos
2. Set category Shoes, condition and size
3. Create.

**Expected:** One shoe listing saved with correct input data; analysis starts.

### QA-011 — Handbag and accessory categories

**Area:** Create listing · **Priority:** P1 · **Platform:** All

**Preconditions:** Handbag and accessory fixture sets available.

**Steps:**

1. Create one handbag with front/brand/interior and one accessory with front/brand
2. Set supported fields and save.

**Expected:** Both drafts use correct categories and applicable fields.

### QA-012 — Photo count limits

**Area:** Create listing · **Priority:** P1 · **Platform:** All

**Preconditions:** Signed in as account A on staging.

**Steps:**

1. Try continuing without photos
2. Add one
3. Then select up to six
4. Attempt exceeding six.

**Expected:** Zero photos cannot continue; supported 1–6 range works; excess handled without crash or silent loss.

### QA-013 — Photo coverage guidance

**Area:** Create listing · **Priority:** P1 · **Platform:** All

**Preconditions:** Label-only and complete product fixture sets.

**Steps:**

1. Upload only a brand-label close-up
2. Read missing-view guidance
3. Add full product views and recheck.

**Expected:** Guidance identifies missing evidence; photos retained; user can correct coverage.

### QA-014 — Category and condition validation

**Area:** Create listing · **Priority:** P1 · **Platform:** All

**Preconditions:** Signed in as account A on staging.

**Steps:**

1. Continue after photo check
2. Leave condition unset
3. Select condition
4. Confirm or correct category
5. Inspect size field.

**Expected:** Required input enforced; selected category/condition/size persist through save.

### QA-015 — Back, cancel and repeated submit

**Area:** Create listing · **Priority:** P1 · **Platform:** All

**Preconditions:** Signed in as account A on staging.

**Steps:**

1. Go back between creation steps
2. Cancel
3. Restart
4. Press final create twice quickly.

**Expected:** Back preserves current inputs where supported; cancel exits cleanly; no duplicate listings from repeated submit.

### QA-016 — Camera capture

**Area:** Create listing · **Priority:** P1 · **Platform:** Android/iOS

**Preconditions:** Real device with camera access permitted by host.

**Steps:**

1. Choose camera
2. Allow permission
3. Capture a product photo
4. Cancel and reopen once.

**Expected:** Captured image appears in selection; cancellation returns safely.

### QA-017 — Denied photo permission

**Area:** Create listing · **Priority:** P1 · **Platform:** Android/iOS

**Preconditions:** Dedicated test device; record initial permission state.

**Steps:**

1. On a fresh install/reset permission state, deny photo access
2. Try selecting photos
3. Restore permission and retry.

**Expected:** Clear permission guidance; no crash; selection works after restoring access.

### QA-018 — iOS photo picker regression

**Area:** Create listing · **Priority:** P0 · **Platform:** iOS

**Preconditions:** Photo fixtures saved on device; record device model, iOS and remote-session ID.

**Steps:**

1. Open Photos app directly
2. Record whether it opens
3. Open Jouft Add photos → Photo library
4. Grant access if prompted
5. Select photos
6. Inspect Settings → Privacy & Security → Photos.

**Expected:** Picker loads selectable assets and returns selected images. Record exact errors, missing assets or locked permissions.

### QA-019 — Remote input responsiveness

**Area:** Create listing · **Priority:** P0 · **Platform:** Android/iOS

**Preconditions:** Device Farm remote session; signed out; use approved credentials.

**Steps:**

1. Focus email then password
2. Type without disclosing password
3. Tap Close
4. Use Device Farm Home if app does not respond.

**Expected:** Input and buttons respond. Record whether failure affects app only or entire remote session.

### QA-020 — Analysis completion

**Area:** Analysis · **Priority:** P0 · **Platform:** All

**Preconditions:** Fresh draft created in this run; allow up to 15 minutes as QA observation limit, not a product SLA.

**Steps:**

1. Create a complete-evidence draft
2. Record save time
3. Refresh/reopen until analysis finishes
4. Inspect title, brand/category, description and value.

**Expected:** Results correspond to source item; value displays valid currency; no unrelated product data; elapsed time recorded.

### QA-021 — Detailed analysis and original evidence

**Area:** Analysis · **Priority:** P1 · **Platform:** All

**Preconditions:** Signed in as account A on staging.

**Steps:**

1. Open View analysis/review
2. Inspect identity, condition, valuation explanation, warnings and original gallery.

**Expected:** Displayed reasoning and evidence concern this item; original photos remain accessible.

### QA-022 — Unknown item and manual review

**Area:** Analysis · **Priority:** P1 · **Platform:** All

**Preconditions:** Owner-supplied ambiguous fixture; conditional outcome depends on evidence.

**Steps:**

1. Create item from ambiguous/insufficient evidence supplied by owner
2. Inspect outcome and publication action.

**Expected:** Useful missing-evidence, unknown-value or manual-review state; no invented guaranteed valuation; unresolved required review prevents publication.

### QA-023 — Edits survive asynchronous work

**Area:** Analysis · **Priority:** P1 · **Platform:** All

**Preconditions:** New analyzing draft; capture before/after values.

**Steps:**

1. While draft is analyzing, edit a description or supported field
2. Save
3. Reopen after completion.

**Expected:** Owner-authored content retained where supported; unrelated edits not overwritten.

### QA-024 — Photo change does not reuse stale results

**Area:** Analysis · **Priority:** P1 · **Platform:** All

**Preconditions:** Disposable draft and two distinct fixture sets; action may require support if UI has no rerun.

**Steps:**

1. Edit draft photos to a different clearly identifiable test item
2. Save/reanalyze using available action
3. Reopen after completion.

**Expected:** Latest results and preview correspond to current photos; obsolete images/results not attached.

### QA-025 — Refresh/retry behavior

**Area:** Analysis · **Priority:** P1 · **Platform:** All

**Preconditions:** Eligible draft; if no user action exists mark Blocked and request controlled support rerun.

**Steps:**

1. Use exposed retry/refresh-analysis action once on eligible draft
2. Navigate away and back.

**Expected:** Request has visible feedback; no duplicate listing; completion or actionable failure is shown.

### QA-026 — Clothing mannequin preview

**Area:** Images · **Priority:** P1 · **Platform:** All

**Preconditions:** Complete-evidence clothing listing; generation enabled. A skipped/failed preview needs recorded reason, not automatic pass.

**Steps:**

1. Wait for eligible clothing preview
2. Inspect product details and all gallery images.

**Expected:** Originals retained; supporting clothing provides coverage; material/product differences flagged for owner review; AI image has disclosure.

### QA-027 — Shoe mannequin framing regression

**Area:** Images · **Priority:** P0 · **Platform:** All

**Preconditions:** Fresh shoe generation under release under test; record generation date, not an older approved image.

**Steps:**

1. Open newly generated low-cut shoe preview
2. Compare with originals
3. Repeat with boots when available.

**Expected:** Matte white feet/ankles; short lower legs continue through top border; no visible cut ends/stumps, clothes, socks or tights; full toes/heels/soles visible. Boots retain full shafts.

### QA-028 — Mannequin approve and exclude

**Area:** Images · **Priority:** P0 · **Platform:** All

**Preconditions:** Two eligible drafts with pending previews; staging only.

**Steps:**

1. On separate drafts approve/include one generated preview and exclude another
2. Save, reopen, then publish when allowed.

**Expected:** Owner choice persists; included image public; excluded image absent from public gallery.

### QA-029 — View/edit preview consistency

**Area:** Images · **Priority:** P1 · **Platform:** All

**Preconditions:** Listing with generated preview; record pending/approved/excluded state.

**Steps:**

1. Open View analysis
2. Note preview
3. Open Edit listing
4. Inspect image set and saved inclusion decision
5. Reopen.

**Expected:** Saved approved image is consistent across views; pending/excluded status is understandable; no unintended duplicate preview.

### QA-030 — Late preview on published listing

**Area:** Images · **Priority:** P1 · **Platform:** All

**Preconditions:** Generation-enabled listing with pending image job; mark Blocked if timing cannot be arranged.

**Steps:**

1. Publish a draft before optional preview completes if allowed
2. Later inspect owner and public gallery.

**Expected:** Late pending preview does not silently become public; explicit inclusion decision required.

### QA-031 — Image cleanup and gallery integrity

**Area:** Images · **Priority:** P1 · **Platform:** All

**Preconditions:** Cleanup enabled and available in target build; otherwise N/A with reason.

**Steps:**

1. Request background cleanup where offered
2. Inspect original/cleaned hero and detail photos
3. Change hero where supported.

**Expected:** Product details preserved; cleanup does not redesign product; detail photos and order remain correct.

### QA-032 — Search title, brand and category

**Area:** Closet · **Priority:** P0 · **Platform:** All

**Preconditions:** A has multiple known brands/categories and at least one searchable listing beyond first page.

**Steps:**

1. Search using a known title fragment
2. Then brand
3. Then category
4. Clear search.

**Expected:** Relevant own listings returned; clearing restores full list.

### QA-033 — Search navigation regression

**Area:** Closet · **Priority:** P0 · **Platform:** All

**Preconditions:** Signed in as account A on staging.

**Steps:**

1. Search for an older listing
2. Open Review listing
3. Return
4. Open Edit listing
5. Save harmless change
6. Return.

**Expected:** Correct listing opens in each case; no “No listing selected” message or wrong-item update.

### QA-034 — Rapid and empty search

**Area:** Closet · **Priority:** P1 · **Platform:** All

**Preconditions:** Signed in as account A on staging.

**Steps:**

1. Type one query then quickly replace with another
2. Search nonexistent text
3. Clear
4. Repeat with surrounding spaces.

**Expected:** Final query controls results; clear empty state; no stale results from earlier request.

### QA-035 — Filters and pagination

**Area:** Closet · **Priority:** P1 · **Platform:** All

**Preconditions:** Web filters vary from mobile; use seeded listings for each available status.

**Steps:**

1. Exercise available All/Active/Draft/Offers/Traded filters
2. Scroll/load further results
3. Combine search and filter where offered.

**Expected:** Statuses and counts agree with visible data; no duplicates/missing older matches.

### QA-036 — Edit and persist

**Area:** Closet · **Priority:** P1 · **Platform:** All

**Preconditions:** Signed in as account A on staging.

**Steps:**

1. Edit title/description and available condition/size fields
2. Save
3. Reopen and reload.

**Expected:** Changes persist on correct listing and are reflected in appropriate public view.

### QA-037 — Publish draft

**Area:** Closet · **Priority:** P0 · **Platform:** All

**Preconditions:** Ready staging draft; account B available.

**Steps:**

1. Review ready draft
2. Resolve required image decisions/manual review
3. Publish once
4. View as B.

**Expected:** Listing becomes active and visible to B with selected image decision and saved details.

### QA-038 — Remove listing

**Area:** Closet · **Priority:** P1 · **Platform:** All

**Preconditions:** Disposable staging listing only; record listing ID before removal.

**Steps:**

1. Remove designated disposable listing
2. Cancel first, then confirm if confirmation exists
3. Refresh/search as A and B.

**Expected:** Cancel preserves item; confirmed removal reflects in owner/public visibility without removing other items.

### QA-039 — Browse, search and detail

**Area:** Marketplace · **Priority:** P0 · **Platform:** All

**Preconditions:** Published B listing available to A.

**Steps:**

1. Browse Marketplace
2. Search known target
3. Open detail
4. Page through images
5. Return and load more results.

**Expected:** Correct item/details/images shown; search and navigation remain usable.

### QA-040 — Matches and preference eligibility

**Area:** Marketplace · **Priority:** P1 · **Platform:** All

**Preconditions:** Release owner supplies known qualifying and nonqualifying source/target pair and matching criteria.

**Steps:**

1. Open matches for A active listing
2. Compare known B target
3. Change relevant style/size preferences and refresh.

**Expected:** Eligible matches follow saved category/size/value rules; own listings not offered as matches.

### QA-041 — Like and share

**Area:** Marketplace · **Priority:** P1 · **Platform:** All

**Preconditions:** Controlled public listing; cancel external social posting after preview.

**Steps:**

1. Toggle like if offered
2. Reload
3. Share controlled listing
4. Open copied link in signed-out browser.

**Expected:** Like state persists appropriately; share opens correct item; private owner data absent.

### QA-042 — Compose and send proposal

**Area:** Trades · **Priority:** P0 · **Platform:** All

**Preconditions:** A/B staging accounts with eligible active listings and required profile data.

**Steps:**

1. As A open B item
2. Start trade
3. Choose eligible own item(s)
4. Review amounts/shipping message
5. Send once
6. Sign in as B and open Inbox.

**Expected:** One proposal with correct offered/requested items appears for intended recipient.

### QA-043 — Decline proposal

**Area:** Trades · **Priority:** P1 · **Platform:** All

**Preconditions:** New controlled proposal.

**Steps:**

1. As B open disposable incoming proposal
2. Decline
3. Inspect A and B inboxes.

**Expected:** Both sides show declined state; no accepted-trade shipping/payment flow.

### QA-044 — Accept proposal

**Area:** Trades · **Priority:** P0 · **Platform:** All

**Preconditions:** Staging only; test payment methods, shipping addresses and sandbox providers confirmed by release owner.

**Steps:**

1. As B inspect new proposal
2. Select offered item if prompted
3. Accept
4. Inspect both accounts.

**Expected:** Both sides agree on accepted items/status; charges follow displayed consent and sandbox configuration.

### QA-045 — Duplicate/stale action

**Area:** Trades · **Priority:** P1 · **Platform:** All

**Preconditions:** Disposable staged proposal; test providers only.

**Steps:**

1. Open same proposal on two sessions
2. Respond in one
3. Attempt response in other
4. Double-tap action where possible.

**Expected:** No contradictory states or duplicate charges/labels; stale session refreshes or shows useful message.

### QA-046 — Address validation and persistence

**Area:** Shipping and billing · **Priority:** P1 · **Platform:** All

**Preconditions:** Synthetic deliverable-format test address; never real customer data.

**Steps:**

1. Add incomplete address
2. Attempt save/use
3. Complete address
4. Save and reopen
5. Set default where offered.

**Expected:** Required data validated; complete address persists and can be selected. Address not public.

### QA-047 — Quote and label

**Area:** Shipping and billing · **Priority:** P1 · **Platform:** All

**Preconditions:** Sandbox shipping provider confirmed; label creation can incur cost if not sandbox. Coordinate with release owner first.

**Steps:**

1. For accepted staging trade select complete addresses
2. Request quote
3. Inspect amount
4. Create label once
5. Open label/tracking view.

**Expected:** Quote and label belong to correct trade; status persists; failures are actionable.

### QA-048 — Payment method lifecycle

**Area:** Shipping and billing · **Priority:** P1 · **Platform:** All

**Preconditions:** Staging payment provider verified in test mode; use provider test card only.

**Steps:**

1. Add sandbox payment method
2. Select default
3. Refresh
4. Remove disposable method when allowed.

**Expected:** Provider flow returns correctly; only masked details shown; default/removal persist.

### QA-049 — Subscription changes

**Area:** Shipping and billing · **Priority:** P1 · **Platform:** All

**Preconditions:** Sandbox confirmed; dedicated test subscription; never purchase a real plan during routine QA.

**Steps:**

1. Open Subscription
2. Inspect current plan
3. Select test plan
4. Complete sandbox flow
5. Reload
6. Exercise available cancellation.

**Expected:** Plan, price and status match consent and provider result; cancellation terms clear.

### QA-050 — Account and style persistence

**Area:** Profile · **Priority:** P1 · **Platform:** All

**Preconditions:** Signed in as account A on staging.

**Steps:**

1. Edit controlled name/style/size preferences
2. Save
3. Reload and sign in again.

**Expected:** Saved values persist and belong to current account; invalid input handled.

### QA-051 — Security actions

**Area:** Profile · **Priority:** P1 · **Platform:** All

**Preconditions:** Disposable account; record available actions; do not alter shared QA credentials.

**Steps:**

1. Open Security
2. Exercise available account-security flows using disposable account
3. Cancel external step once.

**Expected:** Flows require appropriate verification and return safely; no sensitive values exposed.

### QA-052 — Activity and push preferences

**Area:** Notifications · **Priority:** P1 · **Platform:** All

**Preconditions:** Controlled activity generated by B; push-enabled physical device for delivery checks.

**Steps:**

1. Open Notifications
2. Inspect test trade/like activity
3. Open related item
4. Toggle available notification category
5. Save and reopen.

**Expected:** Activity targets correct entity; settings persist; unread/read behavior consistent.

### QA-053 — Push permission and delivery

**Area:** Notifications · **Priority:** P1 · **Platform:** Android/iOS

**Preconditions:** Push supported by installed build; Device Farm test IPA may omit push entitlement: N/A with reason in that build.

**Steps:**

1. Enable push
2. Accept OS prompt
3. Background app
4. Trigger controlled eligible activity from B
5. Tap delivered notification.

**Expected:** One appropriate notification arrives and opens correct screen; denied permission handled without blocking app.

### QA-054 — Subscribe/unsubscribe preference

**Area:** Email feed · **Priority:** P0 · **Platform:** Web

**Preconditions:** Controlled saved profile email; browser signed in.

**Steps:**

1. In web Profile → General inspect email-update preference
2. Unsubscribe
3. Reload
4. Subscribe again
5. Reload.

**Expected:** Saved address preference persists; mobile control is not required by current implementation.

### QA-055 — Unsubscribe email link

**Area:** Email feed · **Priority:** P0 · **Platform:** Email/Web

**Preconditions:** Controlled digest inbox; token URL is secret: redact it from reports.

**Steps:**

1. Open controlled digest footer link
2. Inspect confirmation before submitting
3. Confirm opt-out
4. Repeat confirmation
5. Check web preference.

**Expected:** Opening GET link alone does not opt out; confirmation opts out; repeated opt-out safe.

### QA-056 — Daily new-match digest

**Area:** Email feed · **Priority:** P1 · **Platform:** All

**Preconditions:** Staging only; owner coordinates baseline/schedule and known pair. Default cutoff 14:00 UTC; capture timestamps in UTC.

**Steps:**

1. Have owner establish baseline
2. Introduce known new qualifying A/B pair
3. Wait for scheduled cutoff
4. Inspect controlled inbox and destination link.

**Expected:** One digest lists new matching target and owner source from preceding fixed 24h window; links open correct items; no historical baseline flood.

### QA-057 — No matches and opt-out suppression

**Area:** Email feed · **Priority:** P1 · **Platform:** All

**Preconditions:** Controlled inboxes and owner verification of scheduled worker execution; otherwise Blocked, not Pass.

**Steps:**

1. Use one account with no new matches and another opted out before send
2. Observe next scheduled window
3. Compare opted-in control.

**Expected:** No digest for no-new-match or opted-out addresses; control gets eligible digest.

### QA-058 — Assistant basic and listing flow

**Area:** Assistant · **Priority:** P1 · **Platform:** All

**Preconditions:** Feature available/enabled. If disabled mark N/A; do not assume experimental agent is deployed.

**Steps:**

1. Open assistant
2. Ask supported marketplace/listing question
3. Start listing flow if offered
4. Cancel then retry.

**Expected:** Relevant responses; cancellation safe; supported listing flow uses correct current photos and inputs.

### QA-059 — Offline and reconnect

**Area:** Reliability · **Priority:** P1 · **Platform:** All

**Preconditions:** Disposable draft; restore connectivity after test.

**Steps:**

1. Load list
2. Disconnect device network
3. Try refresh/save
4. Reconnect and retry once.

**Expected:** Useful error/loading feedback; existing data not corrupted; recovery works without duplicate creation.

### QA-060 — Background during analysis

**Area:** Reliability · **Priority:** P1 · **Platform:** All

**Preconditions:** Signed in as account A on staging.

**Steps:**

1. Start draft analysis
2. Background app or leave page
3. Return after several minutes
4. Refresh.

**Expected:** Same listing resumes current server state; no lost draft or duplicate analysis caused solely by navigation.

### QA-061 — Small screen and keyboard

**Area:** Usability · **Priority:** P1 · **Platform:** All

**Preconditions:** Signed in as account A on staging.

**Steps:**

1. On narrow screen open sign-in, create, edit and profile
2. Focus bottom fields
3. Scroll and dismiss keyboard
4. Inspect Closet toolbar.

**Expected:** Inputs/buttons reachable; no clipped controls or overlap; compact toolbar readable; password masking works.

### QA-062 — Accessibility basics

**Area:** Usability · **Priority:** P1 · **Platform:** All

**Preconditions:** VoiceOver/TalkBack or browser accessibility tools; restore settings after test.

**Steps:**

1. Enable screen reader
2. Navigate primary tabs, sign-in fields, photo controls and submit
3. Enlarge text where supported.

**Expected:** Controls have meaningful labels, sensible focus order and reachable actions; errors understandable.

### QA-063 — Cross-account direct links

**Area:** Security · **Priority:** P0 · **Platform:** Web

**Preconditions:** Controlled A private draft and published item; no API tampering required.

**Steps:**

1. Copy A private draft URL if web exposes one
2. Sign in as B and open it
3. Test public listing link separately.

**Expected:** B cannot view/edit A private draft; public detail exposes only intended public fields.

### QA-064 — Production smoke

**Area:** Release · **Priority:** P0 · **Platform:** All

**Preconditions:** Release owner authorizes production account; do not run staging mutation suite on production.

**Steps:**

1. Using designated production QA account, launch
2. Sign in
3. Browse public item
4. Search own Closet
5. Open review/edit without saving
6. Sign out.

**Expected:** Core navigation works; correct account/environment; no data mutation or real transactions.

## 5. Defect report template

Follow the [Device Farm defect workflow](DEVICE_FARM_DEFECT_WORKFLOW.md) for triage, ownership, repair, retest and closure. Track local reports in the [defect register](DEFECT_REGISTER.md); use the repository GitHub issue form when filing an authorized external issue.

- Defect ID/title:
- Case ID and run ID:
- Environment/build/device/OS/browser:
- Severity: Critical / High / Medium / Low
- Preconditions and test listing/offer IDs:
- Steps to reproduce:
- Expected result:
- Actual result and exact message:
- First observed UTC / reproduction frequency:
- Redacted screenshot/video/log link:
- Workaround, if verified:
- Retest build/date/outcome:

Severity guidance: Critical = sensitive data exposure, wrong-account access or unintended real financial action; High = core workflow blocked with no practical workaround; Medium = partial malfunction with workaround; Low = cosmetic issue without task impact. Priority in this plan is execution priority, not defect severity.

## 6. Run summary and cleanup

Report run ID, target build/environment, tested platforms, Pass/Fail/Blocked/N/A/Not Run counts, open defects by severity, and untested areas. Attach the filled CSV and evidence folder. Proposed release gate: all applicable P0 cases pass, no unresolved Critical/High defects, and every Blocked/Not Run case explicitly reviewed by release owner. QA reports a recommendation; the release owner decides release readiness.

Clean up only your recorded disposable listings/proposals and test subscriptions after preserving evidence; use supported UI actions and coordinate anything that cannot be reversed. Restore preferences and device permissions you changed; stop Device Farm sessions. Keep the results history outside the reusable blank template.

## 7. Behavior references

- [Android automation coverage](ANDROID_AUTOMATION_COVERAGE.md): device-suite mapping, prerequisite blocks and remaining manual checks.

- [Listing analysis process](../LISTING_ANALYSIS_PROCESS.md): authoritative analysis, image generation and publication behavior; check deployment-status notes.
- [Daily match feed](../DAILY_MATCH_FEED.md): baseline, first-observed match windows, opt-out and delivery rules. Current preference control is web Profile → General; native mobile control is not implemented in that change.
- [Device Farm test guide](../../tests/devicefarm/README.md): automated harness and known device limitations; automated status is independent of manual results.

This QA document changes no app behavior, deployment, user data or listing-analysis rules.


### Invitation membership trials — November 20, 2026 (local implementation; not deployed)

Use staging with Stripe test credentials and dedicated accounts only. Do not run
renewal/charge tests against production. Native admin management is web-only.

1. As an admin, create no-card and card-required trials. Vary plan, days, dates,
   cap, email/domain rules, first-trial/new-subscriber eligibility and billing cycle.
   Verify invalid settings fail, and non-admin/API-key access is rejected.
2. Copy the one-time code/link, reload admin, and verify only its suffix remains.
   Edit settings and disable/enable the offer. Existing trial terms must not change.
3. As an eligible signed-in member, preview the terms in web and Android/iOS
   Subscription. Confirm accurate duration, card requirement, renewal price/cycle,
   exclusions and explicit consent. No access begins from preview alone.
4. Redeem a no-card offer. Verify plan/status/end date, no Stripe call or charge,
   duplicate redemption behavior, and fallback to the saved plan after server expiry.
5. Try the last remaining place concurrently from two eligible accounts: only one
   succeeds. Try a different account with the same verified email and confirm the
   first-trial restriction. Edited-profile email must not establish eligibility.
6. For card-required/non-renewing trials, complete Stripe test Setup Checkout;
   refresh in the original client. Verify access starts once and no subscription
   is created. Abandoned/expired checkout must not grant access.
7. For renewing trials, verify displayed recurring terms, Stripe trial dates and
   correct existing plan price. In Stripe test mode, advance the clock through
   trial end, payment success/failure and cancellation; verify signed webhooks,
   duplicate/reordered delivery and member refresh yield the correct billing state.
8. Tamper with another account's checkout/session ID, code, version and dates;
   verify rejection. Edit the offer after preview: redemption must require a fresh
   preview. Verify rate limiting and recovery after provider errors/app restart.
9. End an active no-charge trial as admin: access ends immediately, history stays,
   and the previous redemption still counts. Disabling a code must not revoke
   existing grants or alter recurring subscriptions.
10. Test small screens, large text, keyboard access, native refresh after external
    checkout, errors with no email/Stripe configuration, and signup/onboarding
    routing from an invitation link. Record evidence and any blockers.


Trial listing allowance checks (local implementation, not deployed): configure 1,
25 and unlimited new listings; reject zero/negative/fractional values. Verify the
preview, consent and web/native status show the correct total and remaining count.
Create the final slot concurrently: exactly one request succeeds and the other
returns 409 without saving a draft. Repeat via assistant creation. Existing
pre-trial listings do not count; edits/publication/reruns do not use extra slots;
archive/delete do not refund a slot. Offer edits must not alter existing grants.
Verify a paid upgrade and original trial expiry stop the old custom cap, including
Stripe-renewing trials. Unlimited still records usage but never rejects on count.


### Public username acceptance (local implementation, November 23, 2026)

- On web and mobile profile setup, verify Username defaults to `first_name_last_name`.
- Save a custom handle; verify it survives reload and appears as `@handle` on Closet,
  Marketplace and Review Listing, including listings created before the change.
- Change the handle in account settings; verify listing labels show the new handle.
- Attempt another account's handle (including uppercase spelling); expect a clear
  duplicate error and verify the old handle remains saved.
- Reject spaces/punctuation and handles longer than 40 characters. Test accents in
  names and two accounts sharing a name; automatic defaults must remain distinct.
- Verify shipping/billing contact names and sign-in details remain unchanged.


### Request Access signup-interest form (local, November 23, 2026)

- Click every home-page Request Access CTA: open `/request-access`, without a
  sign-up/password modal. Verify direct navigation and Back to home.
- Complete all ten requested groups, including city and state. Verify US clothing
  XS–XXL, US shoes 5–12 in half sizes, quantity and price-range choices.
- Search both brand lists, add an unlisted brand, and remove selected brands.
  Five selections per list is the limit, including custom brands. Require at
  least one brand in each list and explicit contact consent.
- Submit: show a receipt, create no Clerk account, send an internal notification
  to admin@jouft.com with submitted details and UTC time; send no applicant email.
  Invalid/missing fields must not create records. Retry errors without losing input.
- Admin → Access requests shows all submitted details and consent date. A
  non-admin cannot retrieve submissions. Duplicate email updates one record.
- Check narrow/mobile layout, keyboard navigation, labels, scrollable brand
  choices, loading, errors and successful submission on the hosted mobile page.
- Mobile Request Access opens the hosted page after web deployment/new build;
  current simulator binaries and production remain unchanged until rollout.


Request Access location autocomplete: type at least three characters in the
combined City / State field; select a US suggestion and verify both city and
state in the admin submission. Changing the text must clear the old selection;
unselected text cannot be submitted. Verify keyboard selection, loading/no-results,
provider failure, and rapid typing without stale suggestions. No street address
is required. Existing shipping autocomplete should still require street details.


Access requests export: download CSV as admin with more than one page of records;
verify all rows, original/latest submission UTC timestamps, consent, multi-value
sizes/brands, Unicode, commas/quotes, and formula-safe custom text. Non-admins
must be denied. Verify admin email delivery in the deployed mail environment and
that provider failure leaves the request saved and visible in Admin.
