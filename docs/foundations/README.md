# Foundations-Konzept (Zielbild)

Dieses Verzeichnis beschreibt die geplante Zielarchitektur mit 22 Foundations.

Ziel:
- kleine, mode-spezifische `modes/*`-Dateien
- starke zentrale Bausteine für Orchestration, Budget, Logging, LLM und Retrieval
- klare, auditierbare Ausführung statt impliziter Agent-Magie

Reihenfolgeempfehlung (grob, 22 Foundations):
1. Repository / Workspace Foundation (12)
2. Runtime Settings Foundation (04)
3. Trust & Safety / Policy Foundation (14)
4. Capability / Command Contract Foundation (15)
5. Mode Execution Foundation (01)
6. Orchestration Foundation (02)
7. Budget Foundation (03)
8. Output Contract Foundation (10)
9. Observability Foundation (11)
10. LLM Provider Foundation (05)
11. LLM Tasks Foundation (06)
12. Index / Knowledge Snapshot Foundation (18)
13. Retrieval Foundation (07)
14. Evidence & Ranking Foundation (08)
15. Target Resolution Foundation (09)
16. Change Planning / Modification Proposal Foundation (13)
17. Sandbox / Execution Environment Foundation (19)
18. Tool / Shell Execution Foundation (20)
19. Git / VCS Integration Foundation (21)
20. Mutation / Change Execution Foundation (16)
21. .forge Artifact Lifecycle Foundation (17)
22. Run History / Context Foundation (22)

Konsistenzkonventionen (übergreifend):
- Statusräume sind je Vertrag explizit und geschlossen zu definieren.
- Vertrags-/Schema-Versionen sind pro Kernobjekt verpflichtend (`*_contract_version`, `schema_version`).
- Normative Entscheidungen (`allowed|blocked|limited`) werden ausschließlich über Policy (14) geführt.
- Orchestration-`outcome_type=proposal` wird im Output-Vertrag (10) als `result_type=recommendation` abgebildet.

Einzeldokumente:
- [01-mode-execution-foundation.md](./01-mode-execution-foundation.md)
- [02-orchestration-foundation.md](./02-orchestration-foundation.md)
- [03-budget-foundation.md](./03-budget-foundation.md)
- [04-runtime-settings-foundation.md](./04-runtime-settings-foundation.md)
- [05-llm-provider-foundation.md](./05-llm-provider-foundation.md)
- [06-llm-tasks-foundation.md](./06-llm-tasks-foundation.md)
- [07-retrieval-foundation.md](./07-retrieval-foundation.md)
- [08-evidence-ranking-foundation.md](./08-evidence-ranking-foundation.md)
- [09-target-resolution-foundation.md](./09-target-resolution-foundation.md)
- [10-output-contract-foundation.md](./10-output-contract-foundation.md)
- [11-observability-foundation.md](./11-observability-foundation.md)
- [12-repository-workspace-foundation.md](./12-repository-workspace-foundation.md)
- [13-change-planning-modification-proposal-foundation.md](./13-change-planning-modification-proposal-foundation.md)
- [14-trust-safety-policy-foundation.md](./14-trust-safety-policy-foundation.md)
- [15-capability-command-contract-foundation.md](./15-capability-command-contract-foundation.md)
- [16-mutation-change-execution-foundation.md](./16-mutation-change-execution-foundation.md)
- [17-forge-artifact-lifecycle-foundation.md](./17-forge-artifact-lifecycle-foundation.md)
- [18-index-knowledge-snapshot-foundation.md](./18-index-knowledge-snapshot-foundation.md)
- [19-sandbox-execution-environment-foundation.md](./19-sandbox-execution-environment-foundation.md)
- [20-tool-shell-execution-foundation.md](./20-tool-shell-execution-foundation.md)
- [21-git-vcs-integration-foundation.md](./21-git-vcs-integration-foundation.md)
- [22-run-history-context-foundation.md](./22-run-history-context-foundation.md)
