# Foundation 01: Mode Execution Foundation

## Zweck
Ein gemeinsames Ausführungsskelett für alle Modes, ohne sie fachlich gleichzuschalten.

## Kernidee
- Einheitliches Stage-Modell (`init`, optionale Fachstages, `finalize`)
- Einheitliche Fehler- und Abbruchpfade
- Einheitlicher Hook für Budget, Logging und Contracts

## Was sie umfasst
- Stage-Definitionen und Stage-Runner
- Mode-spezifische Stage-Komposition (pro Mode konfigurierbar)
- Standardisierte Stage-Result-Struktur

## Verbindlicher StageResult-Vertrag (Kern)

Jede Stage liefert ein strukturiertes `StageResult` mit mindestens:
- `status` (`ok|noop|blocked|error`)
- `state_delta` (fachliche Zustandsänderung)
- `budget_delta` (Anbindung an Foundation 03)
- `diagnostics` (strukturierte Hinweise/Fehler)
- `section_contributions` (beitragende Section-Daten für Foundation 10, keine finalen Section-Objekte)

Optional:
- `evidence_delta`
- `next_actions_hint`
- `policy_events`

Ziel:
- konsistente Übergabe zwischen Stage-Runner, Orchestrator, Budget und Output-Contract.

## Was sie nicht umfasst
- fachliche Retrieval-/Ranking-/Review-Logik
- Prompt-Inhalte

## Beispiel
`ask`: `init -> retrieve_web -> synthesize -> finalize`  
`query`: `init -> derive_terms -> retrieve_repo -> rank -> finalize`

## Erwarteter Umfang
Mittel

## Aufwand für Realisierung
Mittel bis hoch (wegen Migration mehrerer Modes)

## Priorität
P1

## Risiken
- zu starres Stagemodell
- versteckte Standardlogik statt expliziter Mode-Komposition

## Erfolgskriterium
Jeder Mode nutzt das gleiche Ausführungsskelett, bleibt aber fachlich eigenständig.

## Konzept

### Problem
Modes enthalten heute häufig eigene Ablaufsteuerung, Fehlerpfade und Ausgabeverkabelung. Das erschwert Konsistenz und führt zu wiederholter Infrastruktur-Logik in `modes/*`.

### Ziel
- Einheitliches Ausführungsskelett für alle Modes.
- Mode-Code beschreibt fachliche Schritte, nicht Infrastrukturverkabelung.
- Direkte Integration mit:
  - Foundation 02 (Orchestration)
  - Foundation 03 (Budget)
  - Foundation 04 (Runtime Settings)
  - Foundation 10 (Output Contract)
  - Foundation 11 (Observability)

### Nicht-Ziele
- Keine fachliche Vereinheitlichung der Modes.
- Keine erzwungene identische Stage-Liste für alle Modes.
- Kein versteckter „Super-Agent“-Flow.

### Leitprinzipien
- Gleiches Skelett, unterschiedliche Mode-Komposition.
- Starke Verträge zwischen Stages.
- Sichtbare, auditierbare Ausführung.

## Spezifikation

### 1. Stage-Lebenszyklus
Pflichtstages:
- `init`
- `finalize`

Optionale Stages (modeabhängig):
- `resolve`
- `collect`
- `analyze`
- `synthesize`
- `render`

Plan-Invarianten (verbindlich):
- `init` steht genau einmal am Anfang.
- `finalize` steht genau einmal am Ende.
- Stages dürfen nur in deklarierter Reihenfolge laufen.
- Übersprungene Stages müssen als `noop` oder `blocked` im Trace erscheinen.
- Verdeckte Zusatzstages außerhalb des deklarativen Plans sind unzulässig.

### 2. Stage-Vertrag
Jede Stage:
- erhält `ExecutionContext` (state, settings, budget-view, trace-context)
- liefert `StageResult` (siehe Kernvertrag)
- hat deklarierte Ein-/Ausgangsbedingungen

Zusätzlich verpflichtend:
- `StageResult` enthält `stage_name` und `stage_id`.
- `StageResult` enthält eine optionale `done_reason_hint`, darf aber den finalen `done_reason` nicht selbst festschreiben.
- Seiteneffektklasse der Stage ist deklarativ (`none|read|write`), damit Policy-Checks konsistent greifen.
- Der Statusraum ist geschlossen: zusätzliche Stage-Status außerhalb von `ok|noop|blocked|error` sind im Kernvertrag unzulässig.
- Übersprungene Stages werden ausschließlich als `noop` oder `blocked` modelliert.
- `state_delta` ist partiell und mergebar; eine Stage darf nicht stillschweigend den gesamten `ExecutionState` ersetzen.

### 3. Fehler- und Blockverhalten
- Stage-Fehler werden als strukturierte `StageResult.status=error` zurückgegeben.
- Harte Policy/Budget-Blocks führen zu `blocked`.
- Finalisierung muss auch bei Fehler/Block ausgeführt werden (best effort).
- `finalize` konsolidiert vorhandenen State, Diagnostics und Section-Beiträge, darf aber keine fachlich neuen Ergebnisse erfinden und ist kein Ersatz für Recovery-Logik.

Terminalregel:
- Das finale `done_reason` folgt der Prioritätsregel aus Foundation 02.
- Foundation 01 darf diese Priorität nicht überschreiben.
- Ein Stage-Status `error` oder `blocked` bestimmt nicht automatisch den terminalen Run-Status; die finale Auflösung erfolgt über Foundation 02.

### 4. Übergaberegeln zwischen Foundations
- Budgetdeltas aus StageResult werden an Foundation 03 gegeben.
- Diagnostics + Section-Beiträge fließen in Foundation 10.
- Stage-/Action-Events werden über Foundation 11 emittiert.
- Runtime-Settings kommen ausschließlich aus Foundation 04.
- Iterative Action-Entscheidungen laufen über Foundation 02.

Section-Merge-Regeln:
- Jede zentrale Section hat genau einen verantwortlichen Builder (Foundation 10).
- Stages liefern nur Beiträge (`section_contributions`), keine finalen Section-Objekte.
- Merge-Konflikte werden als Diagnostic codiert und brechen den Run nicht stillschweigend.

### 5. Determinismus
- Bei identischem Input und identischen Settings muss die Stage-Sequenz reproduzierbar sein.
- Optionale LLM-Beteiligung darf den Vertragskern nicht verletzen.

### 6. Minimaler Execution-Trace
Pro Stage müssen mindestens erfasst werden:
- run id
- trace id
- iteration id (falls orchestriert)
- stage name
- stage id
- status
- duration
- state delta summary
- budget delta summary
- diagnostics count
- settings snapshot id

## Design

### Zielstruktur (Vorschlag)
- `core/mode_execution_foundation.py`
  - StageRunner
  - ModeExecutionPlan
  - ExecutionContext/ExecutionState
  - Fehler-/Finalisierungsrahmen
- `core/mode_execution_adapters.py`
  - Adapter für bestehende Mode-Implementierungen

### Datenmodelle (konzeptionell)
- `ModeExecutionPlan`
  - mode_name, stages, orchestration_enabled, view_policy, plan_version
- `ExecutionContext`
  - request, settings, settings_snapshot_id, budget_state_ref, obs_context, contract_context
- `ExecutionState`
  - domain_state, iteration_state, diagnostics, section_contributions, terminal_status, done_reason
- `StageResult`
  - stage_name, stage_id, status, state_delta, budget_delta, diagnostics, section_contributions, optional deltas

### API-Skizze
- `run_mode(plan: ModeExecutionPlan, context: ExecutionContext) -> ExecutionOutcome`
- `run_stage(stage, context, state) -> StageResult`
- `apply_stage_result(state, result) -> ExecutionState`
- `finalize_execution(state, context) -> OutputContract`
- `resolve_terminal_status(state, orchestration_outcome) -> (terminal_status, done_reason)`
- `merge_section_contributions(state, contract_builder) -> dict`

### Integrationsplan
1. Foundation mit Adapter-Layer einführen.
2. `query` als Referenzmigration (höchster Nutzen) umstellen.
3. `explain/review/describe` umstellen.
4. `ask` und übrige Modes migrieren.
5. Mode-lokale Ablaufverkabelung entfernen.

### Migrationsstrategie
- Phase 1: bestehende Mode-`run()` bleibt, nutzt intern StageRunner.
- Phase 2: Stage-Verträge pro Mode schärfen, Duplikate abbauen.
- Phase 3: zentrale Execution-Foundation ist führend.

### Risiken im Design
- zu allgemeines Stage-System mit geringer Lesbarkeit
- indirekte Kontrolle („magisch“) statt expliziter Komposition

### Gegenmaßnahmen
- kleine, klare Stage-Schnittstelle
- mode-spezifische Pläne deklarativ sichtbar
- Quality Gates gegen versteckte Nebenpfade

## Verbindlicher Vertragskern (jetzt)

Diese Punkte sind in Foundation 01 verpflichtend:
- StageRunner mit stabilem StageResult-Vertrag
- feste Anbindung an 02/03/04/10/11 über definierte Übergaben
- `init` und `finalize` als verpflichtende Lebenszyklusanker
- strukturierte Fehler-/Blockbehandlung mit best-effort Finalisierung

## Bewusst verschoben (spätere Detailphasen)

Diese Punkte werden nachgelagert konkretisiert:
- optimierte Parallelisierung einzelner Stages
- advanced scheduling zwischen Stages
- modeübergreifende speculative execution

## Detaillierungsregel

Foundation 01 definiert das Ausführungsskelett und die Integrationsverträge.  
Fachliche Stage-Inhalte bleiben in mode-spezifischen Implementierungen.

## V2-Erweiterungen (Analyse/Proposal/Execution)

### V2-Konzept

#### Problem
Der aktuelle Stage-Rahmen ist für Analyse sehr gut geeignet, trennt aber Proposal- und Execution-Phasen noch nicht als eigenständige Ausführungsdomänen. Dadurch droht:
- Vermischung von empfehlender und mutierender Logik
- unklare Übergangspunkte zwischen „verstehen“, „vorschlagen“, „ausführen“
- inkonsistente Contract-Ausgaben (`analysis` vs. `recommendation` vs. `execution_result`)

#### Zielbild
Mode Execution wird als phasenorientierter Ablaufrahmen geführt:
1. `analysis_phase`
2. `proposal_phase`
3. `execution_phase`

Jede Phase hat:
- eigene Stage-Rollen
- eigene Eintrittsbedingungen
- eigene Budget-/Policy-Guards
- eigene Contract-Contributions

#### Leitprinzipien (V2)
- phasenklar statt implizit
- proposal-first vor execution
- keine Mutationen ohne expliziten Freigabe-/Policy-Pfad
- StageRunner bleibt generisch, Phasenlogik deklarativ im Plan

### V2-Spezifikation (Vertragskern)

#### 1. Phasenmodell (verbindlich)
`ModeExecutionPlan` enthält verpflichtend:
- `phases[]` in fester Reihenfolge: `analysis -> proposal -> execution -> finalize`
- pro Phase: `enabled`, `entry_conditions`, `exit_conditions`, `stage_roles[]`

`finalize` bleibt verpflichtender Abschlussanker.

#### 2. Stage-Rollen (verbindlich)
Jede Stage trägt eine Rolle:
- `analysis`
- `proposal`
- `execution`
- `finalize`

Zusatz:
- `safety_class` (`safe_read|planning_only|mutating`)
- `side_effect_class` (`none|read|write`)

#### 3. Phasenübergänge (verbindlich)
Übergänge sind nur erlaubt, wenn Bedingungen erfüllt sind:
- `analysis -> proposal`: mindestens `analysis_complete` (Foundation 02)
- `proposal -> execution`: mindestens `proposal_ready` + Policy/Freigabe
- `execution -> finalize`: Execution abgeschlossen oder blockiert

Nicht erlaubte Übergänge:
- `analysis -> execution` (ohne expliziten Sonderpfad/Policy)
- `proposal` überspringen bei mutierendem Pfad

#### 4. StageResult-Erweiterung (verbindlich)
`StageResult` enthält zusätzlich:
- `phase`
- `phase_transition_hint` (`stay|next_phase|block_phase`)
- `proposal_artifacts` (optional, nur `proposal`-Rollen)
- `execution_artifacts` (optional, nur `execution`-Rollen)

#### 5. Contract-Contributions (verbindlich)
`section_contributions` muss phasenbezogen klassifizierbar sein:
- `analysis_contributions`
- `proposal_contributions`
- `execution_contributions`

Proposal-relevante Contributions müssen mindestens unterstützen:
- `change_proposal`
- `affected_targets`
- `impact_analysis`
- `alternatives`
- `implementation_plan`

#### 6. Safety-Regel (verbindlich)
Stages mit `side_effect_class=write` dürfen nur laufen, wenn:
- Phase = `execution`
- Policy-Entscheidung erlaubt (Foundation 14)
- Write-Scope validiert (Foundation 12/16)
- gültiger Freigabepfad vorliegt

#### 7. Trace-Kern (verbindlich)
Pro Stage zusätzlich zu v1:
- `phase`
- `stage_role`
- `phase_entry_state`
- `phase_exit_state`
- `phase_transition_decision`

### V2-Design (Integrationspunkte)

#### Zielstruktur (Erweiterung)
- `core/mode_execution_foundation.py`
  - `PhaseRunner`
  - `PhaseTransitionEvaluator`
  - `PhaseContributionRouter`
- `core/mode_execution_phase_policies.py`
  - Standard-Eintritts-/Austrittsregeln je Phase

#### Modell-Erweiterungen
- `ModeExecutionPlan`
  - ergänzt um `phases`, `phase_policies`, `result_type_policy`
- `ExecutionState`
  - ergänzt um `current_phase`, `phase_history`, `phase_gate_status`
- `StageResult`
  - ergänzt um `phase`, `phase_transition_hint`, phasenbezogene Artefaktfelder

#### API-Erweiterungen
- `run_phase(phase, context, state) -> PhaseOutcome`
- `evaluate_phase_transition(state, phase_policy, orchestration_state) -> TransitionDecision`
- `route_phase_contributions(state, contract_builder) -> dict`

#### Integrationspunkte zu anderen Foundations
- Foundation 02:
  - konsumiert/stellt `analysis_complete`, `proposal_ready`, `execution_ready`
- Foundation 03:
  - getrennte Budgeträume pro Phase
- Foundation 04:
  - phasenbezogene Runtime-Settings (proposal depth, execution mode)
- Foundation 10:
  - `result_type` und phasenbezogene Sections
- Foundation 11:
  - Events pro Phase und korrelierte Phase-Transitions
- Foundation 14/16:
  - Policy-/Mutation-Gates vor Execution-Stages

#### Migrationsansatz (V2)
1. Phasenmodell zunächst für `query/explain/review` ohne Execution aktivieren (`analysis+proposal`).
2. Proposal-Contributions standardisieren.
3. Execution-Phase zuerst in kontrollierten Flows (z. B. proposal->patch_only) aktivieren.
4. Alte implizite Übergänge entfernen.
