> **Scoring update (organisers' latest message, 24 Oct 2026): use 40 / 60, not 15 / 35 / 50.**
> The event now has two scored rounds. Round 1 (idea and solution presentation, plus the evaluation form with the
> GitHub Repository Progress Tracker for software teams) is worth **40%**. Round 2 (final build and defence) is worth
> **60%**. Grand total 100. Companies judge technical skill, implementation and development progress through regular,
> feature-level commits. The older 15/35/50 three-round plan below is kept for history; where it disagrees, this note wins.
>
> **Round 2 rubric (raw maximum 50, scaled to the 60% weight):**
>
> | # | Criterion | Raw max | Share of 100 (x1.2) | What we show (see README "Evaluation mapping") |
> |---|---|---|---|---|
> | 1 | Functionality and working demo | 15 | 18 | Doctor approves a request in the console; the patient screen changes; a Telegram tap becomes an event and a Red draft |
> | 2 | Technical depth and code quality | 10 | 12 | DB-level doctor gate, single `decide()` transaction, budget governor, cite-or-cut, 220+ automated tests |
> | 3 | UI/UX and usability | 5 | 6 | Responsive doctor console and patient app, Telugu toggle, large text, empty states |
> | 4 | Completeness vs proposed scope | 5 | 6 | TRACKER.md: feature slices with honest done / partial / planned status |
> | 5 | Viability and deployment readiness | 5 | 6 | Cost caps and RED template mode, consent, PII tokenisation, GCP scripts in `infra/` |
> | 6 | Q&A handling and team contribution | 5 | 6 | Lane ownership table, OpenSpec change log per feature |
> | 7 | Final presentation and demo delivery | 5 | 6 | Ravi's Day 3 vs Day 60 story, rehearsed demo script |
> | | **Total** | **50** | **60** | |

---

# Evaluation framework -> what we do, in what order

Source: the Innovators Conclave 2026 evaluation page (screenshot `evaluation_framework.jpg` in this folder).
3 evaluators per round, each scores 100. Final = 15% R1 + 35% R2 + 50% R3. Max 100.

## What each round rewards
| Round | Weight | Criteria (each scored) |
|---|---|---|
| 1 Idea and Solution Presentation | 15% | Solution/idea, Innovation, Solution approach, Technical soundness/feasibility, Execution timeline |
| 2 Prototype Development and Integration | 35% | Prototype development, Improvement (after evaluator/mentor feedback), Integration (components work together), Usability, Team work |
| 3 Final Demo and Market Readiness | 50% | Performance/final demo (real-world scenarios, clarity), UX and design, Market readiness/impact, Implementation plan/future scope |

Reading it plainly: 85% of the marks are for something that WORKS and is USABLE.
Round 3 alone is half. A beautiful idea with a shaky demo loses.

## Build order (matches the order you gave)
| Step | What | Why it scores | Done when |
|---|---|---|---|
| 1 | Responsive UI, doctor + patient, laptop and phone (previews done) | R2 Usability, R3 UX and Design | Both UIs run in a browser and fit 360px to 1440px |
| 2 | UI with real backend and database, empty states first, then seeded data | R2 Prototype Development | Doctor can approve a request and the patient screen changes |
| 3 | Telegram (patient taps, reminders) | R2 Integration, R3 Performance | A tap on a phone creates an event and shows in the doctor portal within seconds |
| 4 | Gmail (digest out, approve by reply) | R2 Integration | Reply "approve 1" resumes the paused item |
| 5 | Any further channels (Calendar, chemist CSV) | R2 Integration | Only if steps 1-4 are solid |
| 6 | Google Cloud deploy (Cloud Run, Tasks, SQL) | R3 Performance, Market readiness | Public URL works from a phone on mobile data |
| 7 | Mock data load (prompt in MOCK_DATA_PROMPT.md) | R3 demo clarity | Day 3 vs Day 60 demo runs from a seed script |
| 8 | Rehearsal and cut list | R3 | Demo runs twice end to end without help |

## Per-criterion checklist (what evaluators will look for)
- Idea / Innovation (R1): one sentence, "memory that a doctor approves". Show Day 3 vs Day 60.
- Technical soundness (R1): the diagram pack (framework architecture, data flow). Say "rules decide, AI only explains, doctor approves".
- Execution timeline (R1): the phase table in WORK_BREAKDOWN.md when it lands.
- Prototype (R2): live URL, not slides.
- Improvement (R2): keep a visible "what we changed after feedback" list. Log every mentor comment and the fix. This is a scored line on its own.
- Integration (R2): show one event travelling UI -> Telegram -> core -> doctor -> Gmail. The data-flow PNG is the map.
- Usability (R2/R3): large buttons, plain words, works on a cheap phone, Telugu/English toggle.
- Team work (R2): each person owns a lane; say who built what.
- Performance (R3): quick responses, no spinner dead ends. Pre-warm Cloud Run (min instances 1) before judging.
- Market readiness (R3): safety story (doctor gate, consent, no advice), cost per patient, path to a pilot clinic.
- Implementation plan (R3): after-hackathon roadmap, 3 bullets.

## Risks
- Round timings and what is shown in each round are not on the screenshot. Confirm with the organisers.
- Do not spend R2 time on extra channels before the core loop works.
