# CareMemory UI Features Research (Oct 2026)

Basis: spec 03 (sections 0-9), INTEGRATION_DECISIONS c/e, STORY_AND_FEATURES (B.1/B.2). **[S]** = sourced, **[I]** = my inference. Web search was thin on some items (noted); nothing below depends on an unverified claim.

## 1. What strong tools do (and what to steal)

| Source | Pattern | Steal for CareMemory |
|---|---|---|
| Simple.org | Overdue list = "Call list", worked top-down by priority; outcome recorded after each call (agreed to visit / removed); offline for days then sync; data entry under 20 s ([docs](https://docs.simple.org/readme/simple-app-features), [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC9843217)) [S] | Supporter "Today" list ordered by approved visit rank; outcome buttons; a "tap count" budget per action [I] |
| CommCare | Low-literacy guidance: prefer single-select and numeric inputs, very short case lists, number IDs not names, icons in lists, audio/images ([Dimagi wiki](https://dimagi.atlassian.net/wiki/x/-jPKfw)); offline-first caseload download ([use case](https://commcare.dimagi.com/use-cases/service-delivery/)) [S] | Supporter shows patient number + first name + icon; no free text in the happy path [I] |
| DHIS2 | Dashboards can be marked for offline use (cached in browser; filters unavailable offline); outlier detection (z-score/IQR) for data quality ([2.36 notes](https://docs.dhis2.org/en/implement/software-release-information/dhis2-core-releases/dhis-core-version-236/release-notes.html), [2.37](https://community.dhis2.org/t/dhis-version-2-37-is-released/44948)) [S] | Cache the district dashboard for the offline fallback; flag outlier blocks [I] |
| Ni-kshay / NTEP | One platform for notification, adherence monitoring, DBT; Ni-kshay Mitra community support with grievance redressal ([guidance booklet](https://communitysupport.ni-kshay.mohfw.gov.in/Guidance_Booklet_16_09_2022.pdf)). Dashboard internals not found in search [S] | Officers expect "payment stuck", Mitra/Supporter activity, and a grievance path; mirror Ni-kshay vocabulary [I] |
| Khushi Baby | Designed with mothers, nurses, officials for limited literacy; Telugu replication "AMMA KOSAM" in East Godavari ([CIPS](https://cips.org.in/replication/amma-kosam), [UNESCO](https://unesdoc.unesco.org/ark:/48223/pf0000260596)); offline-ready apps [S] | Telugu strings tested with a native speaker; co-design claim only if you do a 10-minute hallway test [I] |
| ASHA apps (mSakhi, Gyan Jyoti) | Voice guidance, illustrations, icon menus; no usability numbers published ([mSakhi](https://www.mbillionth.in/?p=11551), [Gyan Jyoti](https://thecompassforsbc.org/sbcc-spotlights/gyan-jyoti-generating-fp-demand-mobile-phones)) [S] | Icon-first buttons; voice playback is P2 [I] |
| AI-in-clinic UI (practitioner blogs, low evidence) | Bare percentage is not enough; give context and guidance when uncertain; overrides always possible and logged; layered explanations ([Halo Lab](https://www.halo-lab.com/blog/designing-for-clinical-trust-ui-ux-governance-ai-adoption), [HackerNoon](https://hackernoon.com/when-ai-makes-medical-decisions-designing-human-in-the-loop-clinical-systems)) [S, weak] | Matches spec 03's evidence-first design; add plain-language uncertainty labels and an audit tab [I] |
| WCAG 2.2 | New AA: target size min 24x24 CSS px (2.5.8), dragging needs a click/tap alternative (2.5.7), focus not entirely obscured (2.4.11); Focus Appearance is AAA ([W3C](https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/)) [S] | Lens slider needs step buttons (spec has ◀ ▶, good); sticky headers must not cover focus [I] |
| shadcn/ui | Radix gives focus trap, ARIA, keyboard nav; one 2026 vendor audit says default focus rings can miss 3:1 contrast ([audit](https://thefrontkit.com/blogs/shadcn-ui-accessibility-audit-2026)) [S, vendor] | Use it, but override the focus ring token [I] |
| Colour-blind safety | Do not use red/green alone; pair colour with shape/label; Okabe-Ito set; test in greyscale ([overview](https://alexpoole.info/blog/icon-design-with-useful-redundancy/)) [S] | Spec's ▲ ● ✓ plus word already passes; change the hues (section E) [I] |
| DPDP Rules 2025 | Itemised plain-language notice, English or an Eighth Schedule language (Telugu qualifies); sources disagree on the exact scope; consent-manager rules start 13 Nov 2026 ([EY](https://www.ey.com/content/dam/ey-unified-site/ey-com/en-in/pdf/2025/11/dpdp-act-and-rules.pdf), [tsaaro](https://tsaaro.com/blogs/dpdp-rules-2025-explained-full-overview-and-practical-summary)) [S, verify primary] | Consent screens show purpose per source in Telugu; "synthetic data" banner avoids real-PII claims [I] |
| Hackathon demos | Record a backup video, screenshot key screens, show the payoff, hardcode the path if needed ([reskilll](https://blogs.reskilll.com/hackathon-demo-presentation-tips-pitch-3-minutes-win-2026/)) [S] | Offline replay tab is already planned; add a visible "REPLAY" state so it is honest [I] |

Not found: Telegram Mini-App limits, Ni-kshay dashboard layout, Telugu button-size studies. Treat anything on those as [I].

## 2. Gaps in the planned screens (summary)

Spec 03 has no: dark mode or high-contrast; a "today" landing strip; undo; diff view for edits; why-this-flag; per-item audit view; mock-data banner; data-freshness stamps; keyboard help; notification centre; Supporter outcome undo; a judge guide overlay; a live agent trace; calibration view; Telugu toggle on every patient/Supporter string; an offline indicator in the console shell.

## A. Prioritised ADD-LIST (30)

H1 = doctor console (Sonnet), H2 = district/demo/admin (Haiku). Hours are build hours on fixtures.

| # | Feature | Screen | Why | Pri | h | Lane |
|---|---|---|---|---|---|---|
| 1 | "Today" strip: counts of Red due, visits due, overdue, items expiring in 2 h | Queue + patient list header | Today view + risk worklist norm (Simple call list [S]) | P0 | 3 | H1 |
| 2 | "Why this flag" popover on every tier badge: rule id, threshold hit, counter-evidence, what would clear it | Queue, patient page | Layered explanation, [S weak]; judge Q "why Amber?" [I] | P0 | 2 | H1 |
| 3 | Word-level diff of doctor edit vs AI proposal, with reason chips (wrong fact / tone / too long / missing) | Queue edit mode | Overrides logged and learnable [S weak]; feeds `edit_examples` [I] | P0 | 2.5 | H1 |
| 4 | 10 s undo toast after Approve/Reject, only until outbox drains | Queue | Safe one-tap actions [I] | P0 | 1.5 | H1 |
| 5 | Live agent trace panel: node, tool call, citations found, validator cuts, streaming via SSE | Demo console + "How this card was made" drawer | Judge transparency [I] | P0 | 3.5 | H2 |
| 6 | Persistent "SYNTHETIC DATA, NOT REAL PATIENTS" banner and masked IDs by default | App shell | Privacy cue; DPDP posture [I] | P0 | 0.5 | H1 |
| 7 | Plain-language uncertainty label beside every interval ("Low confidence: 12 days of data") | RiskInterval | Bare % insufficient [S weak] | P0 | 1 | H1 |
| 8 | Data-freshness chips per source ("Chemist d46, 2 days late") | Patient overview, drawer | Real feeds lag; trust [I] | P0 | 1.5 | H1 |
| 9 | Overdue/call list: patients past due by N days, sorted by risk, one-tap "call / assign visit" | Clinic dashboard | Simple.org call list [S] | P0 | 2.5 | H1 |
| 10 | Connection chip: Live / Polling / Offline replay, plus red-bordered REPLAY banner | Shell | Honest fallback [I] | P0 | 1.5 | H2 |
| 11 | Persona switcher chips (Dr. Prasad, Lakshmi, DTO, Admin, Judge) with one-click login | Login + shell | Judges as actors (Story doc) [S local] | P0 | 1.5 | H2 |
| 12 | "Judge guide" overlay: three things to touch, then reset | Demo console | Judge-interactive [I] | P0 | 2 | H2 |
| 13 | Colour-blind-safe tier tokens + greyscale test page | Tokens | See E [S] | P0 | 1 | H1 |
| 14 | "All clear" empty state with day summary (approved N, edited M, sent K) | Queue | Calm for busy GP [I] | P0 | 0.5 | H1 |
| 15 | Per-item audit tab (who, when, what, source, hash) | Queue item, patient | Audit trail [S weak] | P1 | 2 | H1 |
| 16 | Citation hover preview (first 120 chars of event) | CitationChip | Faster evidence check [I] | P1 | 1.5 | H1 |
| 17 | Escalation stepper (Doctor, STS, DTO) with live countdown | Red item | Spec has timer only [I] | P1 | 1.5 | H1 |
| 18 | Calibration/reliability plot and coverage badge | Eval console | Credibility with technical judges [I] | P1 | 2 | H2 |
| 19 | Timeline replay (play day 1 to 60, events animate in) | Timeline tab | Animated timelines land [I] | P1 | 2 | H1 |
| 20 | Dark mode and high-contrast toggle | Shell | Clinic night shifts [I] | P1 | 2 | H1 |
| 21 | Keyboard help sheet (`?`), `g q`/`g p` navigation, Ctrl-K patient search | Shell | Busy-user speed [I] | P1 | 2 | H1 |
| 22 | Notification bell, grouped digest, quiet hours | Shell | Notification pattern [I] | P1 | 2 | H1 |
| 23 | Call outcome log (agreed / unreachable / wrong number / removed) | Overdue list | Simple.org outcomes [S] | P1 | 2 | H1 |
| 24 | Q&A: suggested-question chips and "show tools used" footer | Q&A | Provenance [I] | P1 | 1 | H2 |
| 25 | Thumbs and reason on approved cards ("useful?") | Queue | Closes the learning loop [I] | P1 | 1 | H1 |
| 26 | Outlier flags on block table (modified z-score) | District | DHIS2 [S] | P2 | 2 | H2 |
| 27 | One-page printable patient summary (referral) | Patient page | Paper still rules in clinics [I] | P2 | 2 | H1 |
| 28 | Consent ledger timeline with withdraw demo | Consent tab | DPDP [S] | P1 | 1.5 | H2 |
| 29 | Block choropleth | District | Officer expectation [I] | P2 | 3 | H2 |
| 30 | Grievance/feedback link per Supporter (Ni-kshay Mitra framework) | District, Supporter table | Ni-kshay has grievance redressal [S] | P2 | 1 | H2 |

P0 total about 29 h. That is too much for H1 plus H2 on top of spec 03's 48 P0 h. Build items 1, 2, 4, 5, 6, 10, 11 first, then the rest by rank [I].

## B. Top 10 for the demo (ranked)

1. **Agent trace panel (#5).** The live proof that the system "thinks with citations".
2. **Why-this-flag (#2) plus citation click-through (spec).** Answers the first judge question.
3. **Persona switcher (#11) and judge guide (#12).** Judges become Dr. Prasad and Lakshmi in 5 seconds.
4. **Undo toast (#4).** Shows human control; makes live approval safe.
5. **Edit diff (#3).** Visible human-in-the-loop moment; ties to the learning curve.
6. **Uncertainty labels (#7).** Pairs with the Lens funnel and the Day 3 vs Day 60 story.
7. **Connection chip and REPLAY banner (#10).** Turns a failure into a feature.
8. **Today strip (#1) and overdue list (#9).** Shows the doctor's first minute.
9. **Synthetic-data banner (#6) and freshness chips (#8).** Cheap trust signals.
10. **Colour-blind tokens (#13).** Take 1 h; accessibility questions are common.

## C. Keep it simple (do not build in 36 h)

| Skip | Why |
|---|---|
| Map choropleth, drill-through geography | Table plus bar is enough; spec 03 already cuts P1 panels [I] |
| Full native app or Telegram Mini App | Bot inline keyboards plus PWA cover it [I] |
| Voice playback/recording in Telugu | P2 in spec (P-17); accuracy unverified [I] |
| Drag-and-drop anywhere | WCAG 2.5.7 needs alternatives; doubles work [S] |
| Custom chart library or D3 | Recharts with "show as table" |
| Per-user theme builder, role editor UI | Role switcher plus a fixed dark mode is enough |
| Real-time collaborative editing, comments threads | Single doctor per clinic in demo |
| Full i18n of the doctor console | Telugu only on patient/Supporter strings |
| Pixel-perfect print layouts | CSV plus browser print |
| Custom component library | Use shadcn/ui |
| Complex notification preferences | Fixed quiet hours |

## D. Mobile Supporter and patient screens (order of use)

Targets: 360 px wide, 48 px minimum touch (WCAG 24 px is the floor, not the goal) [I]; one task per screen; Telugu default with English toggle; icons plus words; no scrolling for the primary action [I].

**Supporter (Lakshmi): PWA first, Telegram for push**
1. Language pick (Telugu/English), big flags-free text buttons.
2. Sign-in via one-time link or invite code (no password).
3. Consent read-back screen: one source per card, Yes/No, witness confirm (S-07).
4. **Today list:** 6 cards max, rank 1 to 6, patient number, first name, why-icon, distance/time; offline badge.
5. Patient card: one-line reason ("missed 6 of 8 Thursdays"), no risk number, no diagnosis words.
6. Visit outcome: Witnessed / Told / Unreachable / Family screen, then a 5 s undo.
7. Quick measures: weight, payment seen (passbook), numeric keypad only.
8. Escalate button with a one-line note (S-09).
9. Sync status: "3 saved, will send" and a manual retry.
10. My week summary (S-10), optional.

**Patient (Ravi): Telegram first**
1. `/start` deep link, language, one consent card per source.
2. Daily check-in: Taken / Not yet / Missed, three big buttons.
3. Weekly 8 yes/no questions with "I feel unwell" always visible.
4. Monthly payment and weight prompts.
5. `/mydata` (counts per source) and `/stop` withdraw with a confirm.

## E. Design-system recommendation

**Stack:** Tailwind + shadcn/ui (Radix) for dialog, popover, tabs, tooltip, toast, command (Ctrl-K), table, select, checkbox, switch. Tailwind-only for the Supporter PWA (smaller bundle on basic Android, **[I]**: measure with Lighthouse on a throttled profile). Override focus ring to 3 px, 3:1 contrast [S audit].

**Palette (tokens in `tokens.css`; light / dark)**

| Token | Light | Dark | Use |
|---|---|---|---|
| ink | #101828 | #F2F4F7 | text (>=7:1 on bg) |
| bg | #FFFFFF / #F8FAFC | #0B1220 | surfaces |
| brand | #1D4ED8 | #7AA2FF | links, primary buttons, focus |
| red | #B42318 | #FF8A80 | Red tier |
| amber | #A15C00 | #FFC857 | Amber tier |
| green | #067647 | #6EE7A8 | Green tier |
| grey | #667085 | #98A2B3 | ask-only, disabled |
| verified / self-report | brand solid / grey dashed | same | chart series |

Check every pair with a contrast tool before freeze; amber on white is the usual failure [I].

**Risk-colour rules**
1. Colour never stands alone: icon (▲ ● ✓) plus word plus a 4 px left border pattern (solid / diagonal / none) [S principle].
2. Green means "no action needed", not "safe". Tooltip: "ranks follow-up, does not diagnose".
3. Charts use the brand blue and an orange (#D55E00 family) for the contrast series; reserve red for Red-tier only [S: blue/orange safer].
4. Interval always shown; a wide interval greys the tier fill ("low confidence").
5. Dark mode: lighter tints for text, same icons.

**Type and spacing**

| Item | Value |
|---|---|
| Font | Inter (Latin) plus Noto Sans Telugu; system fallback for offline |
| Scale | 12 / 14 / 16 / 20 / 24 / 32 px; doctor body 14, district 16, Supporter 18 (Telugu needs more height; line-height 1.6) |
| Spacing | 4 px base: 4, 8, 12, 16, 24, 32 |
| Touch | Console min 32 px; Supporter and patient min 48 px with 8 px gaps |
| Radius | 8 px cards, 999 px chips |
| Motion | 150 ms; `prefers-reduced-motion` disables timeline replay animation |

**Components (build list):** TierBadge, RiskInterval, UncertaintyLabel, CitationChip (plus hover preview), EventDrawer, WhyFlagPopover, DiffView, UndoToast, TodayStrip, FreshnessChip, ConnectionChip, SyntheticBanner, MaskedId, KpiTile, SuppressedNumber, AgentTracePanel, PersonaSwitcher, EmptyState, Skeleton.

**Icons:** Lucide (outline, consistent, tree-shakable, **[I]** from general knowledge; not verified in search). Every icon-only button gets an `aria-label`.

**Charts:** Recharts, 2 px lines, direct labels, solid = verified and dashed = self-report, shaded band = 90% CI, "show as table" on each, no 3D, no pie; same time axis (sim day) across charts.

**Accessibility baseline (WCAG 2.2 AA):** 4.5:1 text, 3:1 UI and focus, keyboard path for every action, visible focus not hidden by sticky bars (2.4.11), 24 px targets minimum (2.5.8), alternatives to slider drag (2.5.7), `aria-live="polite"` on queue, labelled form fields, same Help link position on every page (3.2.6) [S: W3C].
