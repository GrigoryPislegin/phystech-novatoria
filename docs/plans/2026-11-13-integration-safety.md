# Integration safety execution

Spec: docs/team/tz-codex-final-sprint.md C1–C4, docs/21-application-ui-contract.md.
Base: 8741b0b. Work in the already authorised integration branch; preserve unrelated dirty files. Do not edit Egor's contracts/scoring/evidence/review or Vanya's documents/web/CI. No paid API calls, no secrets in context. Readiness investigations use actual isolated core only.

### Task 1: C1 outgoing data and logs
Reproduce escaped-reference and SDK debug leakage failures without network. Check decoded dynamic strings in both directions. Suppress dependency payload logging before imports and calls. Run full prototype suite and both replays. Expected: valid issued references survive JSON escapes; unissued references and residual findings prevent requests; no synthetic canaries in captured stdout/stderr.

### Task 2: C4 input, lifecycle and export
Reproduce late count/out validation, symlink input, partial export and fatal/local stop behavior. Add application boundary with preflight, opaque content IDs and local manifest, deadline/cancellation/progress. Publish closed-permission reports atomically. Expected: invalid preflight costs zero calls; local output validation continues; privacy/budget/network stop new calls; previous results survive. Run full suite.

### Task 3: C2 presentation boundary
Expose source-backed display rows, explicitly unverified model commentary and safe gap questions without changing scoring. Keep pending E3/E4 states explicit until corrected handoff. Document implemented application API for Vanya. Expected: fabricated free text cannot masquerade as a confirmed manager brief. Run full suite and replays.

### Task 4: C3 runtime readiness
Use scout evidence to reconcile isolated Python3.12 dependencies, add reproducible packaging within distribution permissions, and record actual blockers. No pretend live test. Expected: exact commands and offline checks or concrete missing artifact/permission; standalone Docker includes new modules.

### Task 5: Independent review and delivery
One economy reviewer; fix substantive findings with regression tests. Run repository checks, full tests and two demos, update quality log and publish integration commits. Preserve pending Egor integration and actual protected live as separate requirements.

## Review focus
Data in SDK/core exceptions and log handlers; untrusted references in nested keys; directory/symlink and atomic export failure; cancellation/deadline after successful jobs; model failures misclassified as recoverable; original schema compatibility and honest evidence status. Runtime checks must distinguish mock transport from network and standalone from protected runtime.
