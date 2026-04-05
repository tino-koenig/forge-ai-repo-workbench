# Foundation 06: LLM Tasks Foundation

## Zweck
Task-spezifische LLM-Funktionen als klare APIs (ohne Providerdetails in Modes).

## Kernidee
- getrennt von der Provider-Basis
- pro Task klarer Input/Output-Vertrag
- deterministische Guardrails für sensible Tasks

## Was sie umfasst
- Query Planner
- Query Action Decision
- Summary Refinement
- später: Review Prioritization, Fix Proposal Scoring

## Beispiel
`plan_query_terms(question)` liefert strukturierte `lead_terms/support_terms/search_terms`.

## Erwarteter Umfang
Mittel

## Aufwand für Realisierung
Mittel

## Priorität
P1

## Risiken
- zu enge Kopplung an einzelne Modes
- unklare Kontrakte zwischen task output und deterministic core

## Erfolgskriterium
Modes rufen LLM-Task-APIs, aber halten keine Prompt-/JSON-Parser-Logik mehr lokal.

## Konzept

### Problem
LLM-Aufgaben (Planner, Orchestrator-Entscheidung, Summary-Refinement) sind oft mit Prompt-Details, Parsing und Mode-Logik vermischt. Das erschwert Austauschbarkeit, Tests und Vertragsstabilität.

### Ziel
- Task-spezifische LLM-Funktionen als stabile, providerunabhängige APIs.
- Klare Trennung:
  - Foundation 05: Provider/Completion/Usage/Cost
  - Foundation 06: Task-Verträge, Prompt-Bindung, Parsing, Guardrails
- Modes konsumieren nur Task-Outputs.

### Nicht-Ziele
- Keine freie Prompt-Bastelschicht pro Mode.
- Keine Entscheidungshoheit des LLM über Policy-/Budget-Grenzen.
- Kein Ersatz des deterministischen Kerns.

### Leitprinzipien
- Task-Vertrag vor Prompt-Text.
- Deterministische Guardrails vor Freiform-Ausgabe.
- LLM-Ergebnis ist assistiv, nicht autoritativ für harte Systemgrenzen.

## Spezifikation

### 1. Task-Katalog (Kern)
Mindestens:
- `query_planner`
- `query_action_decision`
- `summary_refinement`

Erweiterbar:
- `review_prioritization`
- `fix_proposal_scoring`

### 2. Task-Vertrag (einheitlich)
Jeder Task hat:
- `task_name`
- `input_schema`
- `output_schema`
- `validation_rules`
- `fallback_policy`
- `usage_contract` (welche Usage/Cost/Provider-Metadaten im Task-Result sichtbar bleiben)
- `task_contract_version`

### 3. Input/Output-Regeln
- Inputs sind streng typisiert und mode-neutral.
- `context` ist nur für klar definierte, task-neutrale Hilfsinformationen erlaubt; freie Mode-Objekte oder implizite Fachzustände sind unzulässig.
- Outputs sind strikt strukturiert (kein freies Fließtext-Protokoll für Kernfelder).
- Parsing-Fehler führen zu deterministischem Fallback.
- Prompt-Templates und Prompt-Bindung liegen in Foundation 06; Provider (Foundation 05) erhält nur vorbereitete Prompt-/Message-Payloads.

### 4. Guardrails (verbindlich)
- LLM darf keine Budget-/Policy-Entscheidung überschreiben.
- `query_action_decision` darf nur Aktionen aus dem erlaubten Action-Set liefern.
- `summary_refinement` darf deterministische Kernclaims nicht ändern.
- Guardrails validieren gegen deterministische Inputs, erlaubte Constraints und bekannte Kernclaims; nicht gegen freie LLM-Selbstaussagen.

### 5. Decision-Source und Trace
Jeder Task-Output enthält:
- `source`: `llm|fallback`
- `status`: `success|fallback|validation_failed|guardrail_failed|call_failed`
- `attempted`: ob ein LLM-Task-Lauf tatsächlich versucht wurde
- `used`: ob das LLM-Ergebnis nach Validation/Guardrails tatsächlich übernommen wurde
- `fallback_reason` (falls zutreffend)
- `latency_ms`
- `model/provider` (wenn genutzt)

Diese Felder müssen mit Foundation 11 korrelierbar sein.

### 6. Versionierung
- Jeder Task hat eine eigene `task_contract_version`.
- Breaking Changes an Output-Feldern sind nur über Versionserhöhung zulässig.
- Task-Versionen sind unabhängig von der Provider-Implementierungsversion.

### 7. Fehler- und Fallback-Semantik
Pflichtfälle:
- Prompt-/Template fehlt
- Completion-Fehler
- Schema-Validation fehlgeschlagen
- Guardrail-Verletzung

Verhalten:
- deterministischer Fallback
- strukturierte Diagnose im Output
- Fallbacks werden aus dem vollständigen Task-Request und klaren Fallback-Regeln abgeleitet, nicht aus losem Kontext allein.

## Design

### Zielstruktur (Vorschlag)
- `core/llm_tasks_foundation.py`
  - Task-Dispatcher
  - gemeinsame Task-Runner
- `core/llm_task_specs.py`
  - Input/Output-Schemas
  - Guardrail-Regeln
- `core/llm_task_prompts.py`
  - Prompt-Template-Bindung pro Task
- `core/llm_task_parsers.py`
  - robuste Parser + Schema-Validation

### Datenmodelle (konzeptionell)
- `LLMTaskRequest`
  - task_name, payload, context, allowed_actions(optional)
  - `context` nur task-neutral und schemagebunden
- `LLMTaskResult`
  - task_name, output, source, status, attempted, used, fallback_reason, usage, diagnostics
- `LLMTaskDiagnostic`
  - code, message, severity, phase (`prompt|call|parse|validate|guardrail`)

### API-Skizze
- `run_llm_task(request: LLMTaskRequest, settings) -> LLMTaskResult`
- `validate_task_output(task_name, output) -> list[LLMTaskDiagnostic]`
- `apply_task_guardrails(task_name, output, context) -> GuardrailResult`
- `fallback_task_result(request: LLMTaskRequest, reason) -> LLMTaskResult`

### Integrationsregeln zu anderen Foundations
- Foundation 05 liefert Completion/Usage/Cost.
- Foundation 02 konsumiert `query_action_decision` nur über validierten Task-Output.
- Foundation 10 übernimmt Task-Usage/Diagnostics in `sections.llm_usage` und `sections.diagnostics`.
- Foundation 11 erhält Task-Events (`task_attempted`, `task_fallback`, `task_completed`).
- Mapping-Regel: `ProviderResult.usage/cost/provider_meta` wird unverändert (oder mit klarer Kennzeichnung) in `LLMTaskResult.usage` übernommen; die Herkunft dieser Werte bleibt sichtbar und darf task-spezifisch nicht umgedeutet werden.
- Zu Foundation 08: Task-Outputs dürfen nur als explizite, getrennte Ranking-Signale eingespeist werden (`llm_task_signal_score`) und dürfen deterministische Kernkomponenten nicht überschreiben.

### Integrationsplan
1. `query_planner` in Foundation 06 heben.
2. `query_action_decision` migrieren.
3. `summary_refinement` migrieren.
4. Mode-lokale Prompt-/Parse-Helfer entfernen.

### Migrationsstrategie
- Phase 1: Adapter auf bestehende Funktionen mit identischem Output.
- Phase 2: Schema-/Guardrail-Zwang aktivieren.
- Phase 3: alte task-spezifische Hilfsfunktionen in Modes entfernen.

### Risiken im Design
- Task-Schemas zu eng oder zu lose
- verdeckte Kopplung an einzelne Mode-Begriffe
- Guardrails unvollständig

### Gegenmaßnahmen
- task-neutrale Kernschemas
- strikte Output-Validation pro Task
- Quality Gates für Fallback-Raten und Guardrail-Verletzungen

## Verbindlicher Vertragskern (jetzt)

Diese Punkte sind in Foundation 06 verpflichtend:
- stabile, versionierte Task-Verträge
- validierte strukturierte Outputs
- deterministische Fallbacks bei Fehlern/Verletzungen
- klare Guardrails gegen Überschreiben von Policy/Budget/Kernclaims
- vollständige Usage/Diagnostics-Felder für Contract und Observability, mit sichtbarer Herkunft und klarem Task-Status

## Bewusst verschoben (spätere Detailphasen)

Diese Punkte werden nachgelagert konkretisiert:
- fortgeschrittene Multi-Task-Ketten mit gemeinsamer Kontextoptimierung
- automatische Prompt-Experimente/A-B-Varianten
- modelladaptive Routing-Strategien je Task

## Detaillierungsregel

Foundation 06 definiert Task-Verträge, Guardrails und Fallback-Semantik.  
Prompt-Feinheiten und Task-spezifische Tuning-Parameter werden in Feature-Dokumenten geschärft.

## V2-Erweiterungen (Proposal-/Impact-/Patch-Tasks)

### V2-Konzept

#### Problem
Der bestehende Task-Katalog deckt primär Analyse-/Formulierungsaufgaben ab. Für v2 fehlen klar standardisierte Planungsaufgaben für Änderungsvorschläge, Wirkungseinschätzung und Umsetzungsplanung. Ohne diese Verträge droht:
- inkonsistente Proposal-Ausgaben zwischen Modes
- Vermischung von Empfehlungs- und Ausführungslogik
- unklare Übergänge zu Policy/Mutation

#### Zielbild
Foundation 06 erweitert den Task-Katalog um eine eigenständige Proposal-/Planning-Familie:
- `change_proposal`
- `impact_estimation`
- `alternative_generation`
- `patch_planning`

Alle neuen Tasks bleiben:
- strikt schema- und guardrail-basiert
- nicht-mutierend
- reproduzierbar nachvollziehbar über Diagnose- und Trace-Felder

#### Leitprinzipien (V2)
- Planung ist ein eigener Vertragsraum zwischen Analyse und Execution
- Outputs sind strukturierte Artefakte, keine freien Narrative
- Guardrails schützen gegen implizite Mutation
- Task-Kombinationen sind orchestrierbar, aber einzeln versioniert

### V2-Spezifikation (Vertragskern)

#### 1. Erweiterter Task-Katalog (verbindlich)
Zusätzliche Pflicht-Tasks:
- `change_proposal`
- `impact_estimation`
- `alternative_generation`
- `patch_planning`

Jeder Task hat:
- eigenes `input_schema`
- eigenes `output_schema`
- eigenes `task_contract_version`
- task-spezifische Guardrails

#### 2. Task-Zwecke und Minimaloutputs (verbindlich)
`change_proposal` mindestens:
- `proposal_status` (`proposed|partial|blocked|uncertain`)
- `change_intents[]`
- `affected_targets[]`
- `proposal_steps[]`

`impact_estimation` mindestens:
- `impact_scope`
- `risk_items[]`
- `dependency_touchpoints[]`
- `test_implications[]`

`alternative_generation` mindestens:
- `alternatives[]` (>=1 bei `status=success`)
- `tradeoff_summary`
- `recommended_option`

`patch_planning` mindestens:
- `planned_edits[]` (datei-/target-bezogen, noch ohne Mutation)
- `preconditions[]`
- `verification_plan[]`
- `execution_blockers[]`

#### 3. Proposal-Statusmodell (verbindlich)
Zusätzlich zum generischen Task-Status führt die Proposal-Familie:
- `proposal_status`: `proposed|partial|blocked|uncertain`
- `proposal_confidence`
- `requires_human_review` (bool)

Regel:
- `proposal_status=proposed` nur bei erfüllten Mindestschemata und ohne harte Guardrail-Verletzung.

#### 4. Input-Kontextgrenzen (verbindlich)
Neue Tasks dürfen nur kontrollierten Kontext erhalten:
- evidenzbasierte Inputs (Targets, Evidence, Constraints, Settings)
- keine direkten Schreib-Handles oder ungebundene Dateimutationstools
- klare Feldgrenzen für erlaubte Änderungsintentionen

`proposal.allowed_change_intents` (Foundation 04) muss in validierter Form in relevante Tasks einfließen.

#### 5. Guardrails für Nicht-Mutation (verbindlich)
Die neuen Tasks dürfen nicht:
- Dateiänderungen ausführen
- direkte Patch-Anwendung triggern
- Mutation außerhalb von Foundation 16 initiieren

Pflichtdiagnose bei Verstoß:
- `guardrail_mutation_attempt_blocked`
- Rückgabe als `status=guardrail_failed` + deterministischer Fallback

#### 6. Cross-Task-Konsistenzregeln (verbindlich)
Wenn mehrere Planning-Tasks kombiniert werden:
- `affected_targets` müssen konsistent referenzierbar sein
- Risiken/Annahmen dürfen nicht stillschweigend widersprüchlich bleiben
- Widersprüche werden als `cross_task_conflict` diagnostiziert

`patch_planning` darf nur auf einer bestehenden Proposal-Basis aufbauen oder muss explizit `proposal_basis_missing` melden.

#### 7. Trace-/Usage-Vertrag V2 (verbindlich)
Jeder neue Task muss zusätzlich liefern:
- `task_family=proposal_planning`
- `proposal_status` (wo anwendbar)
- `input_artifact_refs[]`
- `output_artifact_refs[]`
- `source`/`status`/`attempted`/`used` nach v1

Usage/Cost-Herkunft bleibt aus Foundation 05 erhalten und darf nicht taskseitig umgedeutet werden.

#### 8. Fallback-Semantik V2 (verbindlich)
Bei Fehlern/Guardrail/Schemaproblemen:
- deterministischer Fallback je Task
- Fallback muss mindestens ein minimales, maschinenlesbares Ergebnis liefern (`blocked|partial|uncertain`)
- kein leeres „best effort“-Freitextresultat ohne Vertragsfelder

### V2-Design (Integrationspunkte)

#### Zielstruktur (Erweiterung)
- `core/llm_tasks_foundation.py`
  - `ProposalTaskRunner`
  - `TaskFamilyRouter`
- `core/llm_task_specs.py`
  - V2-Schemas für Proposal-/Planning-Tasks
- `core/llm_task_guardrails.py`
  - Mutation- und Cross-Task-Guardrails
- `core/llm_task_conflicts.py`
  - Konsistenzprüfung zwischen Task-Artefakten

#### Modell-Erweiterungen
- `LLMTaskRequest`
  - ergänzt um `task_family`, `artifact_refs`, `allowed_change_intents`
- `LLMTaskResult`
  - ergänzt um `proposal_status`, `proposal_confidence`, `requires_human_review`, `artifact_refs`
- `LLMTaskDiagnostic`
  - ergänzt um `conflict_scope`, `artifact_ref`, `guardrail_rule_id`

#### API-Erweiterungen
- `run_proposal_task(request, settings) -> LLMTaskResult`
- `validate_proposal_task_output(task_name, output) -> list[LLMTaskDiagnostic]`
- `check_cross_task_consistency(task_results) -> list[LLMTaskDiagnostic]`
- `build_proposal_fallback(task_name, reason, minimal_context) -> LLMTaskResult`

#### Integrationspunkte zu anderen Foundations
- Foundation 02:
  - konsumiert Proposal-Task-Ergebnisse für `proposal_ready`
- Foundation 04:
  - liefert `proposal.*`- und `allowed_change_intents`-Settings
- Foundation 05:
  - bleibt Provider-/Profil-/Usage-Unterbau
- Foundation 10:
  - Proposal-/Impact-/Alternativen-/Plan-Sections aus Task-Artefakten
- Foundation 11:
  - Task-Events inkl. Proposal-Status und Guardrail-Failures
- Foundation 13:
  - nutzt Task-Artefakte als Input für formale Änderungsvorschläge
- Foundation 16:
  - erhält nur explizit übergebene Planartefakte; keine direkte Task-Mutation

#### Migrationsansatz (V2)
1. Neue Task-Schemas und Guardrails zunächst ohne Aktivierung in Modes einführen.
2. `change_proposal` als ersten Referenztask anbinden.
3. `impact_estimation` und `alternative_generation` integrieren.
4. `patch_planning` nur mit aktivem Mutation-Guardrail freischalten.
5. Alte mode-lokale Planungs-Prompts schrittweise entfernen.

#### Verbindliche V2-Regel
Kein LLM-Task aus Foundation 06 darf direkt zu Dateiänderungen führen; jede mögliche Umsetzung erfordert eine explizite, nachvollziehbare Übergabe an Foundation 16.
