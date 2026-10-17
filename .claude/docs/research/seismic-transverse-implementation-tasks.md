# 0720 implementation tasks

Plan: `.agents/docs/plans/webpier-seismic-transverse-report-regeneration.md`.
Approved: 2026-10-17, user "承認します GO".

| Task | Owner | Depends on | Status |
|---|---|---|---|
| Independent fixtures and calculator contract | core | Baseline | Complete; independent PDF/current fixtures |
| Shared seismic frame and 0720 actions | core | Fixtures | Complete; 100 new + 90 existing calculator cases passed; 3 review findings fixed |
| Four-page renderer and visual cases | report | Calculator contract | Complete; 14 tests, all current/variant pages and 40-row expanded layout verified |
| CLI, registry, GUI contracts and README | integration | Public interfaces | Complete; 374 distinct cases have passing evidence; final report/0720 CLI 49 passed |
| Targeted integration and full regression gate | root | All implementation | Related checks passed. Broader partition 3122 passed / 1 unrelated rebar failure / 2 Tk skips; replay and deferred UI recorded separately. Shared uv gate stops on existing lock mismatch |
| Security, quality, test reviews | Review team | Verified implementation | Complete; all 3 reports/logs validated, 3 findings fixed and independently verified, no unresolved Medium+ |
| Final four-page visual QA and 0720-only publication | root | Reviews and checks | Complete; formal pair matches candidate; all4pages viewed;17protectedfiles unchanged |

Product ownership is preflighted in `.agents/logs/ownership-team-execute-webpier-seismic-transverse-report-regeneration.json`. Root alone updates this task list and the plan; implementers report progress by message.
