"""Lane M: approve-by-reply parser (strict allow-list grammar, F5).

Grammar (case-insensitive, one command per line):
    APPROVE|OK|YES  ALL | 1 | 1,2 | 1-5 | 1 and 2
    REJECT <items> [: reason]
    EDIT <n> : new text           (text required)
Anything else is unknown and applies nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from cm.contracts.review import ReplyCommand, ReplyParse

MAX_ITEMS = 50
_WRAPPED_QUOTE = re.compile(r"^On .{0,200}?wrote:\s*$|^-{2,}\s*(Original Message|Forwarded message)", re.I)
_ON_START = re.compile(r"^On\s.+", re.I)
_PLEASANT = re.compile(
    r"^(thanks|thank you|regards|best|best regards|cheers|hi|hello|dear .*|dr\.? ?\w*|ok thanks|sent from my .*)[.!, ]*$", re.I
)
_ITEMS = r"(?P<items>all|\d+(?:\s*(?:,|-|and|&|\s)\s*\d+)*)"
_APPROVE = re.compile(rf"^(?:approve|ok|yes)\s+{_ITEMS}\s*[.!]?$", re.I)
_REJECT = re.compile(rf"^reject\s+{_ITEMS}\s*(?:[:\-]\s*(?P<text>.+))?$", re.I)
_EDIT = re.compile(r"^edit\s+(?P<items>\d+)\s*[:\-]\s*(?P<text>\S.*)$", re.I)


@dataclass
class ParsedReply:
    parse: ReplyParse
    unknown_lines: list[str] = field(default_factory=list)

    @property
    def needs_clarification(self) -> bool:
        return bool(self.unknown_lines) or not self.parse.commands


def strip_quoted(text: str) -> str:
    """Drop quoted history: > lines, 'On ... wrote:', original-message markers, signature."""
    out: list[str] = []
    lines = text.replace("\r\n", "\n").split("\n")
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith(">") or s == "--" or s == "-- ":
            if s.startswith(">"):
                continue
            break
        if _WRAPPED_QUOTE.match(s):
            break
        if _ON_START.match(s) and "wrote:" in " ".join(lines[i : i + 3]):
            break
        out.append(line)
    return "\n".join(out)


def expand_items(spec: str) -> list[int] | None:
    """'1,2' / '1-5' / '1 and 2' -> sorted unique numbers; None on garbage."""
    s = spec.lower().replace("and", ",").replace("&", ",")
    nums: set[int] = set()
    for part in re.split(r"[,\s]+", s.strip()):
        if not part:
            continue
        m = re.fullmatch(r"(\d+)-(\d+)", part)
        if m:
            a, b = int(m[1]), int(m[2])
            if a < 1 or b < a or b > MAX_ITEMS:
                return None
            nums.update(range(a, b + 1))
        elif part.isdigit() and 1 <= int(part) <= MAX_ITEMS:
            nums.add(int(part))
        else:
            return None
    # "1 - 5" with spaces becomes tokens "1","-","5"; reject rather than guess.
    return sorted(nums) or None


def _items(spec: str) -> list[int] | None:
    if spec.strip().lower() == "all":
        return []
    return expand_items(re.sub(r"\s*-\s*", "-", spec.strip()))


def parse_reply(body: str) -> ParsedReply:
    """Parse the doctor's own text. Never raises; unknown text is returned, not acted on."""
    cmds: list[ReplyCommand] = []
    unknown: list[str] = []
    for raw in strip_quoted(body).split("\n"):
        line = raw.strip()
        if not line or _PLEASANT.match(line):
            continue
        cmd = _parse_line(line)
        if cmd is None:
            unknown.append(line[:120])
        else:
            cmds.append(cmd)
    return ParsedReply(ReplyParse(commands=cmds, parser="regex", needs_confirm=bool(unknown)), unknown)


def _parse_line(line: str) -> ReplyCommand | None:
    if m := _APPROVE.match(line):
        items = _items(m["items"])
        return None if items is None else ReplyCommand(verb="approve", items=items)
    if m := _REJECT.match(line):
        items = _items(m["items"])
        text = (m["text"] or "").strip() or None
        return None if items is None else ReplyCommand(verb="reject", items=items, text=text)
    if m := _EDIT.match(line):
        items = _items(m["items"])
        return None if items is None else ReplyCommand(verb="edit", items=items, text=m["text"].strip())
    return None
