# Analysis Report: psm-validate

**Grade: Good**

1 HIGH (absolute path di ps-static-scan.py JSON output), 1 LOW (vendor skip via string match bisa false-positive). SKILL.md bersih — 0 temuan. Script lainnya (ps-flashlight-run.py) solid.

| Severity | Count |
| --- | --- |
| Critical | 0 |
| High | 1 |
| Medium | 0 |
| Low | 1 |

## Findings

### High (1)

#### VAL-H1 — Absolute path di JSON output field module_path

- Lens: architecture
- Location: `scripts/ps-static-scan.py:136`

### Low (1)

#### VAL-L1 — Vendor skip via substring match bisa false-positive

- Lens: determinism
- Location: `scripts/ps-static-scan.py:59`
