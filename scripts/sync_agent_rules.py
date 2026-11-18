"""Generate .cursor/rules/*.mdc from .claude/rules and .claude/skills (single source of truth).

Run after editing anything under .claude/:  python scripts/sync_agent_rules.py
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLAUDE = ROOT / ".claude"
CURSOR = ROOT / ".cursor" / "rules"
HEADER = "<!-- generated from .claude/{src} by scripts/sync_agent_rules.py; edit the source and re-run -->"


def first_heading(text: str) -> str:
    m = re.search(r"^# (.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def main() -> None:
    CURSOR.mkdir(parents=True, exist_ok=True)
    for old in CURSOR.glob("*.mdc"):
        old.unlink()
    for rule in sorted((CLAUDE / "rules").glob("*.md")):
        body = rule.read_text(encoding="utf-8")
        desc = first_heading(body).replace('"', "'")
        out = f'---\ndescription: "{desc}"\nglobs:\nalwaysApply: true\n---\n{HEADER.format(src=f"rules/{rule.name}")}\n\n{body}'
        (CURSOR / f"{rule.stem}.mdc").write_text(out, encoding="utf-8")
    for skill in sorted((CLAUDE / "skills").glob("*/SKILL.md")):
        text = skill.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
        meta, body = (m.group(1), m.group(2)) if m else ("", text)
        desc = re.search(r"^description:\s*(.+)$", meta, re.MULTILINE)
        description = desc.group(1).strip() if desc else first_heading(body)
        name = skill.parent.name
        out = (
            f"---\ndescription: {description}\nglobs:\nalwaysApply: false\n---\n"
            f"{HEADER.format(src=f'skills/{name}/SKILL.md')}\n{body}"
        )
        (CURSOR / f"skill-{name}.mdc").write_text(out, encoding="utf-8")
    print(f"wrote {len(list(CURSOR.glob('*.mdc')))} Cursor rules to {CURSOR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
