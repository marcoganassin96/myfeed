# Backlog

Improvements and automation gaps identified during active development. Not bugs — things that work but should be hardened or automated.

---

## Index

| # | File | Area | Items | Status |
|---|------|------|-------|--------|
| 1 | [ci-cd-automation.md](ci-cd-automation.md) | CI/CD | Post-deploy smoke test, `sam local invoke` in CI, unit tests in CI, build output validation, CloudWatch error check | All open |

---

## Open Items Summary

| # | Item | File | Priority |
|---|------|------|----------|
| 1.1 | Post-deploy smoke test in `scripts/pipeline.py` | ci-cd-automation.md | High — prevents repeating 2026-05-08 incident |
| 1.2 | `sam local invoke` check in GitHub Actions | ci-cd-automation.md | High — catches import errors before AWS deploy |
| 1.3 | `pytest` in GitHub Actions | ci-cd-automation.md | Medium — tests exist locally, not enforced in CI |
| 1.4 | `sam build` output validation (ResolveDependencies check) | ci-cd-automation.md | Medium — silent failure guard |
| 1.5 | CloudWatch error check after deploy | ci-cd-automation.md | Low — redundant once 1.1 and 1.2 are in place |

---

## How to Add Items

1. Create or update a file in this directory (one file per area)
2. Add a row to the Index table above
3. Add rows to Open Items Summary for each new item
4. When an item ships, mark it `Done` in both tables and note the commit or PR
