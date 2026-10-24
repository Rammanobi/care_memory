## 1. Templates
- [x] 1.1 `cm/router/templates/reminders.yaml`: daily check-in, missed-dose nudge, visit, lab, refill (tests: `tests/unit/content/test_templates.py`)
- [x] 1.2 `cm/router/templates/confirmations.yaml`: reminder time changed, visit moved, request received, consent confirm, consent revoke
- [x] 1.3 `cm/router/templates/supporter_and_safety.yaml`: Supporter weekly summary, emergency note

## 2. Fixtures
- [x] 2.1 `fixtures/text_bank.json`: 30 patient replies, 30 doctor drafts (tests: `tests/unit/content/test_text_bank.py`)

## 3. Scanner
- [x] 3.1 `scripts/banned_terms.py` with scan_text, scan_file, scan_repo, main (tests: `tests/unit/content/test_banned_terms.py`)
- [x] 3.2 `data/guidelines/README.md` stub

## 4. Verification
- [x] 4.1 `python -m pytest tests/unit/content` green (50 passed)
- [x] 4.2 `python scripts/banned_terms.py` exits 0 on the repository
