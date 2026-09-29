# Arabic / English localization

The app defaults to English. Login, Register and Profile expose the same `English / العربية` selector. The selection is stored in SecureStore under `dabbarha.language`, separate from authentication keys, so logout does not reset it. Initialization restores the language before rendering auth or navigation.

## Translation conventions

- `src/i18n/dictionaries.ts` contains typed English source keys and Egyptian-friendly Modern Standard Arabic copy. The English dictionary uses those source phrases as its values. `t(key, values)` interpolates complete messages. `monthCount` handles Arabic plural forms through `Intl.PluralRules`.
- Call `t` at render/event time. Do not translate strings once at module initialization, before storage has hydrated.
- Use `statusLabel`, `classificationLabel`, `categoryLabel`, and `sourceLabel` for display only. API enums, category preset values, currency codes, routes, requests and calculations are unchanged. Custom categories and other user data remain intact.
- Zod messages are stable English keys, translated where errors are displayed. Known backend error phrases are mapped at display time; unknown server error details remain verbatim.
- The chat API has no language parameter. Suggested prompts are translated and sent as displayed; typed messages and confirmation replays remain unchanged. Responses are displayed exactly as received. No hidden language instruction is appended. Backend affordability explanations also remain verbatim.

## RTL and restarts

Changing language prompts before restarting, and warns about unsaved Login/Register/Profile edits, including dirty auth forms still mounted behind another auth screen. The selector is disabled during form submission. Storage must succeed before changing the running app.

While a chat request is in flight or a financial confirmation is pending, native navigation removal is prevented and language switching is blocked in the shared store and selector. Finish the request and confirm or cancel its proposed action before switching. This preserves the pending message/key; it does not replay or modify the API request. OS force-quitting is outside this in-memory protection.

Native `I18nManager.allowRTL` and `forceRTL` settings are applied with the existing `Expo.reloadAppAsync` API, using the same JS bundle. A persisted attempt marker prevents automatic reload loops. A host that fails to apply direction shows manual restart guidance and a way to return to its current direction.

Use a **development or standalone native build** for acceptance testing. Expo Go resets native RTL preferences, so unsupported changes are explicitly rejected without overwriting the current preference. The new Expo localization plugin/native configuration requires rebuilding an existing native client. No Expo SDK upgrade or OTA-update setup is required.

The installed Router derives navigation direction from native `I18nManager` on startup. Layouts use logical start/end edges. React Native 0.86 itself maps Text alignment left/right to start/end under RTL, so Typography does not mirror it a second time. Numeric/date/email/password input layouts are explicitly LTR. Back/forward navigation arrows mirror; logos, chart data, vertical financial arrows and non-directional icons do not. Forecast months retain their data order, with native RTL row flow.

## Fonts, numbers and dates

English retains the existing Georgia/system-serif treatment and official SVG logo assets. Bundled Noto Naskh Arabic Regular/Bold provide Arabic glyphs, including when Arabic text appears in English mode. Titles retain their regular weight and hierarchy, with zero Arabic tracking and additional line height. The font license is in `assets/fonts/OFL.txt`.

Display formatting uses `en-US` / `ar-EG`, the Gregorian calendar, and the user's existing currency code. Currency values are never converted. Numeric runs are isolated for bidirectional text. Date-only API values are interpreted as calendar dates without UTC day shifts; payloads retain ISO `YYYY-MM-DD`. Numeric inputs normalize Arabic/Persian digits and Arabic decimal/group separators only; names, passwords and chat content are never normalized.

## Validation

Run from `mobile/`:

```sh
npm run typecheck
npm run check:localization
npx expo install --check
npx expo export --platform android --platform ios
```

The localization check audits literal JSX copy/UI attributes/prose templates and tests translation coverage, font glyph coverage, interpolation, Arabic plural rules, numeric normalization, currency preservation, calendar dates, schema errors, enum labels, storage/logout persistence, Expo Go refusal and restart-loop protection. Native modules are mocked in lifecycle tests; they are not device tests.

Android/iOS production Hermes bundles were successfully generated with both font files. Typechecking, the static-copy audit, and regression tests passed. The dependency check reported matching versions in offline mode (limited validation). The machine's Node 20.17.0 is below Expo's supported minimum 20.19.4; use a supported Node LTS for development.

## Device acceptance still required

No Android device or configured AVD was available during implementation; iOS runtime testing was unavailable on this Windows host. On Android and iOS development/installed builds, verify:

1. Switch both ways before sign-in and in Profile, cancel a switch with dirty fields, cold-launch, log out, and confirm the language persists.
2. Inspect every screen and all three New Commitment steps, edit/detail modals, filters, empty/loading/error states and confirmation dialogs in both languages, including a small phone and larger text settings.
3. Check tab order, stack back gestures, mirrored navigation arrows, horizontal forecast scrolling, keyboard/caret behavior, native Alert alignment, screen-reader labels, font shaping and line clipping.
4. Enter Arabic digits and decimals; compare submitted values, negative/large/zero currency amounts, dates near month boundaries, and unchanged stored currency codes.
5. Send Arabic/English chat messages, inspect mixed-language replies and confirm/cancel a proposed action. Responses and confirmation payloads must stay verbatim.

Intentionally untranslated: brand artwork/name, standard currency codes, email/ISO-date examples, dynamic user content, unknown backend values/errors, backend affordability explanations, and chatbot responses. Operating-system keyboard/menu copy follows the device's settings.

## Final review — 2026-09-19

Continued from the existing implementation without reverting or restarting it. Confirmed issues fixed during review:

- Protected pending/in-flight chat actions from navigation removal and language-triggered reloads.
- Included dirty forms on other mounted auth screens in the restart warning.
- Classified a failed startup reload as restart recovery instead of a settings-read failure.
- Used system text for startup recovery so a missing bundled font cannot affect that message.
- Preserved unknown backend/custom labels such as `constructor` instead of accidentally reading inherited object properties.

`npm run typecheck`, `npm run check:localization` (14 tests and the static-copy/encoding audit), and `git diff --check` passed in this review. The existing Android/iOS Hermes bundle files were verified on disk. API modules/types, backend files and financial calculations were unchanged. Arabic glyph coverage passed for both bundled fonts; actual shaping, clipping, native gestures and restart behavior still require device testing.

Fresh post-review bundles also passed with `npx expo export --platform android --platform ios --output-dir .localization-check/review`. Both Hermes bundles include Noto Naskh Arabic Regular/Bold. These are bundle-compilation checks, not installed-device runs. Generated verification artifacts remain under `.localization-check/` and are not application source.
