# Foundation 20: Tool / Shell Execution Foundation

## Zweck
Einheitlicher Vertrag für Tool-Aufrufe, Shell-Kommandos und Prozessausführung.

## Kernidee
- Tool-/Shell-Nutzung als eigene strukturierte Schicht
- standardisierte Requests/Results statt ad-hoc Prozessaufrufe
- klare Fehlerklassen, Policies, Budgets und Telemetrie

## Was sie umfasst
- `ToolRequest` / `ToolResult`
- Toolklassen und Kommando-Klassifikation
- stdout/stderr/exit-code-Vertrag
- Retry-/Timeout-/Idempotenzregeln
- Integration mit Foundation 19/14/03/11

## Erwarteter Umfang
Groß

## Aufwand für Realisierung
Hoch

## Priorität
P1

## Risiken
- zu breite Toolfreigaben untergraben Safety
- uneinheitliche Fehlerbehandlung je Aufrufpfad
- schlechtere Reproduzierbarkeit ohne normierte Klassifikation

## Erfolgskriterium
Jeder Tool-/Shell-Call läuft über einen einheitlichen, policy-validierten und observability-gekoppelten Vertrag.

## Konzept

### Problem
Direkte Shell- oder Toolaufrufe ohne zentrale Vertragslogik führen zu inkonsistenten Fehlermustern, unklaren Nebenwirkungen und schwerer Governance.

### Ziel
- Zentrale Execution-API für alle Tool-/Shell-Interaktionen.
- Explizite Klassifikation und Nebenwirkungsbewertung pro Kommando.
- Klare Trennung zu Environment (19) und Mutation (16).

### Nicht-Ziele
- Keine Mode-spezifischen Toolstrategien im Kern.
- Kein Ersatz für Git-/VCS-Semantik (21).

### Leitprinzipien
- classify first, execute second
- side effects are explicit
- deterministic diagnostics
- no hidden command execution paths

## Spezifikation

### 1. Request-Vertrag
`ToolRequest` enthält mindestens:
- `tool_contract_version`
- `tool_name`
- `command` / `args`
- `command_class` (`read_only|build|test|lint|format|write_affecting`)
- `expected_side_effect` (`none|filesystem|network|mixed`)
- `timeout_ms`
- `retry_policy_ref` (optional)
- `environment_ref` (Foundation 19)
- `request_id`

### 2. Result-Vertrag
`ToolResult` enthält mindestens:
- `tool_contract_version`
- `status` (`ok|partial|blocked|error|timeout`)
- `exit_code`
- `stdout_ref` / `stderr_ref` (oder redigierte Inline-Varianten)
- `duration_ms`
- `diagnostics[]`
- `observed_side_effects`
- `command_fingerprint`
- `request_id`

### 2a. Fehlerklassen (verbindlich)
Mindestens:
- `tool_config_error`
- `tool_not_found`
- `tool_permission_error`
- `tool_timeout_error`
- `tool_runtime_error`
- `tool_policy_blocked`

### 3. Kommando-Klassifikation
- Klassifikation muss vor Ausführung feststehen.
- Klassifikation steuert Policy-/Budget-/Environment-Prüfungen.
- Fehlklassifikation ist diagnoserelevant (`command_class_mismatch`).

### 4. Timeout-/Retry-Regeln
- Timeout ist verpflichtend.
- Retry nur bei klassifizierten transienten Fehlern.
- Retry nie für eindeutig nicht-idempotente write-affecting Kommandos ohne explizite Freigabe.

### 5. Idempotenz- und Nebenwirkungs-Hinweise
Pflichtfelder pro Request:
- `idempotency_hint` (`idempotent|likely_idempotent|non_idempotent|unknown`)
- `side_effect_hint`

Abweichungen zwischen Hint und beobachtetem Verhalten werden protokolliert.

### 6. Policy-/Sandbox-Kopplung
- Ausführung nur in validiertem Environment (19).
- Policy (14) prüft Toolklasse, Scope und Netzwerkrechte.
- Bei Verstoß: `status=blocked`, keine Ausführung.

### 7. Budget-Kopplung
- Toolausführung meldet Budgetverbrauch (Zeit, externe Aufrufe, optional Dateien).
- Budget-Block muss vor Ausführung greifen (Precheck).
- Bei `status=blocked` durch Budget wird kein Folge-Retry ausgelöst.

### 8. Observability-Kopplung
Pflichtevents:
- `tool_requested`
- `tool_classified`
- `tool_executed`
- `tool_blocked`
- `tool_failed`

Mit `tool_name`, `command_class`, `environment_ref`, `policy_version`, `settings_snapshot_id`.
`command_fingerprint` und `retry_count` sind für ausgeführte Calls mitzuführen.

## Design

### Zielstruktur (Vorschlag)
- `core/tool_execution_foundation.py`
  - Request Validator
  - Classification Gate
  - Execution Controller
- `core/tool_execution_policies.py`
  - command-class policies, retry/timeouts
- `core/tool_execution_diagnostics.py`
  - error classes and diagnostics

### Datenmodelle (konzeptionell)
- `ToolRequest`
- `ToolResult`
- `ToolDiagnostic`
- `ToolExecutionContext`

### API-Skizze
- `classify_tool_request(request, context) -> ClassificationDecision`
- `validate_tool_request(request, environment, policy) -> ValidationDecision`
- `execute_tool_request(request, environment) -> ToolResult`
- `apply_tool_retry_policy(result, request, policy) -> RetryDecision`
- `summarize_tool_execution(result) -> ToolExecutionSummary`

### Integrationspunkte
- Foundation 19: Environment-Handle und Scope-Validierung
- Foundation 14: normative Block-/Allow-Entscheidungen
- Foundation 03: Budgetdeltas und Budget-Prechecks
- Foundation 11: Eventing und Diagnostik
- Foundation 16: write-affecting Pfade als mutierende Vorstufe
- Foundation 21: Git-relevante Toolaufrufe über VCS-Vertrag konsolidieren

## Verbindlicher Vertragskern (jetzt)

Diese Punkte sind in Foundation 20 verpflichtend:
- zentraler ToolRequest/ToolResult-Vertrag
- verpflichtende Kommando-Klassifikation vor Ausführung
- strukturierte Fehler-/Diagnosefelder
- timeout/retry/idempotenz-Regeln mit Policy-Bindung
- verpflichtende Integration mit Sandbox, Budget und Observability

## Bewusst verschoben (spätere Detailphasen)

- tiefere semantische Command-Parser
- adaptive Retry-Strategien aus Historie
- erweiterte Tool-Profile pro Repository-Typ

## Detaillierungsregel

Foundation 20 definiert den Ausführungsvertrag für Tools/Shell.  
Environment-Isolation liegt in Foundation 19, Mutation in Foundation 16.
