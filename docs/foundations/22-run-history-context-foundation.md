# Foundation 22: Run History / Context Foundation

## Zweck
Kontrollierte Wiederverwendung früherer Runs, Entscheidungen, Proposals und Kontextzusammenfassungen.

## Kernidee
- frühere Ergebnisse nutzbar machen, aber nur provenance-markiert und staleness-kontrolliert
- Primärfakten und abgeleitete Verdichtung strikt trennen
- Kontextübernahme explizit statt implizit

## Was sie umfasst
- referenzierbare Run-/Decision-/Proposal-History
- Kontextklassen (`facts`, `derived_summary`, `assumptions`, `proposal_summary`)
- Validitäts-/Staleness-Regeln
- Transition-Kontext zwischen Runs
- Integration mit 17/10/11

## Erwarteter Umfang
Mittel bis groß

## Aufwand für Realisierung
Mittel bis hoch

## Priorität
P2

## Risiken
- veralteter Kontext verfälscht Entscheidungen
- LLM-Zusammenfassungen werden als Primärfakt behandelt
- unklare Herkunft bei Run-übergreifender Wiederverwendung

## Erfolgskriterium
Kontextübernahme ist nachvollziehbar, staleness-gesichert und unterscheidet strikt zwischen Fakten und Verdichtung.

## Konzept

### Problem
Run-übergreifende Wiederverwendung ohne klaren Vertrag führt zu stillen Annahmen, inkonsistenter Kausalität und schwerer Auditierbarkeit.

### Ziel
- Standardisierte Kontextobjekte für Wiederverwendung.
- Kontrollierte Übernahme nur bei gültiger Herkunft/Frische.
- klare Priorität: Fakten > abgeleitete Summaries.

### Nicht-Ziele
- Kein globales Gedächtnis ohne Gültigkeitsprüfung.
- Keine automatische Kontextübernahme ohne Transparenz.

### Leitprinzipien
- provenance first
- freshness-aware reuse
- explicit context transitions
- facts over summaries

## Spezifikation

### 1. Kontextklassen
Pflichtklassen:
- `facts`
- `derived_summary`
- `assumptions`
- `proposal_summary`

Jede Klasse hat eigene Validitäts- und Vertrauensregeln.

### 2. Kontextobjekt-Vertrag
Jedes Objekt enthält mindestens:
- `context_id`
- `context_contract_version`
- `context_class`
- `source_run_id`
- `lineage_id` (falls vorhanden)
- `created_at`
- `validity_window`
- `staleness_status` (`fresh|stale|expired|unknown`)
- `provenance_ref`
- `context_confidence`

### 3. Übernahmeregeln
- Übernahme nur bei explizitem `context_reuse_decision`.
- `facts` dürfen `derived_summary` überschreiben, nie umgekehrt.
- `expired` Kontext darf nicht als aktive Entscheidungsgrundlage genutzt werden.
- Bei Konflikten gilt Precedence: `facts > assumptions > proposal_summary > derived_summary`.

### 4. Staleness-Vertrag
Staleness wird mindestens geprüft gegen:
- Repo-/Snapshot-Bezug (z. B. commit/index snapshot)
- Zeitfenster
- Policy-Einschränkungen

Bei Staleness-Konflikt:
- `reuse_status=blocked|limited`
- Pflichtdiagnose mit Ursache.

Reuse-Statusraum (verbindlich):
- `allowed|limited|blocked`

### 5. Transition-Kontext
Run-Übergänge müssen transportieren:
- übernommene Kontextobjekte
- verworfene Kontextobjekte
- Gründe für Übernahme/Verwerfung
- resultierenden Kontextmix für den Zielrun
- explizite Konfliktauflösung pro Kontextklasse

### 6. LLM-Summary-Regel
LLM-abgeleitete Zusammenfassungen:
- immer als `derived_summary` markieren
- niemals ohne Primärfakt-Referenzen als alleinige Grundlage für Execution-nahe Entscheidungen

### 7. Output-/Observability-Kopplung
Pflichtausgabe:
- `context_reuse_summary`
- `staleness_summary`
- `context_conflicts`
- `context_precedence_decisions`

Pflichtevents:
- `context_loaded`
- `context_reuse_allowed`
- `context_reuse_limited`
- `context_reuse_blocked`
- `context_staleness_detected`

## Design

### Zielstruktur (Vorschlag)
- `core/run_history_context_foundation.py`
  - Context Registry
  - Reuse Evaluator
  - Staleness Evaluator
- `core/run_history_context_policies.py`
  - reuse/staleness policies
- `core/run_history_context_diagnostics.py`
  - conflict and staleness diagnostics

### Datenmodelle (konzeptionell)
- `ContextObject`
- `ContextReuseRequest` / `ContextReuseResult`
- `StalenessReport`
- `ContextTransitionSummary`

### API-Skizze
- `load_context_objects(request, store) -> list[ContextObject]`
- `evaluate_context_staleness(objects, repo_state, policy) -> StalenessReport`
- `decide_context_reuse(objects, staleness_report, objective) -> ContextReuseResult`
- `build_context_transition_summary(reuse_result) -> ContextTransitionSummary`

### Integrationspunkte
- Foundation 17: Artifact Lifecycle/Storage und Versionierung
- Foundation 10: standardisierte Kontext-Sections im Contract
- Foundation 11: Telemetrie über Reuse-/Staleness-Entscheidungen
- Foundation 02: Orchestration nutzt Reuse-Entscheidungen als Input
- Foundation 18: Snapshot-/Index-Bezug für Staleness-Prüfung

## Verbindlicher Vertragskern (jetzt)

Diese Punkte sind in Foundation 22 verpflichtend:
- versionierte Kontextobjekte mit Herkunft und Staleness-Status
- explizite Reuse-Entscheidung statt stiller Übernahme
- harte Trennung zwischen Primärfakten und abgeleiteten Summaries
- block/limit-Semantik bei stale/expired Kontext
- nachvollziehbare Kontext-Transitionen zwischen Runs

## Bewusst verschoben (spätere Detailphasen)

- lernende Reuse-Strategien je Repo-/Task-Typ
- semantische Konfliktauflösung zwischen mehreren Summary-Quellen
- tiefere, timeline-basierte Kontextvisualisierung

## Detaillierungsregel

Foundation 22 definiert kontrollierte Kontextwiederverwendung über Runs.  
Sie ersetzt nicht den Primärfakt-Contract der laufenden Analyse.
