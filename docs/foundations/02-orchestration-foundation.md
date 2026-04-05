# Foundation 02: Orchestration Foundation

## Zweck
Zentrale Steuerung iterativer Task-Abläufe inklusive Stop-/Continue-Entscheidungen.

## Kernidee
- Tasks werden geplant, ausgeführt, bewertet
- Orchestrator kann dynamisch neue Tasks anfügen oder stoppen
- gleiche Done-Reasons und gleiche Iterations-Traces in allen Modes

## Was sie umfasst
- Action-/Task-Modell
- Decision-Layer (deterministisch + optional LLM-gestützt)
- Iterations-State
- Stop-Controller (`sufficient_evidence`, `no_progress`, `budget_exhausted`, `policy_blocked`)

## Beispiel
`query`: Qualität zu niedrig -> `replan_terms` -> erneute Suche -> `read` -> `rank`  
`fix/review-loop`: `fix` -> `review` meldet Regression -> zurück zu `fix` mit Findings-Constraints

## Erwarteter Umfang
Groß

## Aufwand für Realisierung
Hoch

## Priorität
P0/P1 (Kernsystem)

## Risiken
- Endlosschleifen ohne saubere Termination-Policy
- schwer debuggbar ohne klaren Trace je Iteration

## Erfolgskriterium
Task-Entscheidungen sind reproduzierbar, budgetiert und vollständig nachvollziehbar.

## Konzept

### Problem
Mode-spezifische Schleifen und Entscheidungslogik führen zu inkonsistentem Verhalten bei Continue/Stop, Progress-Bewertung und Trace-Ausgabe. Dadurch wird Diagnose schwierig und Weiterentwicklung teuer.

### Ziel
- Ein zentraler Orchestrator steuert iterative Abläufe in allen relevanten Modes.
- Entscheidungen basieren auf expliziten Inputs: Qualität, Budget, Policy, Fortschritt.
- Jede Iteration erzeugt einen konsistenten, auditierbaren Trace.

### Nicht-Ziele
- Keine vollständige autonome Agentenschicht.
- Keine Verdeckung mode-spezifischer Fachlogik.
- Keine hardcodierten Sonderfälle pro Einzelproblem.

### Leitprinzipien
- Deterministischer Kern mit optionalem LLM-Decision-Layer.
- Stop-Regeln sind explizit und vorhersagbar.
- Orchestration ist sichtbar (nicht „black box“).

## Spezifikation

### 1. Orchestration-Scope
Die Foundation muss mindestens folgende Abläufe unterstützen:
- Intra-Mode Iterationen (`query`: search/read/rank/replan/stop)
- Inter-Mode Übergänge (`fix -> review -> fix`) als optionaler Übergabemechanismus

### 2. Action-Modell
Jede Action hat:
- `name`
- `inputs`
- `preconditions`
- `estimated_cost` (hook zur Budget Foundation)
- `result` (state delta + evidenz delta + diagnostics)

### 3. Decision-Modell
Jede Iteration enthält genau eine Primärentscheidung:
- `decision`: `continue | stop`
- `next_action`: action-name oder `None`
- `reason`
- `confidence` (`low|medium|high`) als abgeleiteter Bewertungswert, nicht als freie Schätzung

Zusätzlich verpflichtend:
- `control_signal`: `none | replan | recover | handoff | block`

Optional:
- `alternative_actions` (nur für Trace, nicht automatisch ausgeführt)

### 4. Done-Reasons (verbindlich)
Mindestens:
- `sufficient_evidence`
- `no_progress`
- `budget_exhausted`
- `policy_blocked`
- `error`

Prioritätsregel bei konkurrierenden Gründen (höchste zuerst):
1. `error`
2. `policy_blocked`
3. `budget_exhausted`
4. `no_progress`
5. `sufficient_evidence`

### 5. Progress-Regeln
Progress-Bewertung muss auf messbaren Größen basieren:
- evidence gain
- confidence gain
- top-candidate change
- score gain

Die Bewertung erfolgt über eine zentrale, deterministische Progress-Policy.
`no_progress` darf nicht aus einem beliebigen Einzelindikator abgeleitet werden, sondern aus einer konsistenten Aggregation dieser Signale.

### 6. Policy-Integration
Vor Action-Ausführung muss ein zentraler Policy-Check stattfinden.
Bei Verstoß:
- Action nicht ausführen
- Iteration mit `policy_blocked` dokumentieren

### 7. Trace-Vertrag
Jede Iteration muss mindestens enthalten:
- iteration id
- trace id
- decision + reason + confidence
- action status (`ok|noop|blocked|error`)
- budget before/after
- progress score/components
- done_reason (aktueller Stand)
- `run_id`
- `causal_parent_id` (optional, v. a. für Handoffs/Recovery)

### 8. Determinismus und Fallback
- Wenn LLM-Entscheidung fehlt/ungültig ist, greift deterministische Fallback-Entscheidung.
- Fallback muss im Trace explizit markiert werden.

### 9. Objective- und Acceptance-Gates (verbindlich)
Jeder orchestrierte Run braucht ein explizites `objective` mit messbaren Gates.

Pflichtfelder:
- `objective.id`
- `objective.type` (z. B. `locate_definition`, `explain_dependencies`, `apply_fix`)
- `acceptance_gates` (Liste aus messbaren Bedingungen)
- `hard_fail_gates` (sofortiger Abbruch bei Verletzung)

Beispiele:
- `query/locate_definition`: mindestens ein symbolverankerter Treffer im Top-N.
- `review`: keine offenen Findings `severity=high` nach finalem Check.
- `fix`: alle zugeordneten Regression-Gates grün.

### 10. Formale Zustandsmaschine (verbindlich)
Der Orchestrator arbeitet als finite state machine mit folgenden Kernzuständen:
- `initialized`
- `running`
- `blocked`
- `terminal_success`
- `terminal_failure`

Erlaubte Übergänge:
- `initialized -> running`
- `running -> running`
- `running -> blocked`
- `running -> terminal_success`
- `running -> terminal_failure`
- `blocked -> running` (nur nach deterministischer Recovery/Fallback)
- `blocked -> terminal_failure`

Nicht erlaubte Übergänge sind als Policy-Verstoß zu protokollieren.

`blocked` ist ausschließlich für prinzipiell recoverable Situationen vorgesehen. Nicht recoverable Budget-/Policy-Verstöße führen direkt zu `terminal_failure`.

### 11. Replan-Vertrag (verbindlich)
Replanning (Anpassung/Nachladen von Tasks) ist erlaubt, aber streng geregelt.

Pflichtregeln:
- Replan nur bei definierten Triggern:
  - `low_confidence`
  - `no_progress_streak`
  - `objective_gate_miss`
  - `new_evidence_conflict`
- Jede Replan-Entscheidung muss enthalten:
  - `trigger`
  - `plan_delta` (added/removed/reordered actions)
  - `expected_gain`
- Anti-Loop:
  - gleiche Action mit identischem oder praktisch gleichwertigem Input darf maximal `N`-mal laufen
  - Replan-Budget (`max_replans`) ist verpflichtend

### 12. Failure- und Recovery-Vertrag (verbindlich)
Für Action-Fehler muss es ein standardisiertes Verhalten geben.

Pflichtkategorien:
- `transient_error` (retry-fähig)
- `policy_error` (nicht retry-fähig)
- `budget_error` (nicht retry-fähig)
- `logic_error` (mode- oder code-seitig)

Pflichtverhalten:
- `transient_error`: begrenzter Retry mit Backoff/Variante
- sonst: deterministischer Fallback oder terminaler Abbruch
- jede Recovery-Aktion muss im Trace als `recovery_step` markiert werden

### 13. Inter-Mode-Handoff-Vertrag
Für orchestrierte Übergänge zwischen Modes (z. B. `fix -> review -> fix`) ist ein formales Handoff nötig.

Pflichtfelder:
- `handoff_id`
- `source_mode`, `target_mode`
- `reason`
- `constraints` (z. B. „keine API-Änderung“, „nur Datei X“)
- `evidence_bundle` (relevante Findings/Evidenz)
- `acceptance_gates` für den Zielmode
- `max_loop_count` für zyklische Übergänge

Ein Übergang ohne vollständigen Handoff ist unzulässig und als `policy_blocked` zu beenden.

Der Ziel-Mode darf Handoff-Daten ergänzen, aber nicht stillschweigend abschwächen oder überschreiben. Abweichungen vom Handoff-Vertrag sind trace- und policy-relevant.

### 14. Forensikfester Trace-Vertrag
Zusätzlich zu bestehenden Feldern muss jede Iteration enthalten:
- `action_input_hash`
- `state_hash_before`
- `state_hash_after`
- `settings_snapshot_id`
- `policy_version`
- `decision_source` (`deterministic|llm|fallback`)
- `actual_cost` (nach Ausführung)

## Design

### Zielstruktur (Vorschlag)
- `core/orchestration_foundation.py`
  - Loop-Controller
  - Decision-Anwendung
  - Stop-Controller
  - Trace-Builder
- `core/orchestration_actions.py`
  - Action-Interfaces und ActionResult-Modelle
- `core/orchestration_policies.py`
  - Progress-Policy
  - No-progress-Policy
  - Fallback-Policy

### Datenmodelle (konzeptionell)
- `OrchestrationState`
  - iteration, lifecycle_state, evidence_count, candidate_state, confidence_state, objective_status
- `OrchestrationDecision`
  - decision, next_action, reason, confidence, fallback_trigger, decision_source
- `ActionResult`
  - status, detail, evidence_delta, state_delta, diagnostics, error_category
- `IterationTrace`
  - before/after snapshots, budget, progress, done_reason, hashes, settings_snapshot_id, policy_version
- `ObjectiveSpec`
  - id, type, acceptance_gates, hard_fail_gates
- `HandoffPacket`
  - handoff_id, source_mode, target_mode, constraints, evidence_bundle, acceptance_gates, max_loop_count

### API-Skizze
- `run_orchestration(plan, initial_state, context, objective) -> OrchestrationOutcome`
- `decide_next_action(state, context, objective) -> OrchestrationDecision`
- `execute_action(action, state, context) -> ActionResult`
- `evaluate_progress(prev_state, next_state, objective) -> ProgressResult`
- `replan_if_needed(state, trace, objective) -> PlanDelta | None`
- `apply_recovery(error, state, context) -> RecoveryResult`
- `handoff_to_mode(packet: HandoffPacket) -> HandoffResult`

### Integrationsplan
1. Orchestration-Kern parallel zu bestehendem `query`-Loop einführen.
2. `query` auf zentrale Orchestration umstellen.
3. `explain/review/describe` in vereinfachter Form anbinden.
4. Inter-Mode Übergaben (`fix <-> review`) als zweiter Ausbau.

### Migrationsstrategie
- Phase 1: Adapter-Layer, damit bestehende Mode-Handler weiter nutzbar bleiben.
- Phase 2: Schrittweise Ablösung mode-lokaler Loops.
- Phase 3: Alt-Loop-Code entfernen, Quality Gates auf zentrale Foundation.

### Risiken im Design
- zu komplexes generisches Action-System
- unklare Grenzen zwischen Orchestrator und Mode-Fachlogik

### Gegenmaßnahmen
- kleines, striktes Action-Interface
- Mode-Fachlogik bleibt im Action-Handler, nicht im Loop-Controller
- Done-Reasons/Trace-Felder als verpflichtender Vertragskern
- formale State-Machine und Objective-Gates als harte Vertragsbestandteile

## Verbindlicher Vertragskern (jetzt)

Diese Punkte sind in Foundation 02 verpflichtend, weil sie Architekturkonsistenz sichern:
- Objective- und Acceptance-Gates als messbarer Zielvertrag
- formale Zustandsmaschine mit erlaubten Übergängen
- Replan-Vertrag mit Triggern, Plan-Delta und Anti-Loop-Regeln
- Failure/Recovery-Kategorien mit klaren Retry/Fallback-Abbruchpfaden
- Inter-Mode-Handoff mit Pflichtfeldern und Loop-Grenzen
- forensikfester Iteration-Trace inkl. Decision-Source und Hash-Ankern

## Bewusst verschoben (spätere Detailphasen)

Diese Punkte werden nicht in Foundation 02 final ausdetailliert, sondern in nachgelagerten Feature-Designs:
- exakte Backoff-Formeln und Jitter-Strategien
- konkrete numerische Defaults je Mode/Profile
- vollständige Test-Matrix je Action-/Error-Kombination
- Replay-Engine und erweiterte Kausalgraph-Visualisierung

## Detaillierungsregel

Foundation 02 definiert den stabilen Orchestrationsvertrag auf Systemebene.  
Implementierungsnahe Feinparameter werden nur in Feature-spezifischen Dokumenten festgelegt.

## V2-Erweiterungen (Proposal-Outcome und Reifegrade)

### V2-Konzept

#### Problem
Der bestehende Orchestrator entscheidet heute primär zwischen `continue` und `stop`, ohne die Reifegrade zwischen Analyse, Vorschlag und Ausführung als eigene Vertragszustände zu führen. Dadurch entstehen:
- unklare Stop-Entscheidungen bei eigentlich ausreichender Analyse
- Vermischung von „empfehlen“ und „ausführen“
- uneinheitliche Endzustände für menschenlesbare und maschinelle Ausgaben

#### Zielbild
Orchestration führt einen expliziten Reifegradpfad:
1. `analysis_complete`
2. `proposal_ready`
3. `execution_ready`

Jeder Reifegrad ist:
- messbar über Gates
- tracebar im Iteration-Log
- an Policy/Budget gekoppelt
- als eigener Outcome-Typ auswertbar

#### Leitprinzipien (V2)
- Reifegrad vor Aktionismus: keine Ausführung ohne nachweisbare Proposal-Reife
- kontrollierte Fortschrittslogik statt „continue bis Budgetende“
- gleiche Semantik in allen Modes, unterschiedliche Gates je Objective

### V2-Spezifikation (Vertragskern)

#### 1. Reifegradmodell (verbindlich)
`OrchestrationState` enthält:
- `maturity_state`: `collecting | analysis_complete | proposal_ready | execution_ready | terminal`
- `maturity_reasons[]`: maschinenlesbare Gründe pro Übergang
- `maturity_gate_status`: Gate-Erfüllung je Reifegrad

Übergänge sind nur vorwärts erlaubt, außer bei explizitem `recover`:
- `collecting -> analysis_complete`
- `analysis_complete -> proposal_ready`
- `proposal_ready -> execution_ready`
- `* -> terminal`

Rückstufung (`proposal_ready -> analysis_complete`) ist nur mit `control_signal=recover` und dokumentiertem Trigger zulässig.

#### 2. Outcome-Typen (verbindlich)
Orchestrator liefert explizit:
- `outcome_type=analysis`
- `outcome_type=proposal`
- `outcome_type=execution`
- `outcome_type=failure`

Mapping-Hinweis zu Foundation 10 (Output Contract):
- `outcome_type=proposal` wird im Output-Vertrag als `result_type=recommendation` repräsentiert.

Regeln:
- `analysis_complete` ohne Proposal-Pfad: `analysis`
- `proposal_ready` ohne Execution-Freigabe: `proposal`
- `execution_ready` + erfolgreicher Execution-Pfad: `execution`
- Policy/Budget/Error-Terminal: `failure`

#### 3. Gate-Klassen (verbindlich)
Gates werden in drei Klassen geführt:
- `evidence_gates` (inhaltliche Basis)
- `readiness_gates` (Umsetzungsreife)
- `safety_gates` (Policy/Scope/Budget)

Mindestzuordnung:
- `analysis_complete` erfordert erfüllte `evidence_gates`
- `proposal_ready` erfordert erfüllte `evidence_gates` + `readiness_gates`
- `execution_ready` erfordert alle drei Gate-Klassen

#### 4. Continue/Stop-Entscheidung nach Reifegrad (verbindlich)
`continue|stop` allein reicht nicht; Entscheidung muss zusätzlich enthalten:
- `maturity_target` (gewünschter nächster Reifegrad oder `terminal`)
- `maturity_gap` (welche Gates fehlen)
- `recommended_action_class` (`collect|analyze|propose|validate|execute|stop`)

Wenn `maturity_gap` leer und keine höheren Reifegrade erlaubt/gewünscht sind, muss `stop` mit passendem `outcome_type` erfolgen.

#### 5. Proposal als kontrollierter Endzustand (verbindlich)
`proposal_ready` ist ein legitimer terminaler Erfolgspfad für nicht-mutierende Läufe.

Pflichtfelder bei terminalem Proposal-Outcome:
- `proposal_status`: `proposed|partial|blocked|uncertain`
- `proposal_confidence`
- `proposal_scope`
- `human_review_required` (bool)

#### 6. Execution-Reife und Freigabe (verbindlich)
`execution_ready` darf nur gesetzt werden, wenn:
- Proposal-Outcome vorhanden
- `safety_gates` grün
- Freigabepfad erfüllt (`policy + user/runtime mode`)

Ohne Freigabe bleibt der Orchestrator bei `proposal`-Outcome und darf nicht implizit in Execution wechseln.

#### 7. Done-Reason-Erweiterung (verbindlich)
Zusätzlich zu v1 muss der finale Trace enthalten:
- `terminal_class`: `success_analysis|success_proposal|success_execution|failure`
- `terminal_gate_snapshot` (Gate-Status zum Abschlusszeitpunkt)

Die bestehende Done-Reason-Priorität bleibt unverändert und wird nicht durch Reifegradmarker überschrieben.

#### 8. Anti-Stall-Regel pro Reifegrad (verbindlich)
No-progress wird reifegradbezogen bewertet:
- `analysis_stall`
- `proposal_stall`
- `execution_stall`

Bei Stall muss ein expliziter Pfad gewählt werden:
- `replan`
- `recover`
- `stop` mit begründetem terminalen Outcome

#### 9. Handoff-Erweiterung (verbindlich)
Inter-Mode-Handoffs müssen den Reifegrad transportieren:
- `source_maturity_state`
- `target_required_maturity`
- `gate_snapshot`

Ein Ziel-Mode darf keine niedrigere Reife stillschweigend annehmen.

### V2-Design (Integrationspunkte)

#### Zielstruktur (Erweiterung)
- `core/orchestration_foundation.py`
  - `MaturityController`
  - `GateEvaluator`
  - `OutcomeClassifier`
- `core/orchestration_gates.py`
  - Gate-Katalog, Gate-Policies, Gate-Evaluationslogik
- `core/orchestration_handoff.py`
  - Reifegrad- und Gate-sichere Handoff-Verträge

#### Modell-Erweiterungen
- `OrchestrationState`
  - ergänzt um `maturity_state`, `maturity_reasons`, `maturity_gate_status`
- `OrchestrationDecision`
  - ergänzt um `maturity_target`, `maturity_gap`, `recommended_action_class`
- `OrchestrationOutcome`
  - ergänzt um `outcome_type`, `terminal_class`, `terminal_gate_snapshot`

#### API-Erweiterungen
- `evaluate_maturity(state, objective, gate_policy) -> MaturityResult`
- `classify_outcome(state, done_reason, maturity_result) -> OutcomeType`
- `select_action_class(maturity_result, progress_result) -> ActionClass`
- `build_terminal_gate_snapshot(state) -> GateSnapshot`

#### Integrationspunkte zu anderen Foundations
- Foundation 01:
  - Phasenmodell konsumiert Reifegradmarker als Übergangsbedingungen
- Foundation 03:
  - Budgetauswertung pro Reifegrad und Action-Klasse
- Foundation 04:
  - Runtime-Settings steuern Ziel-Reifegrad (z. B. „analysis only“ vs. „proposal required“)
- Foundation 10:
  - Output-Sections nach `outcome_type` und `terminal_class`
- Foundation 11:
  - Events für Reifegradwechsel, Gate-Evaluierung und terminale Klassifikation
- Foundation 14/16:
  - `execution_ready` nur bei erlaubter Policy- und Mutation-Lage

#### Migrationsansatz (V2)
1. Reifegradfelder und Gate-Snapshot zuerst rein diagnostisch ergänzen.
2. Outcome-Klassifikation aktivieren, ohne bestehende Continue/Stop-Semantik zu brechen.
3. Actions an `recommended_action_class` ausrichten.
4. Inter-Mode-Handoffs auf Reifegradvertrag migrieren.
5. Alte implizite Endzustandslogik entfernen.
6. Replan-/Recover-Logik berücksichtigt Phasenwechsel explizit.

#### Verbindliche V2-Regel
`proposal_ready` ist nicht gleich `execution_ready`; diese Zustände dürfen nicht zusammengelegt werden.
