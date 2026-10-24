# CareMemory: Ravi's Story and Complete Feature Catalogue

*Day 3, it reminds. Day 60, it understands.*

IC26-03-10 · Open Innovation · NTEP. In the brief, the human treatment supporter is called "Saathi". In the product and the deck, we say **Supporter**.

---

## How to use this document

- **Part A** is the spoken pitch: a 3-minute version, a 60-second version, delivery craft and judge interruptions.
- **Part B** is the full feature catalogue, grouped by user surface, with a priority and build hours for each feature, followed by the roadmap and a "what we might be missing" list.

**Deck order** (from `deck.json`): 7 slides.

| # | Slide file | What it shows |
|---|---|---|
| 1 | `cover.html` | Ravi's 6-month dot strip (green taken, red unseen, grey lost) and the brief-to-slide map |
| 2 | `problem.html` | Five stats and six disconnected people |
| 3 | `howitworks.html` | One day in Ravi's care, as a swimlane, plus the channel table |
| 4 | `memory.html` | The Memory Lens: Day 3 vs Day 60, a slider and cited flags |
| 5 | `trust.html` | Opt-in levels, the doctor review queue (live Gmail) and the Supporter evening |
| 6 | `architecture.html` | "Statistics decide. The AI only explains." |
| 7 | `impact.html` | Live evaluation re-roll, the district dashboard and the ask |

Four more files are **not in the deck order**: `whyfail.html`, `solution.html`, `demo.html` and `close.html`. Keep them as backup slides for Q&A (see A.6).

**Stat rule:** speak only these verified numbers. Ravi's own numbers (risk 0.12 → 0.58, "6 of 8 Thursdays", "9 → 85 minutes") are **synthetic target values from our generator**, and we say so.

| Stat | Use it in |
|---|---|
| India has ~25% of the world's TB cases and ~28% of TB deaths | Beat 5 |
| 26.18 lakh TB cases notified in 2024 | Beat 5 |
| 14.6% of patients lost before treatment starts (2013 data) | Q&A, district cascade |
| Of patients 99DOTS flagged as missing doses, only 21% truly had | Beat 5 |
| 62% received even one nutrition payment (2021) | Beat 4 (optional line), payments panel |
| Drug-resistant TB treatment success is ~71% | Q&A on the drug-resistance rule |
| Lancet 2025 trials: digital reminders alone gave no significant gain | Beat 5, Q&A |
| Nutrition support is ₹1,000/month | Beat 4 |
| Treatment takes at least 6 months (2 intensive + 4 continuation) | Beat 2 |

---

# PART A: Ravi's Story

## A.1 The cast (keep these names consistent everywhere)

| Who | Detail | Why it matters |
|---|---|---|
| **Ravi**, 32 | Anantapur. Daily-wage loader. On **Thursday market days** he is at the mandi before 5 am, lifting tomato crates. Cracked-screen phone, shared with his wife in the evenings | His Thursday is the pattern the memory learns |
| **Sunitha** | His wife. Keeps his tablet strip in a steel box beside the wall calendar | Sensory anchor; family stake |
| **Meena**, 8 | His daughter. Wakes at night to his cough | The callback at the end |
| **Dr. Prasad** | Private GP in Anantapur, about 15 TB patients | The human who decides |
| **Lakshmi** | ASHA worker and Ravi's chosen Supporter | The human who visits |
| **Kavya** | Another patient (backstage) | Shows the red drug-resistance rule firing, without changing Ravi's story |

**Ravi's two timelines**

| Day | Without CareMemory | With CareMemory |
|---|---|---|
| 0 | Diagnosed; 6-month prescription | Diagnosed; opts in to Telegram, Lakshmi and chemist records |
| 1–21 | Feels better, back at work | 07:50 check-ins; memory says "I don't know him yet" |
| 4 | — | Lab report read; regimen matches; rule passes |
| 28 | Refill due, not bought | Refill due |
| 30 | — | Conflict: "Taken" taps but no refill → brief → doctor approves → Lakshmi visits |
| 35 | Portal says ₹1,000 paid; Ravi never got it | Payment conflict flagged to doctor and district |
| 42 | — | Thursday pattern confirmed; "misses Sundays" retired as wrong |
| 44 | — | Refill bought; conflict closed, with citation |
| 50 | Stops tablets | — |
| 52 | — | Reply time jumps 9 → 85 min; drift flagged |
| 56 | Month-2 sputum report sits unread in an inbox | Sputum result pinned to the timeline |
| 60 | Nobody has noticed | Card: "Visit Wednesday evening, before market day." Doctor approves |
| 90 | 40 days unseen: lost | Continuation phase, Lakshmi brings the Thursday dose on Wednesdays |
| 180+ | — | Treatment completed |

---

## A.2 The 3-minute version (beat by beat)

Target: **about 420 spoken words.** The demo actions run while you speak, so the words stay short.

| Time | Beat | Slide |
|---|---|---|
| 0:00 | 1. Meet Ravi | 1 Cover |
| 0:20 | 2. Diagnosis day | 1 Cover |
| 0:30 | 3. Weeks 1–3 | 1 Cover |
| 0:38 | 4. The quiet slide | 1 Cover (point at the red dots) |
| 0:55 | 5. Six people, six pieces | 2 Problem |
| 1:15 | 6. What if someone remembered? | 3 How it works |
| 1:45 | 7a. Day 3 vs Day 60 | 4 Memory (live slider) |
| 2:10 | 7b. The doctor decides | 5 Trust (live Gmail and Telegram), 6 Architecture (one line) |
| 2:35 | 8. The ending | 7 Impact (live re-roll) |
| 2:50 | 9. The ask | 7 Impact |

---

### Beat 1: Meet Ravi (0:00–0:20) · Slide 1, Cover

> "This is Ravi. He's thirty-two, from Anantapur. He loads trucks for a daily wage. Thursday is market day, so he's at the mandi before five, lifting tomato crates.
> At home there's his wife Sunitha, and Meena, eight, who wakes up every night to her father's cough.
> Ravi is an illustrative patient, built from real patterns. Every statistic you'll hear today is real."

| Delivery | |
|---|---|
| Pause | A full beat of silence after "This is Ravi." Let the room look at the dots |
| Eye contact | Pick one judge and tell them about Ravi as if he were your neighbour |
| Gesture | An open palm toward the screen on "This is Ravi"; mime lifting a crate on "tomato crates" (small, not theatrical) |
| Honesty line | Say "illustrative patient" plainly and early. It buys trust for everything that follows |

### Beat 2: Diagnosis day (0:20–0:30) · Slide 1

> "Dr. Prasad tells him: it's TB, and it's curable. Take these tablets every day for at least six months. Ravi folds the prescription into his shirt pocket. Sunitha puts the strip in a steel box, next to the calendar."

| Delivery | |
|---|---|
| Pause | Slight pause after "it's curable". It is the hopeful note |
| Gesture | Tap your shirt pocket on "shirt pocket" |
| Tip | Slow down. The sensory details (pocket, steel box, calendar) make him real |

### Beat 3: Weeks 1–3, feeling better (0:30–0:38) · Slide 1

> "Three weeks later the cough eases. He's eating again. He's back at the mandi. He feels cured."

| Delivery | |
|---|---|
| Tone | Light, almost happy. You are setting up the trap |
| Pause | A long pause after "He feels cured." That is the turn |

### Beat 4: The quiet slide (0:38–0:55) · Slide 1, point at the red dots

> "That's when it quietly slides. On Thursdays he leaves at five, and the tablets stay in the box.
> Day twenty-eight, his refill is due. He doesn't buy it.
> The thousand rupees a month for food? The portal says paid. Ravi never got it.
> Day fifty-six, the lab sends his sputum report. It sits in an inbox.
> By day ninety, nobody has seen Ravi for forty days."

*Optional line, if time allows:* "And he's not unusual: in 2021, only 62% of patients got even one nutrition payment."

| Delivery | |
|---|---|
| Gesture | Walk your hand along the dot strip: green, then red, then grey |
| Pace | One sentence per fact, with a short pause between each. Let the silence feel like the 40 days |
| Voice | Drop your volume slightly on "nobody has seen Ravi" |

### Beat 5: Six people, six pieces (0:55–1:15) · Slide 2, Problem

> "Six people each knew one piece. Ravi knew he skipped Thursdays. The chemist knew no refill was sold. The portal said 'paid'. The lab had the result. Dr. Prasad knew what he prescribed. And Lakshmi, his Supporter, hadn't visited in weeks.
> Nobody held all six.
> India has about a quarter of the world's TB: 26.18 lakh people notified last year. Self-reports mislead: of patients 99DOTS flagged as missing doses, only 21% truly had. And Lancet trials in 2025 found that digital reminders alone gave no significant gain.
> Ravi didn't need another reminder."

| Delivery | |
|---|---|
| Gesture | Count the six people on your fingers, one per role. Point at each node on the slide |
| Pause | After "Nobody held all six." |
| Tip | Say the stats fast and flat; let the slide carry the rest (62% and ~71% are on screen). Land hard on the last line |

### Beat 6: "What if someone remembered?" (1:15–1:45) · Slide 3, How it works

> "So we asked: what if someone remembered? Same Ravi, same sixty days, now with CareMemory.
> Day zero: Ravi opts in to three things: a Telegram check-in, Lakshmi, and his chemist's records. Everything else stays off.
> Day one, 7:50 am: 'Did you take today's tablet?' Taken.
> Day four: the lab report arrives, the regimen matches, and a safety rule quietly passes.
> Day thirty: the chemist sold no refill, but Ravi keeps tapping 'Taken'. Overnight, CareMemory drafts a brief with three cited events. At nine, Dr. Prasad approves it. At six, Lakshmi is at Ravi's door. She counts the pills and finds out why: the thousand rupees never came, so he's stretching the strip. That payment flag now goes to the district too."

| Delivery | |
|---|---|
| Gesture | Trace the swimlane left to right as you say each time: 07:50, 13:00, 02:00, 09:00, 18:00 |
| Tone | Warmer and faster. This is the hopeful replay |
| Tip | "What if someone remembered?" is the hinge. Stop, look at the judges, then say it |
| Demo cue | None yet. A teammate opens the console on the Memory Lens, slider at Day 3 |

### Beat 7a: Day 3 vs Day 60 (1:45–2:10) · Slide 4, Memory, **LIVE**

> "Here's what no reminder can do. Day three: it says 'I don't know Ravi yet.' Risk 0.12, wide uncertainty, seven unknowns.
> [drag the slider]
> Day sixty: it knows he misses market-day Thursdays, six of eight. It trusts Lakshmi's word over his own taps. It saw his replies slow from nine minutes to eighty-five. And it threw out its own wrong guess about Sundays, right there on screen.
> Its suggestion: visit Wednesday evening, before market day.
> These are target values from our synthetic generator."

| Delivery | |
|---|---|
| **Demo cue** | Drag the Memory Lens slider from Day 3 to Day 60 **slowly** (about 4 seconds). The funnel narrows and the beliefs appear. Click one citation ("16 'Taken' taps, no refill") to open the chemist CSV rows |
| Pause | Stop talking while the slider moves. Let the screen do it |
| Gesture | Point at "Retired: 'misses Sundays'". Admitting a mistake is the credibility moment |
| Fallback | If the live console fails, the slide itself shows both states. Say "here it is from this morning's run" and carry on |

### Beat 7b: The doctor decides (2:10–2:35) · Slide 5, Trust → Slide 6, Architecture, **LIVE**

> "But the AI doesn't decide. Dr. Prasad does. Today, you're Dr. Prasad.
> [Judge replies 'Approve' in Gmail]
> Approved. Lakshmi's phone buzzes.
> [Second judge taps 'Witnessed']
> Witnessed. That decision goes straight back into memory.
> [Slide 6] Under the hood: statistics find the patterns, a language model only writes the note, and a validator deletes any sentence without evidence."

| Delivery | |
|---|---|
| **Demo cue 1** | Before the pitch, hand Judge A a laptop or phone with the Gmail digest open. On cue they reply "Approve" (or edit one word). The console shows the confirmation echo |
| **Demo cue 2** | Judge B holds the "Lakshmi" phone. The Telegram brief arrives; they tap "Visited – witnessed" |
| **Demo cue 3** | As you say "Approved", a teammate starts the judge-seed re-roll (it takes about 20 s, so it is ready for Beat 8) |
| Gesture | Physically hand the decision to the judge: an open palm toward them on "you're Dr. Prasad" |
| Tip | Spend 5 seconds on slide 6. One sentence, then advance |
| Fallback | Offline replay with simulated Gmail and Telegram, already loaded in a second tab |

### Beat 8: The ending (2:35–2:50) · Slide 7, Impact, **LIVE**

> "In the first story, day sixty is where we lost Ravi. In this one, Lakshmi brings his Thursday tablet on Wednesday night. He's gained two kilos.
> Day one-eighty: every dot is green. Ravi finishes treatment.
> And Meena sleeps through the night.
> [Point at the chart] You picked the seed: two hundred patients, re-scored live against hidden answers, with misses shown."

| Delivery | |
|---|---|
| **Demo cue** | The re-roll result lands. Point at the rising learning curve and at the "missed" count |
| Pause | A full two seconds after "Meena sleeps through the night." This is the emotional callback to Beat 1 |
| Eye contact | Return to the same judge you started with |

### Beat 9: The ask (2:50–3:00) · Slide 7

> "Our ask: an Anantapur district pilot with the District TB cell and a Ni-kshay data agreement, measured by one number: fewer patients lost to follow-up.
> Ravi doesn't need another reminder. He needs someone who remembers.
> Day 3, it reminds. Day 60, it understands. Thank you."

| Delivery | |
|---|---|
| Tone | Steady, slower, lower pitch |
| Gesture | Hands still. No pointing |
| Tip | Stop after "Thank you." Do not add "so yeah". If `close.html` is added to the deck, advance to it on "someone who remembers" |

---

## A.3 The 60-second version

Use it for the elevator round, a video or when the timer is cut. About 150 words. Slides: Cover → Memory → Impact.

| Time | Slide | Say |
|---|---|---|
| 0:00 | Cover | "This is Ravi, 32, a daily-wage loader in Anantapur. Illustrative, but built from real patterns. TB is curable with at least six months of daily tablets." |
| 0:10 | Cover | "Three weeks in, he feels better. He skips market-day Thursdays, misses a refill, his ₹1,000 food support never arrives, and a lab report sits unread. Six people each held one piece. By day ninety, nobody had seen him for forty days." |
| 0:25 | Memory | "CareMemory joins the pieces. On Day 3 it admits it knows nothing. By Day 60 it has learned his Thursdays, caught 16 'Taken' taps with no refill, and noticed his replies slowing. It suggests a Wednesday visit." |
| 0:42 | Memory | "Statistics find the patterns. The AI only explains, with citations. A doctor approves every step." |
| 0:50 | Impact | "Our ask: an Anantapur district pilot, measured by fewer patients lost to follow-up. Ravi doesn't need another reminder. He needs someone who remembers." |

---

## A.4 Techniques that make it feel genuine

| Technique | How we use it | Why it works |
|---|---|---|
| **One name, early** | "This is Ravi" in the first three words | People care about a person, not a percentage |
| **Specific sensory details** | 5 am mandi, tomato crates, the steel box beside the calendar, the prescription folded in his shirt pocket, Meena waking to the cough | Specifics read as true; generalities read as marketing |
| **One honest line** | "Ravi is an illustrative patient, built from real patterns." Later: "These are target values from our synthetic generator." | Disarms the "is this real?" doubt before a judge raises it |
| **Show a mistake** | The retired "misses Sundays" belief, and the "missed" count on the evaluation | A system that admits errors is believable |
| **Same story twice** | Days 0–90 without, then days 0–60 with | Contrast does the persuading; no adjectives needed |
| **Judges as actors** | Judge A is Dr. Prasad in Gmail; Judge B is Lakshmi on Telegram; a judge picks the seed | Judges believe what they did themselves |
| **Callback** | Meena waking at night (Beat 1) → "Meena sleeps through the night" (Beat 8). "Another reminder" (Beat 5) → "someone who remembers" (Beat 9) | Closes the loop; the room remembers the line |
| **The rule of one** | One patient, one district, one success metric | Easy to repeat in the judges' deliberation room |
| **Silence** | Pauses after "He feels cured", "Nobody held all six" and "Meena sleeps" | Silence signals confidence |
| **Plain words** | "Statistics decide. The AI only explains." Never "leveraging agentic paradigms" | Health judges trust plainness |

**Rehearsal rules**
- Rehearse five times with a stopwatch; cut words, never pauses.
- The speaker never touches the laptop. One teammate drives the console; one manages the judge phones.
- Memorise Beats 1, 5 and 9 word for word. Paraphrase the rest.

---

## A.5 Five likely judge interruptions, answered inside the story

| # | Interruption | In-story answer | Show |
|---|---|---|---|
| 1 | **"Ravi isn't real and your data is synthetic. Isn't your accuracy circular?"** | "Fair, and that's why you picked the seed. The generator hides Ravi's real habits in an answer file only the scorer reads. Twenty percent of patients have no pattern at all, and we show what the memory missed. It proves the method, not clinical value. Clinical value is exactly what the Anantapur pilot measures." | `impact.html`: the "missed" and "false, retired" tiles |
| 2 | **"Isn't this just 99DOTS again? The Lancet said reminders don't work."** | "We agree with the Lancet. Look at Ravi: the reminder didn't save him. Lakshmi's Wednesday visit did. CareMemory decides where a scarce human visit should go. And of patients 99DOTS flagged as missing doses, only 21% truly had, so we check self-reports against the chemist and the Supporter instead of trusting them." | `whyfail.html` (backup) |
| 3 | **"What if Ravi has no smartphone, or just stops replying?"** | "Then Lakshmi is his channel. Watch: we turn Telegram off. [toggle] The card shrinks and the uncertainty widens, and the screen says it will learn about four times slower. But the refill and payment rules still fire from the chemist and portal records alone. Nobody is excluded for not owning a phone." | Console: channel toggle on Ravi's page |
| 4 | **"Will the AI hallucinate, or diagnose? Who is liable?"** | "Every sentence on Ravi's card cites an event ID. A validator deletes any sentence without a citation or with a wrong number, and falls back to a template. Then Dr. Prasad approves it. The risk score only ranks who Lakshmi visits first. It never diagnoses or changes a dose. For Kavya, whose lab result didn't match her regimen, the system raised a red flag to the doctor; it did not change her medicines. That matters, because drug-resistant TB treatment success is only about 71%." | `architecture.html`, `memory.html` citations |
| 5 | **"Dr. Prasad has a full clinic. Who has time to review all this?"** | "Ravi's day-30 brief took one email reply. Red items, like Kavya's, come immediately and escalate to the TB supervisor after four hours. Amber items come in one morning batch with bulk approve. Green template messages are sampled 10%. Our estimate is about five minutes a day for a GP with 15 patients, and we'll measure it in the pilot." | `trust.html` queue |

**Two bonus answers**

| Interruption | Answer |
|---|---|
| "Day 60 is too late." | "The rules caught Ravi's refill gap on day 30 and his payment on day 35. Memory doesn't wait until day 60; it just gets sharper. It is useful by around days 14 to 28." |
| "Privacy and stigma?" | "Ravi's neighbours see a bot called 'Health Diary'. It never says TB, and nothing shows on his lock screen. Every channel is off until he opts in, each consent is recorded per source and purpose, and /stop or Lakshmi withdraws it. Withdrawn data disappears on the nightly rebuild." |

---

## A.6 Backup slides for Q&A

| File | Pull it up when asked about |
|---|---|
| `whyfail.html` | Reminders failing, self-report reliability. **Check first:** it says "~23,500 patients in 4 trials", which is not on our verified list. Remove that number or verify it |
| `solution.html` | "How do the six parties connect?" |
| `demo.html` | The QR flow, if judges want to play the patient themselves |
| `close.html` | The closing line. Consider adding it to the deck order as slide 8 |

---

# PART B: Complete Feature Catalogue

**Priority key:** **P0** = must work in the demo · **P1** = stretch · **P2** = future roadmap (no hours given).
**Hours** = focused build hours with AI coding assistance. Integration plumbing is counted once, in section 8. Surface sections count only the flows on top of it.

## B.0a Reference stack (aligned with `CAREMEMORY_ARCHITECTURE.md`)

The full build architecture is in `CAREMEMORY_ARCHITECTURE.md` (v1). The blocks below use short names; this table maps them to that document's components. Where they differ, the architecture document wins.

| Short name used below | Component in `CAREMEMORY_ARCHITECTURE.md` | Technology |
|---|---|---|
| `api` | **`cm-api`** (public Cloud Run service; also serves the React build) | FastAPI, Pydantic v2, psycopg 3 |
| `worker` | **`cm-worker`** (private Cloud Run service, the Cloud Tasks target) | Same image |
| `jobs` | **`cm-nightly`**, **`cm-seed`**, **`cm-eval`** (Cloud Run Jobs), Cloud Scheduler timers, Cloud Tasks for every agent run, resume and send | Cloud Run Jobs, Cloud Scheduler, Cloud Tasks |
| `bot` | Telegram channel binding (`channel_bindings`, `/start <invite_code>`) + **Router / notifier** (§3.11) | python-telegram-bot |
| `gmail_bridge` | Gmail push via Pub/Sub, `gmail_state` | Gmail API |
| `cal_bridge` | Calendar channel | Google Calendar API |
| `store` | Cloud SQL Postgres 16: `events` (INSERT-only), projections, `PostgresSaver`, `PostgresStore`; SQLite/offline replay via `CM_OFFLINE=1` | Postgres, pgvector |
| `vec` | `PostgresStore` semantic index (`edit_examples`) and `guideline_chunks` | pgvector + `EMBEDDING_MODEL` (OpenAI only; falls back to `tsvector`) |
| Ingest agent | **Intake agent** (§3.2) | LangChain, `WORKER_MODEL` |
| Identity matcher | **Identity resolver** (§3.3) | rapidfuzz + `WORKER_MODEL` tie-break |
| `reconciler` | **Reconciler** (§3.4), rules only, runs before the orchestrator | Python |
| `memory_engine` | **Memory curator** (§3.5) + **Risk scorer** (§3.7) | numpy, scipy, scikit-learn |
| `investigator` | **Pattern investigator** (§3.6), a deep agent with sub-agents | deepagents |
| Narrator + `validator` | **Narrator with cite-or-cut validator** (§3.8); patient/Supporter text from the **Drafter** (§3.9) | `ORCHESTRATOR_MODEL` |
| `care_graph` / doctor gate | **Orchestrator deep agent** (§3.1) with `interrupt_on` for `submit_for_review`, `send_message`, `publish_card`; **Doctor-gate interrupt** (§3.10); `approvals` table; transactional `outbox` that refuses rows without a decision or approved template | deepagents `create_deep_agent`, LangGraph |
| Evaluation | **Evaluator** (§3.12), `eval_runs` | scikit-learn |
| District Q&A | **Dashboard query agent** (§3.13), read-only | `WORKER_MODEL` |
| `llm` | `cm/core/llm.py` model registry: LangChain **`init_chat_model`** with `ORCHESTRATOR_MODEL`, `WORKER_MODEL` (`openai:` or `deepseek:`), `VISION_MODEL` and `EMBEDDING_MODEL` (**OpenAI only**, because DeepSeek has no vision or embeddings), optional `FALLBACK_MODEL` | LangChain |
| `console`, `pwa` | React + Vite + Tailwind + Recharts, served by `cm-api` | React, Vite, Recharts |
| Ops | Secret Manager, LangSmith, `audit_log`, region `asia-south1`; LLM calls carry tokenised mock data only | GCP |

## B.0 Summary

| # | Surface | P0 features | P0 hours | P1 hours |
|---|---|---|---|---|
| 1 | Patient (Telegram / PWA) | 9 | 8.5 | 7 |
| 2 | Supporter app | 7 | 6 | 3 |
| 3 | Doctor console + review queue | 8 | 8 | 4 |
| 4 | Doctor/clinic dashboard | 14 | 15 | 4.5 |
| 5 | District TB officer dashboard | 5 | 4 | 6 |
| 6 | Admin, consent, settings | 4 | 4 | 3.5 |
| 7 | AI engine | 16 | 21.5 | 7 |
| 8 | Integrations | 5 | 5.5 | 5.5 |
| 9 | Evaluation and demo tools | 8 | 12 | 3.5 |
| 10 | Security, privacy, compliance | 6 | 3 | 4 |
| | **Total** | **82** | **≈ 88 h** | **≈ 48 h** |

About 88 P0 hours is roughly 4 builders × 22 hours. That is tight, so B.12 gives a cut order.

**Mapping to the brief's expected outputs**

| Brief output | Delivered by |
|---|---|
| Opt-in multi-channel check-ins + Supporter workflow | P-01 to P-09, S-01 to S-07, A-02 |
| Doctor review queue | D-01 to D-08 |
| Memory timeline with Day 3 vs Day 60 | C-05, C-11, C-12 |
| Contradiction and risk flags with cited evidence | E-10, E-12, C-06 |
| District dashboard | T-01 to T-04, T-10 |
| 60-day synthetic evaluation | V-01 to V-04 |

---

## B.1 Patient: Telegram bot / PWA

| ID | Feature | Description | Priority | Hours |
|---|---|---|---|---|
| P-01 | Opt-in onboarding | `/start` with an enrolment code; itemised consent per source and purpose; language choice | P0 | 2 |
| P-02 | Daily check-in | Asks at the patient's chosen time (Ravi: 07:50); buttons for Taken / Missed / Not sure; reply time logged | P0 | 1.5 |
| P-03 | One gentle nudge | A single follow-up if there is no reply after 2 h, then silence; silence itself becomes a signal | P0 | 0.5 |
| P-04 | Stigma-safe identity | Bot named "Health Diary"; never says "TB" or names medicines; nothing sensitive in notification previews | P0 | 0.5 |
| P-05 | Symptom checklist | A weekly 8-item checklist, plus an "I feel unwell" button any time | P0 | 1 |
| P-06 | Danger-symptom fast path | Certain answers create a Red review item at once; the patient gets an approved "contact your Supporter or doctor today" message | P0 | 0.5 |
| P-07 | Payment check | Monthly: "Did your ₹1,000 support arrive?" (yes / no / not sure) | P0 | 0.5 |
| P-08 | `/stop` and `/mydata` | Withdraw consent per channel; see a plain list of what is held | P0 | 1 |
| P-09 | Approved templates only | The bot only sends doctor-approved templates (green tier); free text goes to the queue | P0 | 1 |
| P-10 | Weight self-report | Monthly weight entry | P1 | 0.5 |
| P-11 | Reminders | Refill-due and appointment reminders (Calendar-linked) | P1 | 1 |
| P-12 | Telugu interface | Full Telugu text for every message and button | P1 | 1 |
| P-13 | PWA fallback | The same flows in a browser app with web push, for non-Telegram users | P1 | 2 |
| P-14 | "My progress" card | Days completed, phase (intensive or continuation), witnessed doses; doctor-approved | P1 | 1.5 |
| P-15 | Wearable opt-in | Pair the mock band; a plain explanation that it can only ask questions | P1 | 0.5 |
| P-16 | Milestone messages | End of intensive phase, halfway, completion | P1 | 0.5 |
| P-17 | Voice-note replies | Telugu speech-to-text replies | P2 | — |
| P-18 | Missed-call check-in | Give a missed call to confirm a dose (needs telephony) | P2 | — |

**How we implement it**

| ID | Approach | Libraries / services | Reads → writes | Main risk → fallback |
|---|---|---|---|---|
| P-01 | `/start <code>` deep link binds the Telegram ID to the patient. Language is chosen first, then one consent card per source and purpose, each with Yes/No buttons; everything defaults to No. | python-telegram-bot `ConversationHandler`, FastAPI, `store` | Enrolment code → `Patient.telegram_id`, `ConsentEvent` × n | Patient taps through without understanding → Lakshmi re-reads consent in person (S-07); any channel can be withdrawn later |
| P-02 | Scheduler sweeps every 5 min and enqueues a Cloud Task per patient due; the bot sends an inline keyboard. The callback records the sent and replied times. | python-telegram-bot, Cloud Scheduler, Cloud Tasks | Schedule, consent → `DoseCheckin(status, sent_at, replied_at)` | Telegram outage or rate limits → retries with backoff; the Supporter proxy check-in (S-06) covers the gap |
| P-03 | On send, a Cloud Task is scheduled 2 h later. If there is still no reply it sends one nudge; at day end it writes a no-reply event. | Cloud Tasks, `bot` | `DoseCheckin` → `NoReply` event | Feels like nagging → hard cap of 1 nudge a day, plus quiet hours |
| P-04 | Neutral bot name and avatar. Every template passes a banned-words check (TB, tuberculosis, drug names, Telugu equivalents) in CI and again at send time. | `validator`, pytest | Templates → send / block | A doctor edit adds a banned word → blocked at send, returned to the doctor to fix |
| P-05 | A weekly 8-question yes/no inline flow, plus an always-visible "I feel unwell" button. | python-telegram-bot, Cloud Scheduler | → `SymptomReport` | Survey fatigue → skippable; the Supporter can ask the same questions |
| P-06 | Rule 4 of the `reconciler` runs synchronously on each `SymptomReport`. A danger answer creates a Red `ReviewItem` plus a 4 h escalation task; the patient gets a pre-approved "contact your Supporter or doctor today" template. | `reconciler`, Cloud Tasks | `SymptomReport` → `ReviewItem(red)`, `Conflict` | False alarm → the doctor dismisses it; the bot never gives advice beyond "contact" |
| P-07 | A monthly scheduled question with yes / no / not sure. | Cloud Scheduler, `bot` | → `PaymentReport(received)`; later compared with the Ni-kshay mock | Patient unsure → the Supporter checks the passbook (S-05) |
| P-08 | Command handlers write withdrawal events. `/mydata` shows counts per source from `store`; the nightly rebuild drops withdrawn data. | python-telegram-bot, `store`, `jobs` | → `ConsentEvent(withdrawn)` | Accidental stop → a confirm step; the Supporter can re-enrol with fresh consent |
| P-09 | All outbound text goes through `send_template(template_id, vars)`. Patient free text goes to the ingest agent and then the amber queue. | `bot`, `templates` table, `care_graph` | Templates → messages; free text → `ReviewItem(amber)` | Patient asks a medical question → auto-reply "your Supporter or doctor will answer", item queued |
| P-10 | Monthly numeric prompt with a range check of 25–120 kg. | `bot`, pydantic | → `WeightReport(reporter=self)` | Typos → range check; the Supporter's monthly weight has higher trust |
| P-11 | Refill due date is computed from the actual dispensing date and pack size. If Calendar is opted in, an event is created; otherwise a bot reminder is scheduled. | `cal_bridge`, Cloud Tasks | Dispensing events → reminder | Wrong due date → derived from real dispensing; the Supporter can correct it |
| P-12 | String tables and templates stored per language. The `llm` drafts Telugu once, a native speaker checks it, and the doctor approves the template once. | JSON i18n files, `llm` (`init_chat_model`) | Templates (te/en) | Bad translation → human review of the fixed template set; English fallback |
| P-13 | The same React/Vite app as a PWA, calling the same API. Login by a one-time link from the Supporter; Web Push with VAPID. | React, Vite, vite-plugin-pwa, pywebpush | Same events as Telegram | Unreliable push on some phones → the Supporter channel |
| P-14 | A patient-safe template filled from the approved card: days done, phase and witnessed doses. Never shows the risk score. | `console` / `bot`, `templates` | Approved `MemoryCard` → message | Discouraging content → progress facts only, doctor-approved template |
| P-15 | `/band` toggles wearable consent and starts the mock feed for that patient. | `bot`, `sim` | → `ConsentEvent(wearable)` | Misunderstanding → explicit "it can only ask a question" text |
| P-16 | Scheduled by treatment day (end of intensive phase, halfway, completion). | Cloud Scheduler, `templates` | Regimen events → message | Regimen changed → milestones read from the latest doctor regimen event |
| P-17 | Telegram voice note → OpenAI speech-to-text → the same parser, with a confirmation echo. | OpenAI audio API, `llm` | Voice → `DoseCheckin` / note | Telugu accuracy → confirm echo before writing |
| P-18 | Telephony provider webhook on a missed call from the registered number. | NTEP telephony / IVR provider | Call log → `DoseCheckin(told)` | Spoofing or shared phones → low trust weight, bound to the registered number |

## B.2 Supporter app (Telegram Supporter mode / PWA)

| ID | Feature | Description | Priority | Hours |
|---|---|---|---|---|
| S-01 | Evening visit list | Pushed at 6 pm; ranked by risk; only doctor-approved visits | P0 | 1.5 |
| S-02 | Patient brief | Why to visit and what to check, with cited reasons, in plain words | P0 | 1 |
| S-03 | One-tap visit result | Witnessed / Told / Unreachable | P0 | 1 |
| S-04 | Pill count | Remaining tablets, weekly or on alert | P0 | 0.5 |
| S-05 | Weight and payment entry | Monthly weight; "₹1,000 received?" on the patient's behalf | P0 | 0.5 |
| S-06 | Proxy check-in | Daily or weekly check-ins for patients without phones (Supporter-only mode) | P0 | 1 |
| S-07 | Consent on behalf | Record consent or withdrawal with the patient present, with a read-back | P0 | 0.5 |
| S-08 | Free-text notes | "He's working nights at the mandi" → parsed into events, with a confirmation echo | P1 | 1.5 |
| S-09 | Escalate button | Sends the doctor an urgent item with the Supporter's note | P1 | 0.5 |
| S-10 | My week | Visits done vs planned, patients unreached | P1 | 0.5 |
| S-11 | Read the card aloud | A short script so the patient hears what the memory says about them | P1 | 0.5 |
| S-12 | Offline capture | Record visits with no signal, sync later | P2 | — |
| S-13 | Route order | Orders visits by distance, with map links | P2 | — |

**How we implement it**

| ID | Approach | Libraries / services | Reads → writes | Main risk → fallback |
|---|---|---|---|---|
| S-01 | At 17:30 a job ranks doctor-approved visit items (E-20) and sends the list at 18:00. | Cloud Scheduler, `bot`, `api` | `ReviewItem(approved, visit)`, `RiskScore` → `VisitPlan` | List too long → capped by the Supporter's capacity (default 6); overflow shown to the doctor |
| S-02 | Built from the approved card plus rule-specific "what to check" bullets. Citations are rendered as plain phrases ("no refill since day 28"). | `templates`, `validator` | `MemoryCard`, `Conflict` → brief | Jargon → reading-level check on templates; the doctor approved it |
| S-03 | Inline buttons; the outcome is stored with event time and arrival time. | python-telegram-bot | → `SupporterVisit(outcome, witnessed)` | Fake visits → per-reporter trust (E-06), pill-count cross-checks, doctor spot calls |
| S-04 | Numeric entry. The `reconciler` compares it with pills expected to remain from dispensing and taps. | `bot`, `reconciler` | → `PillCount`; feeds Rule 1 | Miscount → a re-count prompt when implausible; trust weighting |
| S-05 | The same flows as P-07 and P-10, with `reporter=supporter`. | `bot` | → `WeightReport`, `PaymentReport` | Conflicting reports → both kept; the trust score decides weight |
| S-06 | The Supporter picks the patient and answers the same check-in as witnessed or told. | `bot`, `store` | → `DoseCheckin(reporter=supporter, mode)` | Late batch entry → stored event time vs arrival time; late entries down-weighted |
| S-07 | Read-back consent text; the patient agrees aloud; the Supporter confirms; stored with the witness ID. | `bot`, `store` | → `ConsentEvent(witness=supporter_id)` | Coercion → the patient can `/stop` themselves; audit log and DTO spot checks |
| S-08 | Free text → `llm` structured output (a pydantic list of events) → echo "I recorded: works nights from day 50. Correct?" Written only on Yes. | LangChain `init_chat_model` + `with_structured_output` | Note → events (+ raw note kept) | Wrong parse → confirmation required; raw text always kept |
| S-09 | A button creates an urgent `ReviewItem` with the Supporter's note. | `bot`, `care_graph` | → `ReviewItem(amber/red)` | Over-use → the doctor sees escalation counts per Supporter |
| S-10 | A weekly query of the Supporter's visits. | `api`, `bot` | `SupporterVisit` → summary | None significant |
| S-11 | A fixed read-aloud template from the approved patient card. | `templates` | `MemoryCard` → script | Sensitive content → patient-safe template only |
| S-12 | PWA service worker queues events in IndexedDB and syncs later. | vite-plugin-pwa, IndexedDB | Local queue → events | Duplicates → idempotency keys |
| S-13 | Orders the list by distance using village coordinates. | OpenStreetMap / Leaflet | `VisitPlan` → ordered list | Bad coordinates → manual order |

## B.3 Doctor console + review queue

| ID | Feature | Description | Priority | Hours |
|---|---|---|---|---|
| D-01 | Tiered queue | Red / Amber / Green lanes with counts (e.g. 1 / 6 / 23) | P0 | 1.5 |
| D-02 | Evidence-first item | Drivers first, then cited events; clicking a citation opens the source record | P0 | 1 |
| D-03 | Approve / Edit / Reject | Inline editing; rejection needs a reason ("mandi job on Thursdays") | P0 | 1 |
| D-04 | Bulk approve | Approve the whole amber batch after scanning | P0 | 0.5 |
| D-05 | Red escalation | Red items are never auto-sent; they escalate to the STS after 4 h | P0 | 1 |
| D-06 | Gmail flow | Daily digest; approve by replying; a confirmation echo back (plumbing in I-02) | P0 | 1.5 |
| D-07 | Decisions as events | Each decision is stored as a `ReviewDecision` event with clinical authority | P0 | 0.5 |
| D-08 | Templates approved once | A library of green conversation templates, each approved once | P0 | 1 |
| D-09 | Green sampling | A daily summary, every anomaly and a 10% random sample of green items | P1 | 1 |
| D-10 | Edits teach style | Doctor edits become style examples for the narrator | P1 | 1 |
| D-11 | Review metrics | Acceptance rate, time to review, queue age | P1 | 0.5 |
| D-12 | Keyboard shortcuts | A / E / R and j / k for fast review | P1 | 0.5 |
| D-13 | Mobile review | A phone layout for the queue | P1 | 1 |
| D-14 | Nurse delegation | A clinic nurse prepares, the doctor signs | P2 | — |

**How we implement it**

| ID | Approach | Libraries / services | Reads → writes | Main risk → fallback |
|---|---|---|---|---|
| D-01 | `/review` page; `GET /review/queue` grouped by tier; polled every 30 s. | React, TanStack Query, FastAPI | `ReviewItem` | Overload → tier counts and batching |
| D-02 | Each item carries drivers and cited event IDs; a side drawer fetches `/events/{id}` and the source record. | React, FastAPI | `ReviewItem`, `events` | Too much detail → top 3 drivers, expandable |
| D-03 | `POST /review/{id}/decision` resumes the paused LangGraph thread with `Command(resume=...)`. | FastAPI, LangGraph | → `ReviewDecision` | Doctor edit adds an uncited claim → allowed (clinical authority) but tagged doctor-authored |
| D-04 | Batch endpoint over selected amber items. | FastAPI, React | → `ReviewDecision` × n | Rubber-stamping → items with a new belief must be opened first; acceptance metrics (D-11) |
| D-05 | Creating a Red item schedules a Cloud Task 4 h later; with no decision it alerts the STS by email and Telegram. Red is never auto-sent to the patient. | Cloud Tasks, `gmail_bridge`, `bot` | `ReviewItem(red)` → `Escalation` | Task lost → a nightly sweep finds overdue reds |
| D-06 | An 08:30 digest lists item numbers. Replies arrive by Pub/Sub watch (or a 1-minute poll). Keyword rules parse first ("approve 3, 4"); the `llm` parses only if they fail. A confirmation echo is sent back. | Gmail API, Pub/Sub, `llm` (`init_chat_model`) | Reply → `ReviewDecision(channel=gmail)` | Misparse → echo plus console override; only the whitelisted doctor address with DKIM pass is accepted |
| D-07 | The decision is written into `events` with `authority=clinical`; the next rebuild reads it. | `store`, `memory_engine` | → `events(review_decision)` | None; append-only |
| D-08 | `templates` table with versions and `approved_by`; green messages use only approved versions. | Postgres, `console` | `templates` | Stale template → pinned versions; any edit needs re-approval |
| D-09 | A nightly job samples 10% of green conversations (seeded random) plus every anomaly into a summary. | Cloud Scheduler, `gmail_bridge` | Green messages → `Summary` | The sample misses an issue → anomalies are always included |
| D-10 | Stores (draft, edited) pairs in `edit_examples`, mirrored into `PostgresStore` with `EMBEDDING_MODEL` (OpenAI) in pgvector, and retrieves the 3 nearest as few-shot style examples for the narrator. | pgvector, OpenAI embeddings, LangChain | `ReviewDecision` → `style_examples` | Style drift adds content → the validator still enforces citations |
| D-11 | SQL views over decisions, shown with Recharts. | Postgres views, Recharts | `ReviewDecision` → metrics | None significant |
| D-12 | Key bindings on the queue. | react-hotkeys-hook | — | Accidental approve → undo for 10 s |
| D-13 | A responsive layout for the queue. | Tailwind | — | Small-screen errors → confirm dialogs |
| D-14 | A nurse role can prepare decisions; only the doctor role can finalise. | RBAC in `api` | `ReviewItem` → draft decision | Role misuse → audit log |

## B.4 Doctor/clinic dashboard

What the doctor sees: a patient list with risk, timelines, flags, adherence charts, the memory card, approvals and search.

| ID | Feature | Description | Priority | Hours |
|---|---|---|---|---|
| C-01 | Patient list with risk | Name/ID, phase, treatment day, risk with interval, tier badge, last contact, channel icons; sortable | P0 | 2 |
| C-02 | Basic search | Find by name, Ni-kshay ID (mock) or phone | P0 | 0.5 |
| C-03 | Patient timeline | Every event in source lanes (patient, Supporter, chemist, lab, portal, doctor), colour-coded, with an `as_of` slider; click opens the record | P0 | 2 |
| C-04 | Flags panel | Contradictions and rule hits, with cited evidence and open/resolved status | P0 | 1 |
| C-05 | Adherence charts | 7/14/28-day and decayed rates; calendar dots split by reporter (self / witnessed) | P0 | 1.5 |
| C-06 | Weekday-miss heatmap | Makes "Thursdays" visible at a glance | P0 | 0.5 |
| C-07 | Refill coverage bar | Pills dispensed vs "Taken" taps; shows the day 28 → 44 gap | P0 | 0.5 |
| C-08 | Memory card | ≤120 words, citations, draft/approved status | P0 | 1 |
| C-09 | Memory Lens | Day 3 and Day 60 side by side, with a slider (the wow moment) | P0 | 2 |
| C-10 | Uncertainty funnel | The risk interval narrowing from day 1 to day 60 | P0 | 1 |
| C-11 | Beliefs list | Each belief with lifecycle (hypothesis / confirmed / dormant / retired) and evidence | P0 | 1 |
| C-12 | Unknowns admitted | "What I don't know yet" (7 on Day 3, 2 on Day 60) | P0 | 0.5 |
| C-13 | Approvals panel | Pending items for this patient, actionable in place | P0 | 0.5 |
| C-14 | Channel what-if toggles | Turn Telegram off to see the Supporter-only view live | P0 | 1 |
| C-15 | Filters | Tier, phase, channel mix, overdue refill, unpaid | P1 | 0.5 |
| C-16 | Fuzzy search | Misspellings and Telugu transliteration | P1 | 1 |
| C-17 | Weight and payment history | Weight trend (44.0 → 46.1 kg) and month-by-month payments | P1 | 0.5 |
| C-18 | Reply-time chart | Reply latency with the drift marker (9 → 85 min) | P1 | 0.5 |
| C-19 | Wearable trend | Grey "ask-only" chip and trend lines (mock) | P1 | 1 |
| C-20 | Referral summary | A printable handover or transfer summary | P2 | — |

*(C-15 to C-19 total 3.5 h; the B.0 figure of 4.5 h includes 1 h of chart polish.)*

**How we implement it**

| ID | Approach | Libraries / services | Reads → writes | Main risk → fallback |
|---|---|---|---|---|
| C-01 | `GET /patients?as_of=`; TanStack Table with a risk-interval mini bar and badges. | React, TanStack Table, FastAPI | `Patient`, `RiskScore`, `ReviewItem` | Risk misread as diagnosis → always labelled "ranks follow-up only" |
| C-02 | Postgres `ILIKE` on name, phone and ID. | FastAPI, Postgres | `Patient` | None significant |
| C-03 | `GET /patients/{id}/events?as_of=`; a Recharts scatter with one lane per source; the slider sets `as_of`; a click opens the raw record. | Recharts, React | `events` | Slow render → only ~300 events per patient; virtualise if needed |
| C-04 | `GET /patients/{id}/conflicts?as_of=` from the `reconciler`, with evidence chips. | FastAPI, React | `Conflict` | Stale flag → status updates when the conflict closes (e.g. refill on day 44) |
| C-05 | Charts the L1 features; a calendar grid colours dots by reporter. | Recharts `LineChart`, custom grid | `features`, `DoseCheckin` | Confusing two rates → tooltips explain each |
| C-06 | A 7-cell weekday grid of miss rates with credible intervals. | Recharts | `features`, `Belief(weekday)` | Over-reading noise → cells greyed until ≥4 instances |
| C-07 | Cumulative pills dispensed vs cumulative "Taken" taps. | Recharts `ComposedChart` | Dispensing, `DoseCheckin` | Late CSVs → 3-day grace shading |
| C-08 | `GET /patients/{id}/card?day=`; citations rendered as chips linked to events; status from the review item. | React, FastAPI | `MemoryCard`, `ReviewItem` | Unapproved card shown to the wrong role → only doctors see drafts |
| C-09 | Two memory snapshots (day 3 and the slider day). Snapshots for days 1–60 are precomputed nightly so dragging is instant. | React, FastAPI, `memory_engine` | `MemorySnapshot` (cached JSON) | Stage lag → snapshots cached in the browser on load |
| C-10 | The risk interval per day from the snapshots, drawn as an area band. | Recharts `Area` | `RiskScore` history | None significant |
| C-11 | A table of beliefs with status, first seen, confirmed date and evidence IDs. | React | `Belief` | Too many beliefs → retired ones collapsed |
| C-12 | `memory_engine` emits an unknowns list, e.g. "no weekday pattern yet: need ≥4 Thursdays". | `memory_engine` | → `MemorySnapshot.unknowns` | None significant |
| C-13 | The review queue filtered by patient, with the same decision actions. | React, FastAPI | `ReviewItem` | None significant |
| C-14 | `GET /memory?day=&channels=` recomputes the memory with only the chosen sources (an `as_of` plus source filter). | `memory_engine`, FastAPI | `events` (filtered) → snapshot | Too slow live → precompute two variants for the demo patient |
| C-15 | Query parameters on `/patients`. | FastAPI, React | `Patient` | None significant |
| C-16 | rapidfuzz on normalised names, plus pgvector name embeddings for transliteration. | rapidfuzz, pgvector, OpenAI embeddings | `Patient` | Wrong hit → results show ID and village |
| C-17 | Line chart of weight; month-by-month payment table. | Recharts | `WeightReport`, `PaymentReport`, portal mock | None significant |
| C-18 | Reply latency line with the CUSUM change point marked. | Recharts | `features`, `Belief(drift)` | None significant |
| C-19 | Mock wearable trends with a grey "ask-only" chip. | Recharts | `WearableRecord` | Being read as a diagnosis → grey, no alert styling |
| C-20 | Server-rendered PDF of the card, timeline and conflicts. | WeasyPrint | Snapshot → PDF | Data leaving the system → watermark and audit |

## B.5 District TB officer dashboard

What the DTO sees: KPIs, cascade drop-off, payments stuck, pharmacies, Supporter performance and a heatmap. It is de-identified by default.

| ID | Feature | Description | Priority | Hours |
|---|---|---|---|---|
| T-01 | KPI tiles | Active patients, high risk, open red flags, payments overdue, Supporter visits done/planned | P0 | 1 |
| T-02 | Block table | Per block: patients, high risk, payments overdue, visits done | P0 | 1 |
| T-03 | Payments stuck | Portal "paid" vs patient "not received", aged 30 / 60 / 90 days; exportable for follow-up | P0 | 1 |
| T-04 | Overdue red flags | Red items not reviewed within 4 h, by clinic | P0 | 0.5 |
| T-05 | De-identified by default | Names appear only for authorised roles with a stated reason, which is logged | P0 | 0.5 |
| T-06 | Care cascade drop-off | Diagnosed → notified → started → end of intensive → completed, showing where patients leak (pre-treatment loss matters: 14.6% in 2013 data) | P1 | 1.5 |
| T-07 | Pharmacy panel | Chemists reporting, CSV freshness and lateness, refill gaps by pharmacy | P1 | 1 |
| T-08 | Supporter performance | Visits done vs planned, unreachable rate, witnessed share; framed as support, not ranking | P1 | 1 |
| T-09 | Risk heatmap | High-risk density by block or village (synthetic geography) | P1 | 1.5 |
| T-10 | Weekly trends | Week-over-week changes for every KPI | P1 | 0.5 |
| T-11 | Clinic review health | Queue age and acceptance rate per clinic | P1 | 0.5 |
| T-12 | Weekly report export | PDF/CSV for district review meetings | P2 | — |
| T-13 | State roll-up | Multi-district view | P2 | — |

**How we implement it**

| ID | Approach | Libraries / services | Reads → writes | Main risk → fallback |
|---|---|---|---|---|
| T-01 | Nightly materialised views; `GET /district/kpis`; stat tiles with an "as of" time. | Postgres views, FastAPI, Recharts | All patients (aggregated) | Stale numbers → visible timestamp; refresh button |
| T-02 | `GROUP BY block` over the same views. | Postgres, React table | Aggregates | None significant |
| T-03 | Joins portal payment status (mock) with patient and Supporter reports; ageing buckets; CSV export. | Postgres, FastAPI | Portal mock, `PaymentReport` → `PaymentConflict` | Patient misreport → needs 2 "not received" reports or Supporter confirmation |
| T-04 | Query of red items open for more than 4 h, grouped by clinic. | Postgres | `ReviewItem`, `Escalation` | None significant |
| T-05 | The response serialiser drops names unless the role allows it and a reason is given; reasons are logged. Cells under 3 patients are suppressed. | FastAPI dependencies, `access_log` | Aggregates | Re-identification from small counts → small-cell suppression |
| T-06 | Counts per stage from status events, shown as a funnel. | Recharts `BarChart` | Status events | Synthetic data lacks pre-treatment stages → the generator adds them |
| T-07 | Per chemist: last CSV arrival, average lateness, refill gaps. | Postgres, Recharts | Chemist uploads, dispensing | Chemists stop sending → freshness alert to the DTO |
| T-08 | Per Supporter aggregates of visits, unreachable rate and witnessed share. | Postgres, Recharts | `SupporterVisit`, trust scores | Used to punish → framed as support; no public ranking |
| T-09 | A block-level risk grid in Recharts for the demo; a Leaflet map later. | Recharts (Leaflet later) | Aggregated `RiskScore` + synthetic geography | Location privacy → block level only |
| T-10 | Week-over-week deltas on the KPI views. | Postgres, Recharts | Views | None significant |
| T-11 | Queue age and acceptance rate per clinic. | Postgres | `ReviewItem`, `ReviewDecision` | Read as doctor ranking → shown to the DTO only |
| T-12 | A scheduled PDF/CSV report. | WeasyPrint, Cloud Scheduler | Views → file | None significant |
| T-13 | A state-level aggregate across districts. | Postgres / BigQuery | Views | Scale → move aggregates to BigQuery |

## B.6 Admin, consent, settings

| ID | Feature | Description | Priority | Hours |
|---|---|---|---|---|
| A-01 | Enrolment | Enrol a patient; assign a doctor and a Supporter; set the check-in time | P0 | 1 |
| A-02 | Consent ledger | Every `ConsentEvent` per source and purpose: given or withdrawn, by whom, when | P0 | 1 |
| A-03 | Roles and access | Patient, Supporter, doctor, DTO, admin, each with least privilege | P0 | 1.5 |
| A-04 | Withdrawal and erasure | Withdrawn data is dropped on the nightly rebuild, with a confirmation message | P0 | 0.5 |
| A-05 | Integration status | Bot, Gmail OAuth, Calendar and feeds, with last-seen times | P1 | 0.5 |
| A-06 | Template manager | Versioned templates with approval | P1 | 1 |
| A-07 | Escalation settings | Timer length and STS contact | P1 | 0.5 |
| A-08 | Audit log viewer | Who viewed or approved what | P1 | 1 |
| A-09 | Defaults | Language and check-in windows | P1 | 0.5 |
| A-10 | Retention settings | Decay and retention periods per data type | P2 | — |

**How we implement it**

| ID | Approach | Libraries / services | Reads → writes | Main risk → fallback |
|---|---|---|---|---|
| A-01 | A form generates a single-use enrolment code and QR for the patient and Supporter. | React, FastAPI, `qrcode` | → `Patient`, `Assignment`, code | Wrong assignment → editable, audited |
| A-02 | A read-only view over the append-only consent table. | React, FastAPI | `ConsentEvent` | None; append-only |
| A-03 | Demo: seeded mock users with signed JWTs per role (doctor, supporter, sts, dto, admin, chemist, lab); production uses Identity Platform. The JWT carries the role; FastAPI dependencies check the role on every route; queries are filtered by clinic. | PyJWT, FastAPI (Identity Platform later) | `persons.role` | Misconfiguration → deny-by-default plus per-role tests |
| A-04 | The nightly rebuild ignores events whose consent is withdrawn and recomputes all derived tables. Raw withdrawn events are tombstoned and purged. | `jobs`, `memory_engine`, `store` | `ConsentEvent` → purge | Backups keep data → short, documented backup retention |
| A-05 | Health checks for each channel with a last-seen time. | FastAPI, React | Channel heartbeats | None significant |
| A-06 | CRUD over versioned templates, with an approval step. | React, FastAPI | `templates` | Unapproved template used → send path checks the approved flag |
| A-07 | Settings table read by the escalation task. | FastAPI | `settings` | Missing STS contact → falls back to the DTO |
| A-08 | A filtered view of the access log. | React, FastAPI | `access_log` | None significant |
| A-09 | Defaults applied at enrolment. | FastAPI | `settings` | None significant |
| A-10 | Per-type retention periods applied by the nightly purge. | `jobs` | `settings` → purge | Over-deletion → dry-run report first |

## B.7 AI engine (deep agents, memory, rules, evaluation)

Principle: **statistics decide; the LLM only parses and narrates; the doctor approves.** Memory is `f(events, as_of)`: recomputed, never edited.

| ID | Feature | Description | Priority | Hours |
|---|---|---|---|---|
| E-01 | Event store | Append-only Postgres table (SQLite in offline mode); event time and arrival time, source, consent; `store.query(pid, as_of)` blocks future leakage | P0 | 2.5 |
| E-02 | Ingest agent | Telegram, Gmail and CSV → typed events (LangChain structured output) | P0 | 2 |
| E-03 | Consent gate | Events without valid consent are dropped at ingest | P0 | 0.5 |
| E-04 | Feature layer (L1) | Nightly: 7/14/28-day and decayed adherence, weekday misses, refill coverage, reply time, weight | P0 | 1.5 |
| E-05 | Weekday detector | Pooled Bayesian; needs ≥4 instances and ≥90% confidence | P0 | 1.5 |
| E-06 | Per-reporter trust | Separate trust scores for self, Supporter and family reports | P0 | 1 |
| E-07 | Drift alarm | CUSUM change detection on reply time | P0 | 1 |
| E-08 | Calibrated risk | Logistic dropout proxy with an interval, trained on seeds separate from evaluation | P0 | 1.5 |
| E-09 | Belief lifecycle | Hypothesis → confirmed → dormant (21 d) → retired (42 d) | P0 | 0.5 |
| E-10 | Reconciler: 5 rules | Refill vs self-report, drug-resistance result vs regimen, payment mismatch, danger symptom, silence streak; fire from day 1 | P0 | 2.5 |
| E-11 | Narrator (LLM) | Writes the ≤120-word card from L2 beliefs only, citing event IDs | P0 | 1.5 |
| E-12 | Cite-or-cut validator | Strips uncited sentences and wrong numbers; falls back to a template | P0 | 1.5 |
| E-13 | LangGraph orchestration | One graph (ingest → reconcile → memory → narrate → doctor gate); it pauses until approval | P0 | 2 |
| E-14 | Feedback loop | Rejections retire beliefs with a reason; approvals and edits become evidence | P0 | 1 |
| E-15 | Inbound text guard | Prompt-injection filter; the LLM never acts on message content | P0 | 0.5 |
| E-16 | Model fallback | If the API is down, templates are used and the queue keeps working | P0 | 0.5 |
| E-17 | Deep Agents investigator | Plans multi-step checks: refill gap → check payment → check Supporter log → draft a visit brief | P1 | 2.5 |
| E-18 | Identity matcher | Fuzzy match on name, phone and ID (handles the ~5% misspellings) | P1 | 2 |
| E-19 | Wearable deviation | Drift from the person's own baseline only adds a "fever or night sweats?" question | P1 | 1 |
| E-20 | Visit-list optimiser | Ranks visits by risk × reachability within Supporter capacity | P1 | 1 |
| E-21 | LangSmith tracing | Every agent step traced for debugging and audit | P1 | 0.5 |
| E-22 | Learned check-in time | Moves the check-in to the patient's real response window | P2 | — |

**How we implement it**

| ID | Approach | Libraries / services | Reads → writes | Main risk → fallback |
|---|---|---|---|---|
| E-01 | Postgres `events` (id, patient_id, type, payload JSONB, event_time, arrival_time, source, reporter_id, consent_id). The app role has INSERT and SELECT only. `query(pid, as_of)` filters on both timestamps. The same schema runs on SQLite offline. | Cloud SQL Postgres, SQLAlchemy 2, Alembic | All sources → `events` | Accidental edit → no UPDATE or DELETE grants; a trigger blocks changes |
| E-02 | A LangGraph node. Buttons and CSVs use deterministic parsers; the `llm` with `with_structured_output` handles free text only. | LangGraph, LangChain `init_chat_model`, pydantic | Messages, CSVs → typed events | Parse error → raw-text event plus an amber item |
| E-03 | Looks up an active `ConsentEvent` for (patient, source, purpose) before writing. | `api` middleware | `ConsentEvent` → accept / drop | Consent race → events are re-checked at nightly rebuild |
| E-04 | pandas over `query(pid, as_of)`; a Cloud Run job at 02:00. | pandas, numpy, Cloud Scheduler | `events` → `features` | Job fails → yesterday's features kept and marked stale |
| E-05 | A Beta-binomial miss rate per weekday, partially pooled across patients (empirical-Bayes prior). Confirmed when P(weekday rate − other rate > 0.20) ≥ 0.90 with ≥4 instances. | numpy, scipy | `features` → `Belief(weekday)` | False patterns → thresholds, no-pattern patients in evaluation, retirement lifecycle |
| E-06 | A Beta trust score per reporter, from how often their "Taken" agrees with independent signals (refill coverage, witnessed visits, pill counts). | numpy, scipy | Check-ins, dispensing, visits → `Trust` | Little independent evidence → wide interval around a 0.8 prior |
| E-07 | CUSUM on log reply latency against the patient's first-14-day baseline; threshold tuned on training seeds. | numpy | `features` → `Belief(drift)` | Phone change or travel → only adds to the card; the Supporter checks |
| E-08 | Logistic regression on L1 features, trained on separate seeds, calibrated (isotonic). An interval comes from a 50-model bootstrap; drivers are coefficient × feature. | scikit-learn | `features` → `RiskScore(p, lo, hi, drivers)` | Miscalibrated on real data → it only ranks visits; recalibrate in the pilot |
| E-09 | A state machine keyed on the date of the last supporting evidence. | `memory_engine` | `Belief` → status | Flapping → hysteresis on thresholds |
| E-10 | Five pure functions, each returning a `Conflict` with evidence IDs: refill coverage vs "Taken" days; lab drug-resistance result vs regimen; portal paid vs not received; danger symptom; N consecutive non-replies. | Python, pytest fixtures | `events` → `Conflict` | Late chemist CSVs cause false positives → 3-day grace |
| E-11 | `init_chat_model(ORCHESTRATOR_MODEL)` (e.g. `openai:<model>` or `deepseek:deepseek-chat`), temperature 0. The prompt holds only L2 beliefs as JSON with IDs; the output is pydantic `{sentences: [{text, cites}]}`, ≤120 words. | LangChain, OpenAI / DeepSeek | `Belief`, `RiskScore`, `Conflict` → draft `MemoryCard` | Provider outage → `with_fallbacks` to the other provider, then a template card |
| E-12 | Each sentence must cite IDs that exist, belong to the patient and are within `as_of`. Numbers in the text must match the cited beliefs. Failing sentences are dropped; under 2 left → template. | Python, regex, pydantic | Draft card → validated card | Over-stripping → the template is always readable |
| E-13 | The **Orchestrator deep agent** (`create_deep_agent`) plans with `write_todos` and delegates to sub-agents; `interrupt_on` pauses at `submit_for_review`, `send_message` and `publish_card`. `PostgresSaver` keeps paused threads across restarts; the `outbox` constraint refuses any send without a decision or approved template. | deepagents, LangGraph, PostgresSaver | Thread state ↔ `approvals` | Stuck threads → nightly sweep and timeouts |
| E-14 | The next rebuild reads decision events: a rejection retires the belief and keeps the reason; an approval adds supporting evidence. | `memory_engine` | `ReviewDecision` → `Belief` | Wrong rejection → the belief can re-emerge with new evidence |
| E-15 | Inbound text is only ever data in a user message, never instructions; the `llm` returns structured data and has no tools when reading inbound content. | LangChain, regex checks | Inbound text → sanitised | A novel injection → nothing can reach a patient without the doctor gate |
| E-16 | 10 s timeout, provider fallback, then templates; the queue keeps working. | LangChain `with_retry`, `with_fallbacks` | — | Both providers down → template cards and offline mode |
| E-17 | `create_deep_agent` with `init_chat_model(...)` and read-only tools (`query_events`, `get_refills`, `get_payments`, `get_supporter_log`) plus `draft_review_item`. It plans with its todo list and returns only a draft. | deepagents, LangChain, LangGraph | `events` → draft `ReviewItem` | Loops or cost → max 8 steps, read-only tools; P1, so the demo works without it |
| E-18 | rapidfuzz on normalised name + phone + ID; optional OpenAI embeddings for transliterated names. Below a 0.9 score it goes to admin review. | rapidfuzz, pgvector, OpenAI embeddings | Incoming records → `patient_id` | Wrong merge → never auto-merge below threshold |
| E-19 | Rolling median ± k·MAD against the person's own baseline after 5 nights; a deviation only adds a question to the next check-in. | numpy | `WearableRecord` → `WearableDeviation` | Read as a diagnosis → never alerts or scores |
| E-20 | Greedy ranking by risk × chance of being reachable, within Supporter capacity, with a visit at least every 14 days for everyone. | Python | `RiskScore`, `SupporterVisit` → `VisitPlan` | Low-risk patients ignored → the 14-day floor |
| E-21 | LangSmith tracing via env vars, with PII redaction before export. | LangSmith | Traces | PII in traces → pseudonymised inputs (X-01) |
| E-22 | Shifts the check-in time towards the patient's median reply window. | `memory_engine` | `features` → schedule | Too many moves → at most one change a week |

## B.8 Integrations

| ID | Integration | Description | Priority | Hours |
|---|---|---|---|---|
| I-01 | Telegram Bot API | Webhook with polling fallback; patient and Supporter roles; account binding | P0 | 1.5 |
| I-02 | Gmail API (OAuth) | Sends the digest, reads replies, takes chemist CSV attachments | P0 | 1.5 |
| I-03 | Chemist CSV | Daily dispensing file; tolerates 1–3 days of lateness; deduplicates | P0 | 1 |
| I-04 | Ni-kshay mock | Notification ID and monthly payment status (no scraping; MoU later) | P0 | 1 |
| I-05 | LLM provider wrapper | OpenAI and/or DeepSeek through LangChain `init_chat_model`; retries, timeouts, cost cap; keys on the server only | P0 | 0.5 |
| I-06 | Google Calendar | Visit and refill events; attendance | P1 | 1.5 |
| I-07 | Wearable mock | Health Connect/Oura-shaped records for 3 of 40 patients: resting HR, skin temperature, sleep, steps, weight (no SpO2 or HRV) | P1 | 2 |
| I-08 | Lab PDF reader | OpenAI vision extracts the result into an event; the doctor confirms | P1 | 2 |
| I-09 | 99DOTS / MERM import | Ingest existing adherence-tech events | P2 | — |
| I-10 | SMS / IVR gateway | Through NTEP channels | P2 | — |
| I-11 | ABDM / FHIR | Standard health-record exchange | P2 | — |

**How we implement it**

| ID | Approach | Libraries / services | Reads → writes | Main risk → fallback |
|---|---|---|---|---|
| I-01 | A python-telegram-bot `Application` in webhook mode behind a FastAPI route, checking Telegram's secret-token header; polling for local runs. One bot; the role comes from the account binding. | python-telegram-bot, FastAPI, Cloud Run | Updates → `bot` handlers | Webhook down → switch to polling; Telegram retries delivery |
| I-02 | OAuth pre-authorised; refresh token in Secret Manager. `users.watch` → Pub/Sub push; a Scheduler poll every minute as fallback. CSV attachments go to I-03. | Gmail API, Pub/Sub, Secret Manager | Mail ↔ `ReviewDecision`, CSV files | Token expiry on stage → re-authorise the morning of the demo; offline sim (V-06) |
| I-03 | pandas `read_csv` with a pydantic row schema; dedupe on (chemist, bill number); identity match (E-18). | pandas, pydantic | CSV → `Dispensing` events | Bad format → reply email listing the row errors |
| I-04 | A FastAPI router at `/mock/nikshay` serving seeded data in the shape we expect from the real API, behind an adapter interface. | FastAPI, `sim` | Mock → `PortalPayment`, `Notification` | Real API differs → only the adapter changes |
| I-05 | `cm/core/llm.py`: one `get_model(role)` around `init_chat_model`, with `ORCHESTRATOR_MODEL` / `WORKER_MODEL` from env, `with_retry`, `with_fallbacks` (OpenAI ↔ DeepSeek) and a token budget. Vision and embeddings always use OpenAI. | LangChain, OpenAI, DeepSeek, Secret Manager | Prompts → structured outputs | Cost spike → per-day token cap; templates take over |
| I-06 | `events.insert` into the opted-in calendar; attendance from the event response. | Google Calendar API | Visits, refills → calendar events | Low calendar use → Telegram reminders |
| I-07 | The generator writes Health Connect-shaped JSON records to `POST /ingest/wearable`. | `sim`, FastAPI | → `WearableRecord` | Not real data → said openly in the demo |
| I-08 | PDF → images (pypdfium2) → an OpenAI vision model through `init_chat_model(model_provider="openai")` with structured output (test, result, resistance, date). The extraction is shown beside the PDF snippet for doctor confirmation. | pypdfium2, LangChain, OpenAI vision | PDF → `LabResult` (draft → confirmed) | Misread → doctor confirmation; Rule 2 only raises a red item, never acts |
| I-09 | An adapter mapping 99DOTS/MERM exports to our events. | Python adapter | Exports → events | Format changes → versioned adapters |
| I-10 | An SMS/IVR provider webhook. | NTEP telephony / IVR | Calls, SMS → events | Cost → NTEP channels |
| I-11 | FHIR resources (Patient, Observation, MedicationDispense) mapped from events. | fhir.resources | Events ↔ FHIR | Consent scope → ABDM consent manager |

## B.9 Evaluation and demo tools

| ID | Tool | Description | Priority | Hours |
|---|---|---|---|---|
| V-01 | Synthetic generator | Deterministic numpy, seeded; hidden `truth.json`; realistic noise (10% unanswered, late CSVs, misspellings, 20% no-pattern patients, generated opt-ins) | P0 | 4 |
| V-02 | Evaluation report | Brier score and AUROC at days 3/7/14/28/42/60 on 200 patients, against two baselines (population average, "same as last week") | P0 | 2 |
| V-03 | Facts-learned scoreboard | Caught / false and retired / missed / days to detect | P0 | 1 |
| V-04 | Judge seed re-roll | A judge picks a seed; everything regenerates and re-scores in about 20 s | P0 | 1 |
| V-05 | Replay | `POST /sim/advance?to_day=`, with `as_of` honoured everywhere | P0 | 1 |
| V-06 | Offline harness | Simulated Telegram and Gmail; the demo runs with no internet | P0 | 1 |
| V-07 | Precomputed fallback | Evaluation stored for 3 seeds, plus a backup video | P0 | 1.5 |
| V-08 | Demo reset | One button back to a clean state | P0 | 0.5 |
| V-09 | Judge QR onboarding | Scan to play the patient | P1 | 1 |
| V-10 | Scenario injector | Inject a red flag or a payment failure live | P1 | 1 |
| V-11 | Ablation view | AUROC with memory on/off and with channels removed | P1 | 1.5 |

**How we implement it**

| ID | Approach | Libraries / services | Reads → writes | Main risk → fallback |
|---|---|---|---|---|
| V-01 | `numpy.random.Generator(seed)`; latent traits per patient; daily simulation; pills dispensed derive from pills actually taken. The `llm` writes only free-text notes, cached per seed. | numpy, `sim` | Seed → `events.jsonl`, `truth.json` | Too clean → noise settings and 20% no-pattern patients |
| V-02 | Risk trained on seeds 1–50 and scored on the judge's seed at each day via `as_of`, against two baselines. | scikit-learn (`brier_score_loss`, `roc_auc_score`) | Events, truth → `EvalReport` | Weak numbers → shown honestly; it proves the method only |
| V-03 | Compares beliefs with the true traits: precision, recall, days to detect. | pandas | `Belief`, `truth.json` → scoreboard | Truth leakage → only the evaluator reads `truth.json` |
| V-04 | `POST /eval?seed=` runs a vectorised job (200 patients × 60 days) with progress over server-sent events; target about 20 s. | FastAPI, numpy, multiprocessing / Cloud Run job | Seed → `EvalReport` | Over 20 s on stage → precomputed seeds (V-07) or 100 patients |
| V-05 | A clock service; every endpoint takes `as_of`; `POST /sim/advance?to_day=`. | FastAPI, `store` | Clock → all reads | Future leakage → `as_of` filter tests |
| V-06 | `CHANNEL_MODE=sim` swaps in fake Telegram and Gmail adapters that write to the same ingest path; the console shows a phone mock. Runs on SQLite with no internet. | FastAPI, SQLite, React | Same events | Divergence from real channels → shared adapter interface tests |
| V-07 | Results for 3 seeds stored as JSON; a backup video recorded by hour 30. | JSON, OBS | `EvalReport` files | Live failure → switch tab |
| V-08 | Truncate and reseed with a confirm dialog. | FastAPI | DB → clean seed | Accidental reset mid-pitch → confirm plus admin role only |
| V-09 | QR → `t.me/<bot>?start=judge_x` binds each judge to their own copy of a demo patient. | python-telegram-bot, `qrcode` | → demo binding | Many judges at once → one copy per judge |
| V-10 | An admin endpoint inserts crafted events (a red symptom, a payment failure). | FastAPI | → events | Pollutes evaluation → tagged and excluded |
| V-11 | Re-runs the evaluation with memory or channels removed. | scikit-learn, `sim` | → ablation report | Slow → precomputed |

## B.10 Security, privacy, compliance

| ID | Control | Description | Priority | Hours |
|---|---|---|---|---|
| X-01 | Pseudonymise before the LLM | Names and phones are replaced with IDs in every prompt | P0 | 1 |
| X-02 | Secrets on the server | Keys only in the server `.env`, never in the client | P0 | 0.25 |
| X-03 | Coordination-only guard | No diagnosis or dosing advice in any output; risk is labelled "ranks follow-up only" | P0 | 0.5 |
| X-04 | Audit trail | Append-only record of who viewed or approved what | P0 | 0.5 |
| X-05 | Account binding | Telegram users bind with a clinic or Supporter code; no strangers | P0 | 0.5 |
| X-06 | No minors | The prototype excludes under-18s | P0 | 0.25 |
| X-07 | Consent off by default | Covered by E-03 and A-02 | P0 | (in E-03) |
| X-08 | Purpose limits and decay | Covered by E-09 and A-04 | P0 | (in E-09) |
| X-09 | DPDP notice and breach plan | Itemised notice; breach-response plan (DPDP Rules 2025 guide the design) | P1 | 1 |
| X-10 | CDSCO position note | Why this is coordination software, and the Class A/B route if claims grow | P1 | 0.5 |
| X-11 | Encryption | Encryption at rest (SQLCipher) and HTTPS everywhere | P1 | 1 |
| X-12 | Rate limits | Abuse protection on the bot and webhooks | P1 | 0.5 |
| X-13 | Red-team set | Test cases for hallucination and prompt injection | P1 | 1 |
| X-14 | Data localisation | Hosting in an India region | P2 | — |

**How we implement it**

| ID | Approach | Libraries / services | Reads → writes | Main risk → fallback |
|---|---|---|---|---|
| X-01 | Before every `llm` call, names and phones are replaced with tokens (e.g. P-0042), mapped back only in the UI. | Python regex + patient-name list (Presidio optional) | Prompts | Names inside free text → name-list matching; nothing leaves without tokens |
| X-02 | Secret Manager → env on Cloud Run; `.env` locally (git-ignored); detect-secrets pre-commit hook. | Secret Manager, detect-secrets | Keys | Key leak → rotate; keys never reach the browser |
| X-03 | The validator blocks diagnosis words and dose amounts in any output; the UI labels risk "ranks follow-up only". | `validator` | Outputs | New phrasing slips through → red-team set (X-13) |
| X-04 | FastAPI middleware writes actor, resource and action to an INSERT-only table. | FastAPI, Postgres | → `access_log` | Log tampering → no UPDATE or DELETE grants |
| X-05 | Single-use codes that expire in 48 h, tied to a phone number. | `api`, `bot` | Codes → binding | Code shared → rebind needs the Supporter |
| X-06 | Age check at enrolment (≥18). | `api` | `Patient` | Wrong age entered → Supporter verification |
| X-07 | See E-03 and A-02. | — | — | — |
| X-08 | See E-09 and A-04. | — | — | — |
| X-09 | Written notice per source and purpose; breach plan with contacts and timelines. | Docs | — | Out of date → reviewed with each new channel |
| X-10 | A short note: coordination only, no diagnosis, risk ranks follow-up. | Docs | — | Scope creep → claims review before release |
| X-11 | Cloud SQL encryption at rest (CMEK optional); HTTPS by default on Cloud Run; SQLCipher for offline SQLite. | Cloud SQL, Cloud Run, SQLCipher | — | Laptop loss → encrypted offline database |
| X-12 | Per-IP and per-user limits; Telegram secret-token check. | slowapi | — | Abuse → block and alert |
| X-13 | A pytest suite of adversarial notes and cards, run in CI. | pytest, LangSmith datasets | — | Gaps → add every real failure as a test |
| X-14 | Deploy in `asia-south1`; production terms under NTEP's legal basis. | Cloud Run, Cloud SQL regions | — | Third-party LLM calls leave India → pseudonymised prompts; regional providers later |

---

## B.11 Future roadmap

| Feature | Why | Depends on |
|---|---|---|
| **IVR and missed-call check-ins** | Reaches patients without smartphones or literacy | NTEP telephony |
| **Telugu voice bot** | Speak-and-listen check-ins; lower literacy barrier | Speech models, testing in the field |
| **Native Android app with Health Connect** | Real wearable and phone data (a PWA can't read Health Connect) | Play Store, a privacy review |
| **Ni-kshay integration + ABHA/ABDM linkage** | Real notifications and payment status; one health ID | MoU with NTEP |
| **99DOTS / MERM ingestion** | Adds existing adherence data instead of competing with it | Data agreement |
| **SMS and WhatsApp** | Wider reach (WhatsApp's API is paid) | NTEP channels, budget |
| **Drug-resistant TB pathway** | Longer regimens and more side-effect monitoring | Clinical protocol work |
| **Side-effect (ADR) tracker** | Side effects are a common reason to stop; flag them early to the doctor | Clinical checklist |
| **Household contact screening and preventive therapy tracker** | Protects families like Meena's | NTEP guidelines |
| **Payment ticketing** | Turns "paid but not received" into a tracked ticket with the district | District accounts team |
| **Ni-kshay Mitra nutrition matching** | Connects donors to patients whose support is stuck | Mitra programme |
| **Transfer and migration handover** | Daily-wage workers move; the memory moves with them | Inter-district process |
| **Post-treatment follow-up** | Relapse checks after completion | Protocol |
| **Comorbidity flags** | Diabetes, HIV, alcohol and tobacco change risk | Screening data |
| **Mental-health screen** | A short mood screen routed to a counsellor | Counsellor network |
| **Other diseases** | HIV ART, diabetes, hypertension, leprosy, hepatitis C, post-partum follow-up: any long treatment where pieces are scattered | Disease rule packs |
| **Cough monitoring via the phone mic** | Research only; no clinical claims | Validation studies |
| **Pilot evaluation design** | Stepped-wedge cluster pilot measuring loss to follow-up | Ethics approval, district partner |

---

## B.12 If we fall behind: P0 cut order

Cut from the top. Never cut the Memory Lens, the review queue, the Gmail loop or the evaluation re-roll.

1. C-14 channel toggles → explain it verbally with the `trust.html` slide.
2. T-04 overdue red flags → show it on the queue instead.
3. C-12 unknowns list → keep the number on the card.
4. D-08 template library → hard-code three templates.
5. E-16 model fallback → rely on V-06 offline replay.
6. S-07 consent on behalf → patient consent only.

---

## B.13 What we might be missing

| # | Area | Gap | What to do |
|---|---|---|---|
| 1 | Product | **What's in it for Ravi?** Daily replies need a reward. Today the value mostly goes to the doctor | Make payment tracking ("your ₹1,000 is stuck; we've told the district") and the progress card patient-facing |
| 2 | Product | **Shared phones.** Sunitha may answer on Ravi's phone, so who is the reporter? | Treat "who replied" as unknown; per-reporter trust already helps; ask "Is this Ravi?" now and then |
| 3 | Product | **Phone-number churn and migration.** Daily-wage workers change SIMs and move | Bind identity through the Supporter; add transfer handover (roadmap) |
| 4 | Product | **Women and low-literacy patients** have less phone access | Supporter-first design; IVR and voice on the roadmap; test with women patients |
| 5 | Clinical | **Side effects** are a common reason people stop, but our checklist is symptom-focused | Add side-effect items to the weekly checklist, routed to the doctor |
| 6 | Clinical | **Comorbidities** (diabetes, HIV, alcohol use) and depression change risk | At least capture them at enrolment as fields; flag for the doctor |
| 7 | Clinical | **Household contacts.** Our ending promises Meena is safe, but no feature tracks contact screening | Add a contact-screening reminder (P2), or soften the ending line |
| 8 | Clinical | **Clinical validation of the risk proxy.** "7+ misses in 14 days" is not NTEP's lost-to-follow-up definition | Say so openly; the pilot validates against real outcomes |
| 9 | Operational | **Supporter workload and pay.** Lakshmi already has many duties | Cap the list size; show time per visit; align with NTEP supporter payments |
| 10 | Operational | **Chemist participation.** Will chemists send a daily CSV? | Make it a one-tap upload; tie it to the mandatory TB notification duty; pilot with 3 chemists |
| 11 | Operational | **Liability when a flag is ignored.** Who is responsible if a red item expires? | The escalation chain and audit log; write the policy in pilot terms |
| 12 | Operational | **Private GP onboarding.** Why would Dr. Prasad join? | Pitch it as saving time and meeting the notification duty; PPSA agencies as channel partners |
| 13 | Operational | **Cost per patient** is not stated anywhere | Estimate hosting, LLM and messaging cost per patient-month before the pitch |
| 14 | Pitch | **Placeholders on slides.** `[X/Y]`, `[n]`, `[Z]` and `[d]` on `impact.html` and `demo.html` must be filled from the real evaluation run | Fill them, or say "target" out loud |
| 15 | Pitch | **Unverified numbers on slides.** `whyfail.html` says "~23,500 patients in 4 trials"; `problem.html` says "4 cluster-randomised trials". Neither is on the verified list | Verify against the Lancet paper or remove; say "Lancet 2025 trials" |
| 16 | Pitch | **Saathi vs Supporter.** The brief says Saathi; the deck says Supporter | Say once: "the Supporter, the brief's Saathi" |
| 17 | Pitch | **Competitor framing.** Judges may name 99DOTS, MERM or Ni-kshay tools | One line: "We sit on top of them. We reconcile, remember and target visits." |
| 18 | Pitch | **Story consistency.** The cover shows 50 days taken then 40 unseen; the spoken story must match it exactly | Use the A.1 timeline everywhere; rehearse with the slide |
| 19 | Pitch | **Demo single points of failure.** Venue Wi-Fi, OAuth expiry, Telegram rate limits | Hotspot, pre-authorised OAuth, offline replay tab, spare phone, backup video |
| 20 | Pitch | **The architecture slide is out of date.** `architecture.html` still lists the Claude API, Gemini API and SQLite. The build now uses OpenAI and/or DeepSeek through `init_chat_model` (OpenAI for vision and embeddings) on Cloud SQL Postgres | Update slide 6 to match `CAREMEMORY_ARCHITECTURE.md` before rehearsal |

---

## ADDENDUM (23 Oct): household contact screening, and why we built this

### New feature: household contact screening (P0, about 3 h)
This feature makes the story's ending ("his family is protected") true.
- **What it does:**
  - When a patient is notified, the Supporter records the household members: name, age, and whether they have symptoms. They tap through a 4-symptom checklist (cough over 2 weeks, fever, weight loss, night sweats).
  - CareMemory creates a "screen family" task, puts a calendar visit on the Supporter's calendar for week 1, and sends a doctor-approved invitation for family testing.
  - Children under 5 and anyone with symptoms are flagged for the doctor to review. The doctor decides on preventive treatment (TPT); the system never does.
  - It tracks contacts listed, contacts screened, and contacts referred.
- **How we implement it:**
  - **Tables:** a `household_contacts` table (patient_id, relation, age_band, symptoms, screened_at, referred). Every write is also stored as an event.
  - **Rule:** a reconciler rule, "contacts not screened by day 14", raises an amber review item.
  - **Calendar:** a Calendar event is created through the outbox, with doctor approval.
  - **Dashboards:** the district dashboard gets a new KPI, "Contacts screened %".
- **Story ending, revised:** "Lakshmi screened Ravi’s family in the first week. Meena and their son were tested. Six months later, Ravi finished his course, and Meena finally slept through the night."

### Why we built this: the one line to stick on
> **“TB is curable. People still die of it because their care forgets them. We built CareMemory so that no patient’s story is ever forgotten.”**

Why this problem, and why it's worth choosing:
1. **It is the biggest infectious killer in India, and it is curable.** India has about 25% of the world's TB cases and about 28% of its deaths. The cure already exists. What is missing is follow-through, and follow-through is a software problem.
2. **The gap is coordination, not medicine.** Six people each hold one piece of a patient's story, and nobody joins them up. Reminders alone did not significantly help in the Lancet 2025 trials, and self-reports mislead (only 21% of the patients flagged really missed doses). The missing layer is memory and reconciliation.
3. **It is a national mission.** TB Mukt Bharat is a national campaign with a buyer and a budget: NTEP, district TB cells, and the private-sector partnership agencies (PPSA).
4. **AI is genuinely needed here.** The system has to reason across messy, contradictory sources over 6 months and learn each person's pattern. A rule-based form app cannot do that.
5. **It is safe by design.** A doctor approves everything, and the AI never diagnoses. We picked a problem where AI helps humans act sooner, not one where it replaces them.
6. **It scales beyond TB.** The same memory loop fits any long treatment: diabetes, HIV, hypertension, and maternal care.
