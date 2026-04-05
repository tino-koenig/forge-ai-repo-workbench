# Foundation 21: Git / VCS Integration Foundation

## Zweck
Einheitlicher Vertrag für Git-Status, Diffs, Branch-/Worktree-Kontext und patchnahe Repo-Operationen.

## Kernidee
- VCS-Zustand als explizite, versionierte Kontextbasis
- kein implizites „Nebenbei-Git“
- sichere, nachvollziehbare VCS-Operationen mit klaren Guardrails

## Was sie umfasst
- Repo-State-Snapshot
- Diff- und Baseline-Modelle
- Patch-Check/Apply/Reverse-Check
- Branch-/Worktree-Strategien
- Konflikt-/Safety-Regeln
- Integration mit Output/Observability/Mutation

## Erwarteter Umfang
Mittel bis groß

## Aufwand für Realisierung
Mittel bis hoch

## Priorität
P1

## Risiken
- fehlerhafte Baseline-Auswahl verfälscht Ergebnisse
- unsichere Patch-Anwendung in dirty worktrees
- inkonsistente VCS-Provenienz in Outputs

## Erfolgskriterium
Jeder vcs-relevante Lauf hat einen expliziten, reproduzierbaren VCS-Kontext und sichere Apply-/Conflict-Regeln.

## Konzept

### Problem
Ohne zentrale VCS-Foundation werden Branch-/Diff-/Apply-Informationen uneinheitlich genutzt. Das erschwert Analysequalität, Patch-Sicherheit und Audit.

### Ziel
- Einheitlicher, auslesbarer VCS-Vertrag für Analyse, Proposal und Mutation.
- VCS-Snapshot als Pflichtkontext für change-nahe Flows.
- Klare Sicherheitsregeln für Apply und Konflikte.

### Nicht-Ziele
- Kein Ersatz für Tool-Execution (20).
- Keine UI-spezifische Git-Visualisierung.

### Leitprinzipien
- explicit baseline
- explicit dirty-state handling
- safe apply before convenience
- provenance always visible

## Spezifikation

### 1. Repo-State-Snapshot
Pflichtfelder:
- `vcs_contract_version`
- `repo_root`
- `vcs_type` (`git`)
- `head_ref`
- `head_commit`
- `branch_name`
- `dirty_state`
- `untracked_count`
- `staged_count`
- `snapshot_created_at`

### 2. Diff-Vertrag
Mindestens unterstützte Diff-Sichten:
- `working_tree_vs_head`
- `staged_vs_head`
- `working_tree_vs_base_ref`

Jede Diff-Sicht ist referenzierbar (`diff_ref`) und provenance-markiert.

### 3. Baseline-Auswahl
Baseline muss explizit sein:
- `base_ref`
- `base_resolution_source` (`user|policy_default|auto_resolved`)

Unklare Baseline führt zu `baseline_ambiguous`.

### 4. Patch-Operationen
Pflichtoperationen:
- `patch_check`
- `patch_apply`
- `patch_reverse_check`

Bei Konflikten:
- `apply_status` liegt im definierten Apply-Statusraum; Konfliktfälle müssen mindestens `conflict|blocked` abbilden
- strukturierte Konfliktdiagnose inkl. betroffener Targets

Apply-Statusraum (verbindlich):
- `checked|applicable|applied|conflict|blocked|error`

### 5. Safety-Regeln
- write-affecting VCS-Operationen nur mit gültiger Policy/Freigabe.
- Keine stillen destructive operations.
- Dirty-Worktree-Regeln müssen zentral geprüft werden (`allow_dirty_apply` nur explizit).
- Apply in dirty state ohne explizite Freigabe führt zu `blocked_dirty_state`.

### 6. Branch-/Worktree-Kontext
- Branch-/Worktree-Strategie muss explizit gewählt oder policy-gesteuert sein.
- Wechsel/Erstellung werden als Event mit Rückbezug protokolliert.

### 7. Provenienzvertrag
Output/Observability müssen ausweisen:
- verwendete Baseline
- relevante Diff-Referenzen
- Apply-/Conflict-Ergebnis
- VCS-Kontext-Snapshot-ID

### 8. Konflikt-/Recovery-Vertrag
- Konflikte werden als strukturierte `conflict_items[]` ausgegeben.
- `apply_status=conflict` muss einen `recovery_hint` enthalten.
- Reverse-Check ist für mutierende Apply-Pfade verpflichtend.

## Design

### Zielstruktur (Vorschlag)
- `core/vcs_foundation.py`
  - State Snapshot
  - Diff Resolver
  - Apply Controller
- `core/vcs_policies.py`
  - dirty-state/apply/branch policies
- `core/vcs_diagnostics.py`
  - baseline/conflict diagnostics

### Datenmodelle (konzeptionell)
- `VcsSnapshot`
- `VcsDiffRequest` / `VcsDiffResult`
- `VcsApplyRequest` / `VcsApplyResult`
- `VcsDiagnostic`

### API-Skizze
- `capture_vcs_snapshot(context) -> VcsSnapshot`
- `resolve_vcs_baseline(request, snapshot, policy) -> BaselineDecision`
- `compute_vcs_diff(request, snapshot) -> VcsDiffResult`
- `check_patch_applicability(request, snapshot) -> VcsApplyResult`
- `apply_patch_with_safety(request, snapshot, policy) -> VcsApplyResult`

### Integrationspunkte
- Foundation 16: Mutation Execution nutzt VCS-Safety-Vertrag
- Foundation 10: Output mit Baseline-/Diff-/Apply-Provenienz
- Foundation 11: VCS-Events und Konfliktdiagnosen
- Foundation 20: konkrete Shell/Git-Aufrufe laufen über Tool-Execution
- Foundation 14: normative Freigaben für apply-/branch-Operationen

## Verbindlicher Vertragskern (jetzt)

Diese Punkte sind in Foundation 21 verpflichtend:
- expliziter VCS-State-Snapshot
- deklarierte Baseline und Diff-Sichten
- sichere Patch-Check/Apply-Regeln mit Konfliktdiagnose
- keine impliziten destruktiven VCS-Operationen
- vollständige VCS-Provenienz in Output und Observability

## Bewusst verschoben (spätere Detailphasen)

- tiefere blame-/history-Analysen für Empfehlungssysteme
- multi-repo/submodule spezifische Strategien
- semantische Diff-Klassifikation

## Detaillierungsregel

Foundation 21 definiert VCS-Kontext und sichere VCS-Operationen.  
Toolausführung bleibt in Foundation 20, mutierende Umsetzung in Foundation 16.
