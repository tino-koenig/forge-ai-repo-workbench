# Foundation 03: Budget Foundation

## Zweck
Ein zentrales Budgetkonto für Iterationen, Zeit, Dateien und Tokens.

## Kernidee
- jede Action meldet Verbrauch
- Budgetzustand wird vor/nach jeder Action protokolliert
- Abbruchregeln sind zentral und modeübergreifend identisch

## Was sie umfasst
- Budgettypen (`max_iterations`, `max_wall_time_ms`, `max_files`, `max_tokens`)
- Kostenmodell pro Action
- Budget-Deltas pro Iteration

## Beispiel
`read` verbraucht `files + tokens`, `rank` nur `tokens`, `stop` verbraucht 0.

## Erwarteter Umfang
Mittel

## Aufwand für Realisierung
Mittel

## Priorität
P1

## Risiken
- unplausible Kostenmodelle pro Action
- driftende Budgetsemantik in einzelnen Modes

## Erfolgskriterium
Budgetentscheidungen sind konsistent und im Trace klar begründet.

## Konzept

### Problem
Budgetverbrauch und Abbruchbedingungen sind aktuell teilweise mode-lokal implementiert. Dadurch unterscheiden sich Semantik, Zählweise und Trace-Qualität.

### Ziel
- Ein zentrales Budgetkonto für alle orchestrierten Abläufe.
- Einheitliche Regeln für Verbrauch, Restbudget und Budget-Abbruch.
- Transparente Vorher/Nachher-Werte in jeder Iteration.

### Nicht-Ziele
- Keine starre globale Kostenmatrix für alle Zukunft.
- Keine fachliche Entscheidung, welche Action „sinnvoll“ ist (das bleibt Orchestration/Mode-Logik).

### Leitprinzipien
- Budgets sind technische Guardrails, keine Qualitätsbewertung.
- Verbrauch muss messbar und reproduzierbar sein.
- Abbrüche durch Budget sind immer explizit begründet.

## Spezifikation

### 1. Budgettypen
Verbindliche Kernbudgets:
- `max_iterations`
- `max_wall_time_ms`
- `max_files`
- `max_tokens`

Erweiterbar:
- `max_actions`
- `max_external_calls`

### 2. Budgetzustand
Für jeden Run wird ein Budgetzustand geführt:
- `limit`
- `used`
- `remaining`
- `exhausted` (bool)

### 3. Verbrauchsmodell
Jede Action meldet Budgetverbrauch als strukturierte Deltas:
- `files_delta`
- `tokens_delta`
- `wall_time_delta_ms` (messbar)
- optional weitere Deltas

### 4. Prüfzeitpunkte
Budgetprüfung muss mindestens stattfinden:
1. vor Action-Ausführung (pre-check)
2. nach Action-Ausführung (post-check)

Wenn pre-check fehlschlägt:
- Action wird nicht ausgeführt
- Iteration erhält Status `budget_blocked`
- `done_reason=budget_exhausted`

### 5. Abbruchregeln
Sobald ein hartes Budget erschöpft ist:
- keine weiteren „verbrauchenden“ Actions
- Orchestrator darf nur finalisieren/summarize

### 6. Trace-Vertrag
Pro Iteration müssen dokumentiert werden:
- budget before/after pro Budgettyp
- verbrauchte Deltas
- verbleibende Budgets
- Budget-Abbruchgrund (falls zutreffend)

### 7. Kalibrierbarkeit
Kostenparameter (z. B. token-Kosten pro Action) müssen über Runtime-Settings zentral überschreibbar sein.

## Design

### Zielstruktur (Vorschlag)
- `core/budget_foundation.py`
  - BudgetState
  - BudgetPolicy
  - Pre-/Post-Checks
  - Delta-Anwendung
- `core/budget_cost_models.py`
  - Kostenregeln pro Action-Typ
  - default + mode-spezifische Overrides

### Datenmodelle (konzeptionell)
- `BudgetLimits`
  - iterations, wall_time_ms, files, tokens
- `BudgetUsage`
  - iterations_used, wall_time_used_ms, files_used, tokens_used
- `BudgetSnapshot`
  - before, delta, after
- `BudgetDecision`
  - `allow|block`, reason

### API-Skizze
- `init_budget(limits) -> BudgetState`
- `precheck_budget(state, planned_delta) -> BudgetDecision`
- `apply_budget_delta(state, actual_delta) -> BudgetState`
- `budget_snapshot(state_before, delta, state_after) -> BudgetSnapshot`

### Integrationsplan
1. Budget Foundation parallel zum bestehenden Query-Loop integrieren.
2. `query` vollständig umstellen.
3. `explain/review/describe` zumindest auf einheitliche wall-time/iteration Budgets umstellen.
4. Verbindliche `sections.budget`-Ausgabe aus der Output Contract Foundation (10) nutzen.

### Migrationsstrategie
- Phase 1: Adapter für bestehende Budgetvariablen.
- Phase 2: zentraler BudgetState wird führend.
- Phase 3: mode-lokale Budgetzähler entfernen.

### Risiken im Design
- falsche Kostenparameter führen zu zu frühem/zu spätem Abbruch
- wall-time kann je Umgebung stark variieren

### Gegenmaßnahmen
- Kostenparameter runtime-konfigurierbar machen
- Budget-Trace in Quality Gates prüfen
- Defaults konservativ wählen und empirisch kalibrieren

## Verbindlicher Vertragskern (jetzt)

Diese Punkte sind in Foundation 03 verpflichtend:
- einheitliche Budgettypen und zentraler Budgetzustand
- Pre-/Post-Budgetchecks mit klarer Block-Semantik
- strukturierte Budget-Deltas je Action/Iteration
- deterministische Budget-Abbruchregeln
- standardisierte Ausgabe in `sections.budget` (Foundation 10)

## Bewusst verschoben (spätere Detailphasen)

Diese Punkte werden nachgelagert konkretisiert:
- adaptive Budget-Profile je Capability/Repo-Typ
- erweiterte Kostenmodelle pro Action-Klasse
- prädiktive Budgetsteuerung auf Basis historischer Runs

## Detaillierungsregel

Foundation 03 definiert den stabilen Budgetvertrag und die Abbruchmechanik.  
Konkrete Kostenparameter und Optimierungsstrategien werden in Feature-Dokumenten geschärft.

## V2-Erweiterungen (Phasen-Budgets und Mutationsschutz)

### V2-Konzept

#### Problem
Ein einziges, globales Budget reicht für v2-Orchestrierung nicht aus, weil Analyse, Proposal und Execution unterschiedliche Risikoprofile haben. Ohne Trennung droht:
- Budgetverdrängung (Analyse verbraucht Execution-Spielraum)
- unscharfe Freigabegrenzen für mutierende Schritte
- schlechte Erklärbarkeit, warum ein Lauf endet oder blockiert

#### Zielbild
Budget wird phasen- und risikobasiert geführt:
1. `analysis_budget`
2. `proposal_budget`
3. `execution_budget`

Zusätzlich zu technischen Budgets existieren operative Schutzbudgets:
- `risk_budget`
- optional `change_surface_budget`

#### Leitprinzipien (V2)
- getrennte Konten statt impliziter Vermischung
- Execution-Budget standardmäßig restriktiver
- technische und operative Grenzen gemeinsam auswerten
- Budgetentscheidungen bleiben deterministisch und tracebar

### V2-Spezifikation (Vertragskern)

#### 1. Phasenkonten (verbindlich)
BudgetState enthält getrennte Konten:
- `analysis`
- `proposal`
- `execution`

Jedes Konto führt:
- `limits`
- `used`
- `remaining`
- `exhausted`

Ein globales `run_total` bleibt optional für Gesamtobergrenzen, ersetzt aber keine Phasenkonten.

#### 2. Budgetklassen je Phase (verbindlich)
Für jede Phase müssen mindestens unterstützt werden:
- `max_iterations`
- `max_wall_time_ms`
- `max_files`
- `max_tokens`

Optional:
- `max_actions`
- `max_external_calls`

Regel:
- Action-Verbrauch wird immer genau einem primären Phasenkonto zugeordnet.
- Cross-phase-Verbrauch ist nur über explizite Transferregel erlaubt.

#### 3. Operative Budgets (verbindlich)
Neben technischen Budgets:
- `risk_budget` (akkumuliertes Risikoprofil geplanter/ausgeführter Schritte)
- `change_surface_budget` (z. B. max betroffene Targets/Dateien; optional aktivierbar)

Wenn operative Budgets erschöpft sind:
- `budget_blocked` für die betroffene Action-Klasse
- kein stillschweigendes Downgrade auf riskantere Ausführungspfade

#### 4. Striktere Execution-Grenzen (verbindlich)
Standardregel:
- `execution` ist restriktiver als `analysis`/`proposal`, sofern nicht explizit überschrieben.

Mindestens eine der folgenden Bedingungen muss standardmäßig strenger sein:
- geringeres `max_tokens`
- geringeres `max_files`
- strengeres `risk_budget`

#### 5. Pre-/Post-Checks pro Phase (verbindlich)
Budgetprüfung erfolgt je Action:
1. `precheck(phase, planned_delta, risk_delta)`
2. `postcheck(phase, actual_delta, actual_risk_delta)`

Bei Precheck-Block:
- Action wird nicht ausgeführt
- Iteration erhält `action_status=blocked`
- `done_reason` gemäß Prioritätsordnung aus Foundation 02

#### 6. Budget-Transfers (verbindlich geregelt)
Transfers zwischen Phasenkonten sind standardmäßig verboten.

Erlaubt nur wenn:
- explizite Runtime-Policy aktiv
- Transfergrund dokumentiert
- Transfergrenze konfiguriert
- Transfer im Trace als eigener Eventtyp erscheint

Ohne erlaubte Transferpolicy darf Execution niemals Analysis-/Proposal-Restbudget verbrauchen.

#### 7. Reifegradkopplung (verbindlich)
Budgetentscheidungen müssen Reifegrad aus Foundation 02 berücksichtigen:
- `analysis_complete`: Analysis-Budget darf finalisiert werden
- `proposal_ready`: Proposal-Budget maßgeblich
- `execution_ready`: Execution-Budget + operative Budgets maßgeblich

`execution_ready` ohne ausreichend verfügbares Execution-/Risk-Budget ist unzulässig.

#### 8. Budget-Diagnostics (verbindlich)
Pflichtdiagnostik bei Block/Exhaust:
- betroffenes Konto + Budgetklasse
- `planned` vs. `remaining`
- Blocktyp (`hard_limit|risk_limit|surface_limit|policy_limit`)
- empfohlene nächste Aktion (`stop|replan|defer_execution`)

#### 9. Trace-Kern V2 (verbindlich)
Pro Iteration zusätzlich zu v1:
- `phase_budget_before/after`
- `global_budget_before/after` (falls aktiv)
- `risk_budget_before/after`
- `change_surface_before/after` (falls aktiv)
- `budget_transfer_event` (optional)

### V2-Design (Integrationspunkte)

#### Zielstruktur (Erweiterung)
- `core/budget_foundation.py`
  - `PhaseBudgetManager`
  - `OperationalBudgetManager`
  - `BudgetTransferController`
- `core/budget_policies.py`
  - Phasenprofile
  - Restriktionsregeln für Execution
  - Transfer-Policies

#### Modell-Erweiterungen
- `BudgetState`
  - ergänzt um `phase_accounts`, `operational_accounts`, `transfer_history`
- `BudgetDecision`
  - ergänzt um `phase`, `blocked_account`, `block_type`, `recommended_next_action`
- `BudgetSnapshot`
  - ergänzt um `phase_snapshot`, `operational_snapshot`, `transfer_snapshot`

#### API-Erweiterungen
- `precheck_phase_budget(state, phase, planned_delta, planned_operational_delta) -> BudgetDecision`
- `apply_phase_budget_delta(state, phase, actual_delta, actual_operational_delta) -> BudgetState`
- `request_budget_transfer(state, from_phase, to_phase, amount, reason) -> TransferDecision`
- `build_budget_diagnostics(state, decision) -> BudgetDiagnostics`

#### Integrationspunkte zu anderen Foundations
- Foundation 01:
  - Stage/Phase liefert primäre Budgetzuordnung je Action
- Foundation 02:
  - Reifegrad und Decision-Logik konsumieren Budgetblockgründe
- Foundation 04:
  - Runtime-Settings liefern Phase-Limits, Transferpolicy, Risk-Limits
- Foundation 10:
  - `sections.budget` enthält Phasen- und operative Budgets
- Foundation 11:
  - Events für Budgetblock, Transfer, Exhaustion, Restriction-Trigger
- Foundation 14/16:
  - Execution-Budgetentscheidungen werden mit Policy-/Mutation-Schutz korreliert

#### Migrationsansatz (V2)
1. Phasenkonten zuerst rein beobachtend mitschreiben.
2. Diagnostics auf phasenbezogene Auswertung umstellen.
3. Harte Prechecks je Phase aktivieren.
4. Operative Budgets (`risk_budget`) zuschalten.
5. Transferregeln nur explizit und standardmäßig deaktiviert einführen.

#### Verbindliche V2-Regel
Execution-Budget ist separat, restriktiver und darf ohne explizite Transferpolicy keine Analysis-/Proposal-Reste konsumieren.
