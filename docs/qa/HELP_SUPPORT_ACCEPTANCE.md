# Help & Support acceptance

Updated November 17, 2026. Implemented locally; not deployed. Native device acceptance remains pending.

## User entry points

- Web account menu **Support** opens public `/support` in a new tab, preserving work in the original tab. Footer **HELP & SUPPORT** reaches the same page. `/support/` also works.
- Help renders without a Clerk provider; signed-out users and users having sign-in problems can read it.
- Mobile **Help & Support** is available in Profile and in the signed-out Contact Us section. It opens a full-screen, safe-area-aware modal; Close and Android Back return to the previous screen.
- Existing listing-specific reporting and trade issue reporting are unchanged. General contact opens a reviewable email draft or telephone link, not a server-side ticket. No message was sent in development verification.

## Content maintenance

The canonical 16 articles are in `packages/app-client/src/supportContent.mjs` and are rendered by both clients. The readable edition is [USER_HELP.md](../USER_HELP.md). Run `node scripts/build_user_help.mjs` after changing the articles, then use `--check` to verify the edition matches.

Cover account access and onboarding, listing creation/status/search, analysis and missing values, optional AI image choices, Marketplace matching, trades and issue reporting, shipping, billing, email preferences, privacy/deletion, and app troubleshooting. Keep wording aligned with actual controls. Do not promise response times, refunds, authenticity certification, or features that are not enabled. Identify website-only controls where native does not expose them.

## Automated verification

- 142 Node checks passed across shared-client, mobile and web code, including help search/synonyms, combined topic filtering, article/link consistency and email-draft encoding.
- 117 API integration checks passed, including public `/support` and `/support/` access without credentials.
- Web production build and Expo Babel compilation of the mobile app and help component passed.
- Web preview rendered the FAQ and contact options. Full interaction/responsive acceptance and native runtime acceptance have not been completed.

## Manual acceptance before release

1. Open Support from a signed-in web account. Verify the original tab retains its current form state and the new tab shows help.
2. Open `/support` and `/support/` while signed out. Confirm there is no sign-in redirect. Verify help can load without a successful Clerk initialization.
3. Search `mannequin`, `$0`, `forgot password`, `unsubscribe`, and `shipping`. Open matching answers and check that content is readable.
4. Combine a search with a topic that has no match; verify the empty state, clear action, and contact options remain usable.
5. Check all topic buttons with keyboard navigation, visible focus, and a screen reader. Expand/collapse answers; verify headings, labels, count announcements, and links.
6. At narrow phone widths and with text zoom, check wrapping, horizontal overflow, article text, email address, and contact controls. Contact the team should jump to the contact area.
7. Choose a contact topic and inspect the email draft recipient, subject and template. Do not send a message as part of this check. With no mail app configured, verify that the address can be read/copied. Verify the phone link without placing a call.
8. Open Privacy, Terms and Data deletion links; verify the corresponding public pages.
9. On Android and iOS, open native help from Profile and from the signed-out Contact Us section. Check search with the keyboard open, topic scrolling, answer expansion, contact jump, safe areas, text scaling, Close and Android Back.
10. In native help, simulate an unavailable email/telephone handler; verify an error and the email address remain visible.
11. Open a listing issue report separately and confirm its existing submission flow is unaffected. Do not submit test reports or modify real production listings.

Deployment requires a web/API release for `/support` and fresh mobile builds for the native entry points. This implementation does not change listing analysis, pricing or publication behavior.
