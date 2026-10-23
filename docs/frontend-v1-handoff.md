# Handoff to Jomana — remove AI chat from Dabbarha v1.0

This is an implementation checklist, not a message sent to the frontend owner.
The frontend worktree was inspected read-only at `1c144d4`, local `jomana/latest`
tracking `origin/jomana/frontend`. No frontend file, branch or dependency changed.
Paths below are relative to `/Users/mohamedelgamily/Projects/dabbarha-frontend`.

## Backend release contract

`POST /chat` and other `/chat` paths now return ordinary **404 Not Found**, including
requests with a valid user token or an old confirmation header. This is deliberate
feature removal, not a temporary outage. No 503 retry flow, placeholder assistant,
AI “coming soon” card or mock chat should appear in public v1.0.

Registration/login, optional profile, obligation CRUD, dashboard, forecast and
affordability routes and JSON contracts remain. Obligations can still contain
`source=chatbot_entry` as legacy provenance; retain parsing compatibility for old
records. There is no need to delete, hide or convert those obligations.

## Exact cleanup targets

1. `mobile/app/(tabs)/index.tsx:63` — remove `/chat` from the dashboard action-route
   union; `:169` — remove the “Ask Dabbarha” / message-circle action. Adjust the
   remaining shortcut grid for three actions and check English/Arabic layouts.
2. `mobile/app/chat.tsx` — remove the Expo file route and its screen, suggested
   prompts, messages, confirmation card, mutation/request state, confirm/cancel
   handlers, provider-result banners and chat-specific navigation guards. Hiding
   only the shortcut leaves a reachable file-based route/deep link.
3. `mobile/src/api/chat.ts` — remove the client and `X-Confirmed-Tool-Key` handling.
   `mobile/src/types/chat.ts` — remove request/response/message/pending-action types.
   These are dedicated modules; preserve the shared Axios client and auth handling.
4. `mobile/src/store/languageStore.ts:16`, `:34`, `:80` — remove `chatProtected`,
   `setChatProtected` and its chat-only language-switching condition. Preserve dirty
   financial-form protection, persistence, RTL configuration, reload guards and errors.
5. `mobile/src/components/common/LanguageSelector.tsx:10`, `:17`, `:32`, `:41` — remove
   chat-protection checks and the pending-chat warning. Keep busy/disabled state,
   normal radio accessibility and language switching. This is a shared component;
   do not delete it.
6. `mobile/src/i18n/dictionaries.ts` — remove UI copy used only by chat (including
   the Ask Dabbarha shortcut, assistant messages, confirmation notices, empty states,
   provider replies and conversation status). Check call-site usage before removing
   generic keys used by financial screens. Retain source-label compatibility for
   historical obligations; consider a neutral “Imported” / “سابق” label for legacy
   `chatbot_entry` after product copy review, without changing the backend value.
7. `mobile/src/i18n/index.ts:33` — preserve historical source parsing; remove a `chat`
   alias only if nothing else uses it. Its comments about protecting arbitrary user
   text can stay with non-chat wording. `mobile/src/types/obligation.ts` should retain
   legacy-source compatibility; all new manual forms should continue manual entry.
8. `mobile/scripts/localization.test.cjs:204` — remove the pending-chat language-lock
   test; keep financial/source-label, formatting, auth, RTL and dirty-form tests.
   `mobile/scripts/audit-localization.cjs:16` — remove the chat-only generated-ID
   exception after its screen is removed. `mobile/LOCALIZATION.md` — replace chat
   confirmation/runtime scenarios with v1.0 financial/localization checks.
9. `mobile/src/components/common/Icon.tsx:71`, `:110` — consider removing the
   message-circle mapping only after checking all remaining uses. Keep the shared
   icon component and icon package; no dependency is proven chat-exclusive here.

The bottom tab layout (`mobile/app/(tabs)/_layout.tsx`) already contains only Home,
Obligations, Profile and Forecast. The root stack (`mobile/app/_layout.tsx`) has no
explicit Chat screen registration; the chat route comes from its file. Preserve
auth redirects, localization/query providers, tab navigation and the shared
`+not-found` route. Generic shared UI components remain in use outside chat.

## Acceptance checks before v1.0 mobile release

- No visible chat tab, shortcut, screen, marketing copy or AI empty/error state.
- Old `/chat` deep links reach the normal not-found flow and never mount a chat
  client; no background or user-triggered `/chat` request remains.
- No confirmation header or pending tool state is sent/stored by v1.0 clients.
- Registration/login, optional income/profile, manual obligation create/edit/delete,
  dashboard, forecast, affordability and logout still work.
- Historical obligations retain their amounts/schedules/source compatibility.
- English and Arabic/RTL dashboard shortcut layouts and language switching work;
  dirty financial forms retain their existing safeguards.
- Run frontend TypeScript checks and existing localization tests; update snapshots
  only for reviewed feature removal. No backend code or older branch copy should
  be merged into the backend as a shortcut.

The frontend cleanup remains a **public-release coordination blocker**. Backend
removal is complete independently, but the currently inspected mobile worktree
still contains the removed feature until its owner implements this handoff.


## Phase 2g.1 consolidated mobile handoff

For the full current mobile contracts and end-to-end design handoff, use
[`frontend-api-contracts.md`](frontend-api-contracts.md) and
[`frontend-mobile-integration-handoff.md`](frontend-mobile-integration-handoff.md).
Those documents cover auth/session rotation, financial plans and paid occurrences,
forecast/affordability, notifications, localization/RTL, deletion and device acceptance.
This file remains the focused chat-removal coordination note; the browser admin
dashboard is separate future work.
