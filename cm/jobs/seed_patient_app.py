"""Lane B: sample content of the patient app for PT-0142 (mirrors web/src/pages/PatientApp/sampleData.ts)."""

from __future__ import annotations

# 60 days oldest first; the last character is today (not yet recorded in the seed).
_FIRST30 = "oooomoooooooooooomoooooooooomo"
_LAST30 = "ooooooooooomoooooooooooooooooo"
HISTORY60 = _FIRST30 + _LAST30
MISS_REASON = {
    4: "Forgot to take it",
    17: "Travelling",
    28: "Felt unwell",
    41: "Ran out of tablets",
}

# id, days_ago, title, text, for_supporter
PATIENT_MESSAGES = [
    (
        "pm-1",
        0,
        "Bring your medicine strip",
        "Please bring your medicine strip to the visit on Wednesday at 6 pm.",
        True,
    ),
    (
        "pm-2",
        1,
        "Lab slot held for you",
        "Your lab slot is held for Friday at 10 am. Please come to the clinic reception first.",
        False,
    ),
    (
        "pm-3",
        3,
        "Well done this week",
        "Thank you. You did not miss a day this week. Keep going.",
        True,
    ),
    (
        "pm-4",
        8,
        "Reminder time saved",
        "Your reminder time is saved. Tell us if you want to change it again.",
        False,
    ),
    (
        "pm-5",
        15,
        "Clinic closed on Sunday",
        "The clinic is closed this Sunday. It opens again on Monday at 9 am.",
        False,
    ),
    (
        "pm-6",
        30,
        "Welcome to CareMemory",
        "Welcome. Your care team will send you approved messages here.",
        False,
    ),
]
UNREAD_MESSAGES = {"pm-1", "pm-2"}

APPOINTMENTS = [
    {
        "id": "u1",
        "bucket": "upcoming",
        "appt_kind": "visit",
        "title": "Clinic visit",
        "when": "Wed 6 pm",
        "place": "Anantapur Clinic",
    },
    {
        "id": "u2",
        "bucket": "upcoming",
        "appt_kind": "lab",
        "title": "Lab test",
        "when": "Fri 10 am",
        "place": "Anantapur Clinic lab",
    },
    {
        "id": "u3",
        "bucket": "upcoming",
        "appt_kind": "visit",
        "title": "Clinic visit",
        "when": "Next month",
        "place": "Anantapur Clinic",
    },
    {
        "id": "p1",
        "bucket": "past",
        "appt_kind": "visit",
        "title": "Clinic visit",
        "when": "2 weeks ago",
        "place": "Anantapur Clinic",
        "days_ago": 14,
        "note": "Done",
    },
    {
        "id": "p2",
        "bucket": "past",
        "appt_kind": "lab",
        "title": "Lab test",
        "when": "4 weeks ago",
        "place": "Anantapur Clinic lab",
        "days_ago": 28,
        "note": "Your doctor has the result",
    },
    {
        "id": "p3",
        "bucket": "past",
        "appt_kind": "visit",
        "title": "Clinic visit",
        "when": "6 weeks ago",
        "place": "Anantapur Clinic",
        "days_ago": 42,
        "note": "Done",
    },
    {
        "id": "p4",
        "bucket": "past",
        "appt_kind": "lab",
        "title": "Lab test",
        "when": "8 weeks ago",
        "place": "Anantapur Clinic lab",
        "days_ago": 56,
        "note": "Your doctor has the result",
    },
]

# id, text, when, status, reply  (sx-1 equals the archived rq-0 in seed_data.json, so it is skipped)
PAST_REQUESTS = [
    (
        "sx-2",
        "I need help getting my refill.",
        "3 weeks ago",
        "approved",
        "A nurse called you and your refill is ready.",
    ),
    ("sx-3", "Can I change my visit to Monday?", "4 weeks ago", "declined", None),
    (
        "sx-4",
        "Where do I go for the lab test?",
        "6 weeks ago",
        "approved",
        "Please go to the clinic reception first.",
    ),
    ("sx-5", "Can my sister come with me?", "7 weeks ago", "declined", None),
]


# Fictional patient documents and plain-language medicines for PT-0142 (no drug names).
# id, days_ago, doc_kind, title, summary
DOCUMENTS = [
    (
        "d1",
        14,
        "visit_summary",
        "Visit summary",
        "Your clinic visit went well. Keep taking your tablets every day.",
    ),
    ("d2", 28, "lab_slip", "Lab slip", "Your blood test was done. Your doctor has the result."),
    (
        "d3",
        45,
        "letter",
        "Welcome letter",
        "Welcome to your care team. Call the clinic if you have a question.",
    ),
]
# id, label, when, note
MEDICINES = [
    ("m1", "Morning tablets", "Every day with water", "Take them after breakfast."),
    ("m2", "Evening vitamin", "Every evening", None),
]
