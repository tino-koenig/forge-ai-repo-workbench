# Foundation 19: Sandbox / Execution Environment Foundation

## Zweck
Kontrollierte Ausführungsumgebung für Builds, Tests, Probeumsetzungen und potenziell riskante Operationen.

## Kernidee
- Ausführung nur in klar beschriebenen, begrenzten und beobachtbaren Umgebungen
- keine impliziten Nebenwirkungen außerhalb definierter Grenzen
- technische Isolation + policy-konforme Freigaben + Telemetrie

## Was sie umfasst
- Environment-Typen (`local_controlled`, `container_isolated`, `ephemeral_workspace`)
- Rechte-/Isolationsmodell (`read`, `write`, `network`, `exec`)
- Mount-/Path-Regeln und Secret Boundary
- Ressourcenlimits (`timeout`, `cpu`, `ram`, `disk`)
- Lifecycle (`create`, `prepare`, `reset`, `cleanup`)
- Integration mit Foundation 14/20/11

## Erwarteter Umfang
Groß

## Aufwand für Realisierung
Hoch

## Priorität
P1

## Risiken
- inkonsistente Isolationsregeln je Modus
- Secret-Leaks über unklare Mount-/Env-Regeln
- hohe Komplexität bei mehreren Environment-Typen

## Erfolgskriterium
Jede Ausführung ist einem Environment-Typ zugeordnet, policy-validiert, resource-begrenzt und vollständig nachvollziehbar.

## Konzept

### Problem
Ohne eigene Environment-Foundation laufen Tool- und Shell-Ausführungen in uneinheitlichen Kontexten. Das gefährdet Reproduzierbarkeit, Sicherheit und Diagnostik.

### Ziel
- Einheitlicher Vertrag für Ausführungsumgebungen.
- Klare Trennung von Environment-Definition (19) und Tool-Aufruf (20).
- Verlässliche Kopplung an Policy, Budget und Observability.

### Nicht-Ziele
- Kein Ersatz für Tool-Klassifikation oder Kommando-Parsing (Foundation 20).
- Keine Business-Logik pro Mode.

### Leitprinzipien
- Explicit isolation
- least privilege by default
- reproducible lifecycle
- observable execution boundaries

## Spezifikation

### 1. Environment-Typen
Mindestens:
- `local_controlled`
- `container_isolated`
- `ephemeral_workspace`

Jeder Typ hat ein versioniertes Capability-Profil.
Jede aktive Umgebung trägt zusätzlich einen `environment_fingerprint` (z. B. image/tooling/profile hash) für Reproduzierbarkeit.

### 2. Rechte-/Isolationsvertrag
Pflichtfelder:
- `read_scope`
- `write_scope`
- `network_scope`
- `exec_scope`
- `secret_scope`

Default: deny-by-default, explizite Freigaben pro Scope.

### 3. Ressourcenvertrag
Pro Run/Environment verpflichtend:
- `timeout_ms`
- `cpu_limit`
- `memory_limit_mb`
- `disk_limit_mb`
- optional `process_limit`

Limitverletzungen liefern strukturierte Diagnosen (`resource_limit_exceeded`).

### 3a. Tooling-Vertrag
- Verfügbare Toolchains sind pro Environment-Profil deklarativ gelistet.
- Fehlende Pflichttools führen zu `environment_tooling_incomplete`.

### 4. Mount- und Pfadvertrag
- Nur deklarierte Mounts.
- Schreibzugriff nur innerhalb validiertem `write_scope`.
- Symlink- und Traversal-Regeln müssen zentral geprüft werden.

### 5. Secret Boundary
- Secrets nur über deklarierte Secret-Provider.
- Keine unredigierte Secret-Ausgabe in stdout/stderr/logs.
- Secret-Zugriffe werden als Eventklasse separat protokolliert (ohne Secret-Werte).

### 6. Lifecycle-Vertrag
Pflichtphasen:
1. `create`
2. `prepare`
3. `active`
4. `reset` (optional)
5. `cleanup`

Fehlschläge in `cleanup` dürfen Diagnostik nicht verlieren.
Ein best-effort Cleanup ist immer verpflichtend, auch bei vorangehendem Fehler.

Environment-Statusraum (verbindlich):
- `created|prepared|active|blocked|failed|cleaned`

### 7. Policy-Integration
- Environment-Erzeugung/Auswahl ist policy-gesteuert.
- Nicht erlaubte Kombinationen (`network=on` in restricted mode) führen zu `blocked`.

### 8. Observability-Integration
Pflichtevents:
- `environment_created`
- `environment_prepared`
- `environment_blocked`
- `environment_reset`
- `environment_cleaned`

Mit `run_id`, `lineage_id` (falls vorhanden), `environment_id`, `environment_profile`.

## Design

### Zielstruktur (Vorschlag)
- `core/execution_environment_foundation.py`
  - Environment Manager
  - Isolation/Scope Validator
  - Lifecycle Controller
- `core/execution_environment_profiles.py`
  - deklarative Environment-Profile
- `core/execution_environment_security.py`
  - Secret/Scope Guardrails

### Datenmodelle (konzeptionell)
- `EnvironmentRequest`
  - requested_type, environment_contract_version, policy_context, required_scopes, resource_limits
- `EnvironmentProfile`
  - type, profile_version, allowed_scopes, defaults, hard_limits
- `EnvironmentHandle`
  - environment_id, profile_id, state, effective_scopes
- `EnvironmentResult`
  - status, diagnostics, handle_ref

### API-Skizze
- `create_environment(request, context) -> EnvironmentResult`
- `prepare_environment(handle, tool_requirements) -> EnvironmentResult`
- `validate_environment_scope(handle, action) -> ScopeDecision`
- `reset_environment(handle) -> EnvironmentResult`
- `cleanup_environment(handle) -> EnvironmentResult`

### Integrationspunkte
- Foundation 14: normative Scope-/Safety-Gates
- Foundation 20: Tool/Shell-Execution in validierten Environments
- Foundation 03: Environment-/Execution-Kosten
- Foundation 11: Lifecycle- und Block-Telemetrie
- Foundation 16: mutierende Ausführung nur in freigegebenem Environment

## Verbindlicher Vertragskern (jetzt)

Diese Punkte sind in Foundation 19 verpflichtend:
- deklarative Environment-Typen mit Scope-/Limit-Vertrag
- deny-by-default Rechte-/Isolationsmodell
- reproduzierbarer Lifecycle mit Cleanup
- Secret Boundary mit Redaction/No-Leak-Regeln
- policy- und observability-integrierte Ausführung

## Bewusst verschoben (spätere Detailphasen)

- differenzierte Sandbox-Backends pro Plattform
- erweiterte Cache-/Layer-Optimierung für Environments
- verteilte Execution-Pools

## Detaillierungsregel

Foundation 19 definiert Ausführungsgrenzen und Environment-Lifecycle.  
Toolklassifikation und Command-Semantik bleiben in Foundation 20.
