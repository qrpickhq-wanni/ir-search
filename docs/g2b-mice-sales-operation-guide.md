# G2B MICE Sales Operation Guide

## Purpose

Connect 나라장터 용역 공고·낙찰·계약을 Showda/QRPick sales windows:

1. Direct bid review (before proposal deadline)
2. Consortium / solution partner supply to bidders
3. Award-winner outreach (after award, supplier still UNKNOWN)
4. Pre-registration / late-event windows
5. Next-cycle watch from prior-year same program

## Run

```bat
scripts\run_g2b_mice_mvp.bat
```

Or:

```bat
.venv\Scripts\python.exe app\run_g2b_mice_mvp.py --today 2026-07-16
```

Set `DATA_GO_KR_SERVICE_KEY` before live collect. Without it, exit 0 with `PARTIAL_EXPECTED`.

## Reports

Under `reports/YYYY-MM-DD/`:

| File | Content |
|------|---------|
| `g2b-mice-procurements.csv` | All linked procurements |
| `g2b-mice-sales-queue.csv` | P0–P2 queue |
| `g2b-direct-bid-opportunities.csv` | DIRECT_PRIME_BID |
| `g2b-consortium-opportunities.csv` | CONSORTIUM_BID |
| `g2b-solution-partner-opportunities.csv` | SUBCONTRACT_OR_SOLUTION_PARTNER |
| `g2b-award-winner-outreach.csv` | AWARD_WINNER_WINDOW |
| `g2b-bid-partner-window.csv` | BID_PARTNER_WINDOW |
| `g2b-next-cycle-watch.csv` | NEXT_CYCLE_WINDOW (STRONG/MEDIUM prior year) |
| `g2b-lifecycle-summary.md` | Run summary |

All CSV: UTF-8 BOM.

## Rules of engagement

- Do not assert 시스템 공급사 when unknown (`system_supplier_status=UNKNOWN`).
- Do not assert 사전등록 오픈 when unverified (`registration_open_status=UNKNOWN`).
- Eligibility is qualification-only; past deadline → readiness/go only.
- Industry names alone do not exclude routes.
- No login/CAPTCHA bypass; OpenAPI only.

## Registry note

`config/mice-source-registry.yaml` entry `g2b` remains `QUERY_EXTENSION` until this MVP is promoted; live OpenAPI path is `config/g2b-mice-lifecycle.yaml`.
