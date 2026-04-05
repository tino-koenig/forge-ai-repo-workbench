# Foundation 16: Mutation / Change Execution Foundation

## Zweck
Kontrollierter Vertrag für tatsächliche Dateiänderungen, Patch-Erzeugung und optionales Anwenden.

## Kernidee
Mutation ist eine eigene Phase nach Proposal oder expliziter Nutzeranweisung, nie ein stilles Nebenprodukt.

## Was sie umfasst
- Execution-Request aus Proposal oder Nutzeranweisung
- `dry_run|patch_only|apply`
- Patch-/Change-Modelle
- Write-Targets und Scope-Prüfung
- Vorbedingungen/Konflikte/Blocker
- Idempotenz-/Safety-Regeln
- Ergebnisvertrag
- Rollback-/Revert-Hinweise

## Erwarteter Umfang
Groß

## Aufwand für Realisierung
Hoch

## Priorität
P1

## Risiken
- Mutation startet ohne belastbare Basis (Proposal/explicit request)
- Scope-Überschreitungen führen zu unkontrollierten Änderungen
- fehlende Verify-/Rollback-Pfade verschlechtern Safety

## Erfolgskriterium
Jede Mutation ist explizit angefordert, policy-validiert, scope-begrenzt, überprüfbar und rückverfolgbar.

## Konzept

### Problem
Ohne zentrale Mutation-Foundation drohen stille Änderungen, inkonsistente Apply-Regeln und nicht nachvollziehbare Execution-Pfade.

### Ziel
- Einheitlicher Vertrag für `dry_run|patch_only|apply`.
- Strikte Trennung von Planung (13) und Umsetzung (16).
- Sicherheits- und Verifikationsregeln als Pflichtbestandteil jeder Mutation.

### Nicht-Ziele
- Keine automatische Konfliktmagie ohne explizite Regeln.
- Kein Ersatz für Policy (14) oder Environment/Tool-Ausführung (19/20).

### Leitprinzipien
- explicit mutation intent
- scope-limited execution
- verify before finalize
- observable and reversible outcomes

## Spezifikation

### 1. Execution-Vertrag
Pflichtfelder:
- `execution_id`, `mode`, `proposal_ref(optional)`, `targets`, `write_scope`, `status`, `changes`, `diagnostics`

Statusraum (verbindlich):
- `planned|validated|applied|partial|blocked|error`

Mapping-Hinweis zu Foundation 10:
- `status=applied` entspricht im Output-Kern typischerweise `result_type=execution_result` mit `result_status=success`.

### 2. Execution-Modi
- `dry_run`: keine Dateimutation, nur simulierte Änderungsartefakte
- `patch_only`: Patch erzeugen, aber nicht anwenden
- `apply`: tatsächliche Anwendung innerhalb validiertem Scope

### 3. Sicherheitsregeln
- keine stillen Repo-Änderungen
- keine Änderung außerhalb freigegebenem Scope
- keine Ausführung ohne nachvollziehbare Änderungsbasis

### 4. Preconditions und Gates
Vor `apply` verpflichtend:
- positive Policy-Entscheidung (14)
- gültiges Environment/Tool-Setup (19/20)
- write-scope-validierung
- optionale Human-Freigabe gemäß Runtime/Policy

### 5. Verifikationsvertrag
Nach Mutation:
- `verification_steps[]`
- `verification_status`
- `regression_signals[]` (falls vorhanden)
- `post_apply_diagnostics[]`

### 6. Rollback-/Recovery-Vertrag
- Ergebnis enthält `rollback_hint` und `revert_feasibility`.
- Bei teilweisem Fehlschlag muss `status=partial|error` plus Recovery-Hinweise geliefert werden.

### 7. Provenienz und Nachweis
Pflichtreferenzen:
- `proposal_ref` oder `explicit_request_ref`
- `execution_ref`
- `change_artifact_refs` (patch/diff)
- `policy_decision_ref`
- `environment_ref`
- `tool_execution_refs[]`

## Design

### Zielstruktur (Vorschlag)
- `core/mutation_foundation.py`
- `core/mutation_models.py`
- `core/mutation_safety.py`
- `core/mutation_verification.py`

### API-Skizze
- `plan_patch(execution_request, context) -> PatchPlan`
- `apply_patch_plan(plan, context) -> MutationResult`
- `validate_mutation_scope(plan, policy) -> ValidationResult`
- `verify_mutation_result(result, verification_policy) -> VerificationResult`
- `build_mutation_provenance(result) -> MutationProvenance`

### Integrationspunkte
- Foundation 13: Proposal als primäre Änderungsbasis
- Foundation 14: normative write-/apply-freigabe
- Foundation 19/20: kontrollierte Ausführungsumgebung und Toolausführung
- Foundation 21: VCS apply/check/conflict-Kontext
- Foundation 10/11: execution result contract + observability chain

## Verbindlicher Vertragskern (jetzt)

Diese Punkte sind in Foundation 16 verpflichtend:
- explizite Execution-Modi (`dry_run|patch_only|apply`)
- vorgelagerte Scope-/Policy-/Environment-Gates
- strukturierter Mutation-Result-Vertrag inklusive Verifikationsstatus
- klare Provenienz von Basis, Entscheidung und Änderungsartefakten

## Bewusst verschoben (spätere Detailphasen)

- automatische Konfliktauflösung
- teilautomatische Revert-Strategien
- adaptive Verify-Strategien je Änderungstyp

## Detaillierungsregel

Foundation 16 definiert Ausführungssicherheit und Änderungsvertrag, nicht die Analysephase.
