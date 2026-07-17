#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""One definition of what is skill CONTENT versus what is a build artifact living inside it.

A skill directory holds two different things. There is the content that ships — SKILL.md,
references/, scripts/, assets/ — and there are this builder's own process artifacts:
`.memlog.md` and the dated run folders under `.analysis/`. A scanner that does not tell
them apart ends up reading its own output.

That is not hypothetical. scan-path-standards reported 7248 path "findings" for psm-validate
of which ZERO touched the live tree — every one came from earlier analysis reports. Because
each run scans the reports of every run before it, the artifact doubled every round: 2 KB,
13 KB, 27 KB, 58 KB, 123 KB, 274 KB, 591 KB, 1.3 MB across thirteen rounds, reaching 24% of
the whole repository. Each analyze run then had to be told to discount the noise by hand,
which is a gotcha the tooling should not be creating.

The rule is deliberately about shape, not product names: any path component that starts with
a dot, relative to the skill root, is an artifact — the same convention that already covers
.git and .venv. Naming `.analysis` and `.memlog.md` explicitly would need editing again the
next time the builder writes something; this does not.
"""
from pathlib import Path


def is_build_artifact(path, skill_root):
    """True when `path` is a build artifact rather than shipped skill content.

    A path outside `skill_root` is not an artifact of it — say so rather than guessing.
    """
    try:
        rel = Path(path).resolve().relative_to(Path(skill_root).resolve())
    except ValueError:
        return False
    return any(part.startswith(".") for part in rel.parts)


def skill_files(skill_root, patterns=("*.md", "*.json")):
    """Sorted skill-content files matching `patterns`, with build artifacts excluded."""
    root = Path(skill_root)
    found = set()
    for pattern in patterns:
        found |= {
            p for p in root.rglob(pattern)
            if p.is_file() and not is_build_artifact(p, root)
        }
    return sorted(found)
