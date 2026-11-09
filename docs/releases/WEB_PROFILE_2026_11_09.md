# Web profile and homepage updates

November 9, 2026. Deployed and verified in production: release `3a1d49c`,
GitHub Actions workflow `42718631994` succeeded. Live frontend asset checks,
production-image age validation checks (without account-data writes), and
`/v1/health` passed.

- Reuse the homepage footer throughout the web app after a minimum viewport height.
- Link the entire signed-in logo to My Closet without link decoration.
- Rename homepage step 02 to “Unlock Your Custom Marketplace”.
- Suggest expanding style preferences when Marketplace has no matches and the owner has at least three active listings; link directly to Style Preferences.
- Allow explicitly clearing the profile phone number and retain the empty value after reload.
- Share pending profile hydration requests so setup redirects are not skipped during startup.
- Require a valid adult birthday on profile saves; omitted birthdays retain an existing birthday. Use UTC dates for the 18-year boundary. Incomplete or underage profiles enter setup. The birthday control uses month/day/year selectors.
- Improve setup address layout, error visibility, and guidance to select multiple sizes and categories.
- Offer four goals: Refresh My Closet, Sustainable Fashion, Trade Instead of Sell, Access Luxury Fashion. Removed goals trigger setup on the next web login/load and clear the old selections so users can select up to two current choices. Otherwise-complete profiles go directly to step 4; current valid choices remain accepted. This release does not change native mobile onboarding.

Validation: web production build, goal normalization tests, profile age and phone regression tests, archived-closet regression, and API integration tests. The publishing email test fixture now supplies an adult birthday to satisfy the new profile requirement.

The release excludes unrelated Entrupy, native-mobile, and Device Farm work. Local account quiz-reset data is not part of the deployment.
