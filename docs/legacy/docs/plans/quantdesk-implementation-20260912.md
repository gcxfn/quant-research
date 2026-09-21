# QuantDesk Implementation Plan & Readiness Record (2026-09-12)

Owner: independent integration/security reviewer. This file records the approved plan, the
contract LOCK, ownership boundaries, review protocol, and — honestly — the current readiness
state of each component. It is updated as components land; author self-reported PASS never
updates readiness here, only verified evidence does.

## 1. Mandate

Implement the user's approved QuantDesk plan in `apps/quantdesk/` (shared workspace, no git
reset/checkout/commit, no touching existing research/quant files or unrelated dirty changes).
After repeated GLM-5.3 rate limits, the user explicitly authorized Codex models to complete
implementation; the main conversation coordinates integration and review.
Production-minded working code only: demos explicitly non-executable, missing integrations
fail closed, dependencies isolated to the app.

## 2. Canonical contract

The wire/env/token contract is LOCKED and transcribed in
`apps/quantdesk/verification/CONTRACT.md` (source: integration contract LOCK, 2026-09-12).
All components implement against that document; disputes resolve against it, and changes to
it require main-conversation coordination.

Summary of locked surfaces:

- Public API prefix `/api/v1`, JSON snake_case, Bearer opaque app token; auth, account
  (optimistic concurrency + idempotent trades), recommendations (executable gating), news
  (shared analysis, no account context), chat sessions/messages → tasks, task SSE with
  `Last-Event-ID`, memory, owner-protected artifacts, status.
- Capability token: `base64url(compact JSON claims) + "." + base64url(HMAC-SHA256)`, claims
  `{sub, task_id, scopes, exp}`; `CAPABILITY_SECRET` never in Pi; closed scope vocabulary;
  task-active enforcement by backend; `task_id` body matching.
- Internal tokens: `PI_MANAGER_TOKEN` (backend→manager), `PI_WORKER_TOKEN`
  (per-container, manager-only), `MODEL_SERVICE_TOKEN` (news worker, shared subject news,
  recorded usage without a usage quota).
- Canonical tools: account, recommendations, news, calculate_fees, export_data, memory_list,
  memory_save, memory_delete, artifact_save; bodies `{task_id, ...}`; JSON responses.
- Manager sandbox: `{stdout, stderr, exit_code, artifacts:[...]}`; artifacts uploaded via
  backend artifact_save; no input host paths.
- Model gateway: OpenAI-compatible `/v1/chat/completions` SSE; Pi passes capability only.

## 3. Components & ownership

| Component | Path | Owner | Status (verified) |
|---|---|---|---|
| Canonical contract + adversarial verification | `apps/quantdesk/verification/**` | independent reviewer | contract transcribed; test suite built; integration run pending backend |
| App boundary rules | `apps/quantdesk/AGENTS.md` | independent reviewer | written |
| Pi worker | `apps/quantdesk/pi/**` | Pi agent | files appearing (package.json, src, prompts, test) — not yet reviewed |
| Backend | `apps/quantdesk/server/**` | backend agent | primitives present; routes and integration under implementation |
| Desktop | `apps/quantdesk/desktop/**` (expected) | desktop agent | not present yet |
| Infra | `apps/quantdesk/infra/**` (expected) | infra agent | not present yet |

## 4. Review protocol (independent reviewer)

1. Maintain `verification/CONTRACT.md` as the canonical reference.
2. Read fresh implementation while authors work; report concrete P1/P2 issues with file+line
   to main; author PASS is evidence input, never final.
3. Once a backend appears: run `apps/quantdesk/verification/run_contract_tests.py` against it
   (see verification/README.md). Suite fails closed without a configured base URL.
4. Focus areas: externally-facing auth; RLS role/cross-user paths; model gateway scopes +
   revocation/cancel; sandbox (no secrets, outputs extraction, filesystem masks); cost
   calculations (shared cash, T+1, exact fees); stale release gates; executable gating.

## 5. Readiness log (append-only, honest)

- 2026-09-12 (reviewer): workspace inspected; `apps/` absent at start; root tree dirty with
  factor-miner work (untouched). Main baseline reported by coordinator: 25 `test_t0` tests +
  fixture smoke PASS (reviewer has not rerun the root suite; it is the production gate and
  owned by main). Docker Linux engine reported not running by coordinator — no container
  end-to-end claim is permitted yet. Python 3.11.15 available on PATH.
- 2026-09-12 (reviewer): `verification/CONTRACT.md`, `apps/quantdesk/AGENTS.md`, this plan,
  and the verification suite scaffold created. `apps/quantdesk/pi` appeared during writing;
  review queued.
- 2026-09-12 (reviewer, later): suite completed — offline selftest 14/14 PASS observed;
  integration mode verified fail-closed (exit 2, no base URL); 26 integration tests
  registered awaiting backend. Root AGENTS.md app-specific section appended (explicitly
  authorized by main this session; pre-existing dirty hunks untouched, verified via git
  diff). Coordinator confirmed server: 117.72.219.131, Ubuntu 24, 2 CPU/3.8 GiB, Docker
  working; existing :80 price-comparison app must be preserved; infra to bind loopback
  :18080. Remote integration runs will execute there once infra lands, read-only with
  respect to the existing app. Persistent status lives in
  `apps/quantdesk/verification/REPORT.md` (THS login + live model gateway listed PENDING,
  no PASS overclaim). Open hygiene item V-001: no node_modules ignore rule at root while
  Pi deps are installed — main to coordinate.

## 6. Constraints honored

- No automatic paid model calls (tests use recorded/static fixtures only).
- No claims of live server or container end-to-end before actually observed.
- Reviewer edits only owned paths; peer files inspected read-only.

## 7. Latest user amendments and observed integration (2026-09-12)

- All account/fee/breakeven/sizing/reconciliation calculations belong to the external
  developing strategy algorithm. Application stores inputs and execution records and
  calls the versioned adapter. Missing strategy never triggers a financial fallback.
- Single portable Windows EXE, public registration without invitations, minimal UI,
  no AI usage quotas. Only shared news analysis has a 100–200-character limit.
- Added user request: refined minimalist frontend; update metadata endpoint and shared
  announcements; each module explains connectivity, maintenance and API billing failure.
  Generic rate limiting must not be mislabeled as insufficient credit. Update downloads
  require trusted HTTPS metadata; no silent execution of downloaded software.
- Actual implementation files now exist for desktop, backend, Pi, gateway, egress,
  container manager and sandbox. This supersedes earlier scaffold-only snapshots.
  Build, full cross-service integration and portable EXE delivery remain pending.
- Main observed remote edge container running with existing price-comparison containers
  preserved. HTTPS health currently fails TLS handshake; edge ACME logs report authorization
  connection reset and rate limiting. Public login is NOT ready.
- Current main differential verification: backend/infra/reference token interop and
  malformed-token handling 20 passed; deployment template still has one product max-token
  assignment to remove. No model calls or financial strategy validation were performed.
