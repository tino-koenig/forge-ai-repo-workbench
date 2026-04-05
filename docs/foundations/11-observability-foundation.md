# Foundation 11: Observability Foundation

## Zweck
End-to-end Telemetrie über Stages, Aktionen, Budgets und LLM-Nutzung.

## Kernidee
- nicht nur LLM-Events, sondern komplette Pipeline-Events
- korrelierbare Run-IDs
- klarer Diagnosepfad für `budget_exhausted` und `no_progress`

## Was sie umfasst
- Eventmodell pro Stage/Action
- Budget-/Progress-/Decision-Telemetrie
- Korrelation zwischen Mode-Runs und Folge-Runs

## Beispiel
Trace zeigt: Iteration 2 `read` (+3 files, +720 tokens), kein Confidence-Gewinn, danach `no_progress`.

## Erwarteter Umfang
Mittel bis hoch

## Aufwand für Realisierung
Mittel bis hoch

## Priorität
P1

## Risiken
- zu viel Logging ohne klare Signalqualität
- PII/Secrets in unzureichend redigierten Events

## Erfolgskriterium
Jede Orchestrationsentscheidung ist mit messbaren Telemetriedaten begründet.

## Konzept

### Problem
Aktuell ist Observability stark LLM-zentriert. Für ein Qualitäts-Tool fehlen durchgängige, korrelierbare Pipeline-Signale über Stages, Actions, Budgets, Policies und Entscheidungen.

### Ziel
- End-to-end Telemetrie für den gesamten Ausführungspfad.
- Einheitliche Diagnosebasis für `no_progress`, `budget_exhausted`, `policy_blocked` und Fehlentscheidungen.
- Nachvollziehbarkeit über einzelne Runs und Mode-Übergänge hinweg.

### Nicht-Ziele
- Kein unkontrolliertes Verbose-Logging.
- Kein Speichern sensibler Inhalte ohne Redaktion.
- Keine Abhängigkeit von externen Observability-Plattformen als Pflicht.

### Leitprinzipien
- Signalqualität vor Eventmenge.
- Strukturierte Events vor Freitext.
- Privacy-by-default (Redaction/Minimierung).

## Spezifikation

### 1. Event-Ebenen
Die Foundation muss mindestens erfassen:
- Run-Events (`run_started`, `run_finished`)
- Stage-Events (`stage_started`, `stage_finished`, `stage_failed`)
- Action-Events (`action_planned`, `action_executed`, `action_noop`, `action_blocked`)
- Decision-Events (`decision_made`, `fallback_applied`)
- Budget-Events (`budget_snapshot`, `budget_exhausted`)
- Policy-Events (`policy_check`, `policy_blocked`)

Abgrenzung der Ebenen:
- `stage_*`: Lebenszyklus einer Stage
- `action_*`: operative Ausführungsebene
- `decision_*`: Entscheidungs- und Steuerungsebene
- `policy_*`: normative Prüf- und Gate-Ebene

### 2. Korrelation
Pflicht-Korrelationsfelder:
- `run_id`
- `session_id` (falls vorhanden)
- `iteration_id`
- `trace_id` (durchlaufend)
- `parent_run_id` (bei Inter-Mode-Handoff)

### 3. Minimales Event-Schema
Jedes Event enthält mindestens:
- `event_id`
- `timestamp`
- `event_type`
- `event_schema_version`
- `event_catalog_version`
- `capability`
- `profile`
- `source_component`
- `payload` (strukturiertes Objekt für domänenspezifische Eventdaten; Korrelation und Meta-Felder bleiben getrennt, keine freien Textblöcke als Primärträger)
- `redaction_status`

Für Orchestration-bezogene Events (`action_*`, `decision_*`, `budget_*`, `policy_*`) sind zusätzlich verpflichtend:
- `iteration_id`
- `trace_id`
- `decision_source` (falls vorhanden)
- `done_reason` (aktueller Stand, falls vorhanden)
- `policy_version`
- `settings_snapshot_id`
- `action_input_hash` (falls action-bezogen)
- `state_hash_before` und `state_hash_after` (falls zustandsverändernd)

### 4. Qualitätsmetriken
Pflichtmetriken pro Run:
- Dauer gesamt / pro Stage
- Action-Verteilung (`ok/noop/blocked/error`)
- Budgetverbrauch (before/after)
- Progress-Entwicklung pro Iteration
- Decision-Sources (`deterministic|llm|fallback`)

### 5. Privacy und Redaction
Pflichtregeln:
- keine unredigierten Secrets in Logs
- Prompt-/Antwortinhalte nur nach klarer Policy und mit Redaktionsstufe
- Event enthält `redaction_version`
- `redaction_status` folgt einem definierten Statusraum (z. B. `not_needed|applied|blocked|failed`)

### 6. Sampling und Level
Unterstützte Levels:
- `minimal` (produktiver Default)
- `standard`
- `debug`

Sampling/Detailgrad muss runtime-konfigurierbar sein, ohne Schemabruch.

Sampling oder reduzierte Detailgrade dürfen Pflicht-Korrelationsfelder, Pflicht-Diagnosefelder und deterministisch erforderliche Ursachenketten nicht entfernen. Reduziert werden dürfen nur Zusatzdetails.

### 7. Diagnosefähigkeit
Der Trace muss ausreichend sein, um folgende Fragen deterministisch zu beantworten:
- Warum wurde gestoppt?
- Warum wurde replanned?
- Warum wurde eine Action blockiert?
- Welche Budgets waren entscheidend?

Diese Antworten müssen aus korrelierten strukturierten Events ableitbar sein, nicht aus Freitextinterpretation.

### 8. Verfügbarkeit und Retention
- Korrelierbare Telemetrie muss für einen definierten Analysezeitraum lokal verfügbar bleiben.
- Rotation und Retention dürfen den verpflichtenden Diagnose- und Korrelationskern innerhalb dieses Zeitraums nicht zerstören.

### 9. Event-Governance
- Jeder Eventtyp gehört zu einem versionierten Eventkatalog.
- Neue Eventfelder sind additiv zu entwickeln; Breaking-Änderungen erfordern Katalog-/Schemaanhebung.
- Deprecated Eventtypen bleiben für einen definierten Übergangszeitraum auswertbar.

## Design

### Zielstruktur (Vorschlag)
- `core/observability_foundation.py`
  - Event-API und Korrelation
  - Level-/Sampling-Policy
- `core/observability_redaction.py`
  - Redaction-Pipeline für strukturierte Felder
- `core/observability_store.py`
  - lokale Speicherung, Rotation, Retention

### Datenmodelle (konzeptionell)
- `ObsEvent`
  - event_id, timestamp, event_type, run_id, trace_id, payload, redaction_status
- `ObsContext`
  - capability, profile, session_id, parent_run_id
- `ObsRunSummary`
  - aus Events abgeleitete Summary: duration, decision_breakdown, budget_summary, outcome

### API-Skizze
- `obs_start_run(context) -> run_id`
- `obs_emit(event_type, payload, context) -> None`
- `obs_emit_budget(snapshot, context) -> None`
- `obs_finish_run(outcome, context) -> ObsRunSummary`
- `obs_redact(event) -> event`

### Integrationsplan
1. Eventmodell und Korrelation zentral einführen.
2. Orchestrator (02) an Observability anbinden.
3. Budget Foundation (03) Snapshots standardisiert ausgeben.
4. Output Contract Foundation (10) nutzt Run-Summary für `provenance/diagnostics`.
5. Done-Reason-Semantik gemäß Foundation 02 unverändert in Events und Contract übernehmen.

### Migrationsstrategie
- Phase 1: bestehende LLM-Observability parallel weiterführen.
- Phase 2: Pipeline-Events ergänzen und korrelieren.
- Phase 3: mode-lokale Ad-hoc-Logs reduzieren, zentrale Events als Quelle.

### Risiken im Design
- zu hohe Eventdichte
- inkonsistente Eventtypen ohne Governance
- Redaction-Lücken bei neuen Feldern

### Gegenmaßnahmen
- Event-Typ-Katalog zentral versionieren
- additive Weiterentwicklung bevorzugen; bestehende Auswertungen dürfen nicht still brechen
- feste Review-Regel für neue Eventfelder
- Redaction-Tests als Quality Gate

## Verbindlicher Vertragskern (jetzt)

Diese Punkte sind in Foundation 11 verpflichtend:
- einheitliches Event-Schema mit Korrelation
- Pflichtmetriken pro Run/Iteration
- zentrale Redaction-Regeln mit Versionsfeld
- deterministische Diagnose für Stop-/Block-/Replan-Entscheidungen
- Sampling/Level dürfen den verpflichtenden Diagnose- und Korrelationskern nicht ausdünnen
- korrelierbare Telemetrie muss für einen definierten Analysezeitraum lokal verfügbar bleiben

## Bewusst verschoben (spätere Detailphasen)

Diese Punkte werden nachgelagert konkretisiert:
- Export in externe Observability-Systeme
- erweiterte Anomalie-Erkennung und Alerting
- UI-optimierte Timeline-/Graph-Darstellungen

## Detaillierungsregel

Foundation 11 definiert den stabilen Telemetrievertrag.  
Provider-spezifische Log-Ausleitung und Analysefeatures werden separat ausgearbeitet.

## V2-Erweiterungen (Proposal-/Execution-Telemetrie)

### V2-Konzept

#### Problem
v1 liefert starke Run-/Iteration-Telemetrie, aber die Kette zwischen Analyse, Proposal und Execution ist noch nicht als durchgehende Lineage formalisiert. Dadurch fehlen:
- eindeutige Herkunft von Änderungsvorschlägen
- nachvollziehbare Gründe für Proposal-Verwerfung/Block
- auditfähige Zuordnung, warum und auf welcher Basis eine Execution gestartet wurde

#### Zielbild
Observability bildet in v2 eine zusammenhängende Entscheidungs- und Ausführungskette ab:
- Analyse-Lineage
- Proposal-Lineage
- Execution-Lineage

Alle drei sind über stabile Korrelation und Kausalreferenzen verknüpft.

#### Leitprinzipien (V2)
- kausal verknüpft statt nur zeitlich sortiert
- entscheidungsrelevante Gründe strukturiert erfassen
- keine Execution ohne nachvollziehbaren Ursprung
- Redaction und Auditierbarkeit bleiben gleichrangig

### V2-Spezifikation (Vertragskern)

#### 1. Lineage-Kern (verbindlich)
Zusätzliche Pflichtfelder für proposal-/execution-nahe Events:
- `lineage_id` (durchgehend)
- `analysis_run_id` (falls vorhanden)
- `proposal_run_id` (falls vorhanden)
- `execution_run_id` (falls vorhanden)
- `causal_event_id` (referenzierte Ursache)

Regel:
- Events ohne gültige Lineage-Zuordnung sind in v2 für proposal-/execution-kritische Pfade unzulässig.

#### 2. V2-Eventtypen (verbindlich)
Zusätzlicher Eventkatalog:
- `proposal_started`
- `proposal_completed`
- `proposal_rejected`
- `proposal_blocked`
- `execution_requested`
- `execution_approved`
- `execution_blocked`
- `execution_applied`
- `execution_failed`
- `execution_reverted` (optional)

Jeder dieser Typen hat ein stabiles Payload-Schema und Versionierung.

#### 3. Decision-Telemetrie Proposal (verbindlich)
Proposal-bezogene Events müssen enthalten:
- `proposal_status` (`proposed|partial|blocked|uncertain`)
- `proposal_reason_codes[]`
- `proposal_confidence`
- `proposal_scope_summary`
- `requires_human_review`

Wenn Proposal verworfen/geblockt:
- `rejection_or_block_reason_codes[]`
- `missing_prerequisites[]` (z. B. fehlende Targets/Coverage/Policy)

#### 4. Decision-Telemetrie Execution (verbindlich)
Execution-bezogene Events müssen enthalten:
- `execution_request_origin` (`proposal|explicit_user_request|system_recovery`)
- `execution_ref` (wenn ausgeführt)
- `policy_decision`
- `write_scope_status`
- `approval_status`

Bei Block/Fail:
- `execution_block_or_fail_codes[]`
- `rollback_recommendation` (wenn relevant)

#### 5. Kausalitätsregeln (verbindlich)
`execution_requested` muss kausal referenzieren:
- entweder ein Proposal-Event (`proposal_completed|proposal_status=proposed`)
- oder einen expliziten Nutzerauftrag

Fehlt diese Kausalbasis:
- Eventdiagnose `execution_without_causal_basis`
- Execution-Pfad gilt als observability-invalid

#### 6. Cross-Run-Konsistenz (verbindlich)
Für zusammenhängende Ketten:
- `lineage_id` bleibt stabil
- `parent_run_id` und `causal_event_id` dürfen nicht widersprüchlich sein
- Statusübergänge müssen plausibel sein (z. B. kein `execution_applied` ohne vorheriges `execution_requested`)

Verstöße werden als `lineage_consistency_violation` diagnostiziert.

#### 7. Redaction-/Audit-Regeln V2 (verbindlich)
Proposal-/Execution-Events dürfen keine sensitiven Inhalte im Klartext enthalten, wenn Policy das verbietet.

Pflichtfelder trotz Redaction:
- Ursachen-/Statuscodes
- Korrelation
- Outcome-Klassifikation

Redaction darf die Kausalbeweiskette nicht zerstören.

#### 8. Run-Summary-V2 (verbindlich)
Run-/Lineage-Summary muss zusätzlich ausweisbar machen:
- `lineage_outcome` (`analysis_only|proposal_only|execution_completed|execution_blocked|failed`)
- `proposal_to_execution_latency_ms`
- `decision_source_distribution`
- `policy_block_points[]`

### V2-Design (Integrationspunkte)

#### Zielstruktur (Erweiterung)
- `core/observability_foundation.py`
  - `LineageTracker`
  - `CausalityValidator`
  - `ProposalExecutionEventEmitter`
- `core/observability_lineage.py`
  - Lineage-Modelle und Konsistenzregeln
- `core/observability_audit.py`
  - Audit-Sichten für Proposal->Execution-Ketten

#### Modell-Erweiterungen
- `ObsEvent`
  - ergänzt um `lineage_id`, `causal_event_id`, `event_schema_version`
- `ObsContext`
  - ergänzt um `analysis_run_id`, `proposal_run_id`, `execution_run_id`
- `ObsRunSummary`
  - ergänzt um `lineage_outcome`, `proposal_execution_linkage`, `block_points`

#### API-Erweiterungen
- `obs_link_lineage(context, lineage_id) -> ObsContext`
- `obs_emit_proposal_event(event_type, payload, context) -> None`
- `obs_emit_execution_event(event_type, payload, context) -> None`
- `validate_lineage_consistency(events) -> list[ObsDiagnostic]`
- `build_lineage_summary(lineage_id) -> ObsLineageSummary`

#### Integrationspunkte zu anderen Foundations
- Foundation 01:
  - liefert Phasenwechsel als Events mit Lineage-Bezug
- Foundation 02:
  - liefert Reifegrad- und Decision-Signale für Proposal/Execution-Events
- Foundation 10:
  - nutzt Lineage-Summary in `diagnostics`/`provenance`
- Foundation 13:
  - Proposal-Status/Artefakte werden observability-seitig referenziert
- Foundation 16:
  - Execution-Nachweise und Blockgründe werden als Kernereignisse erfasst
- Foundation 17:
  - Retention/Lifecycle-Regeln für Telemetrieartefakte

#### Migrationsansatz (V2)
1. Lineage-Felder diagnostisch ergänzen, ohne harte Validierung.
2. Proposal-/Execution-Eventtypen aktivieren.
3. Kausalitätsvalidierung für execution-nahe Flows verpflichtend machen.
4. Run-Summaries um Lineage-Outcomes erweitern.
5. Alte, unverkettete Execution-Logs abbauen.

#### Verbindliche V2-Regel
Jeder Execution-Run muss über `lineage_id` und `causal_event_id` auf ein Proposal oder einen expliziten Nutzerauftrag rückverfolgbar sein; ohne diese Kausalbasis ist der Execution-Pfad nicht gültig.
