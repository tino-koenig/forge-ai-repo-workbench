# Foundation 07: Retrieval Foundation

## Zweck
Einheitliche Retrieval-Schnittstelle über Repo-, Index-, Graph- und Web-Quellen.

## Kernidee
- alle Retrieval-Quellen liefern kompatible Kandidaten- und Evidenzobjekte
- Source-Typen bleiben transparent (`repo`, `framework`, `web_docs`, ...)

## Was sie umfasst
- Retriever-Interfaces
- Candidate-Modelle
- source_scope/source_origin-Regeln
- Normalisierung von Snippets/Line-Evidence

## Beispiel
`ask:docs` und `query` liefern beide standardisierte Evidenzobjekte für Ranking und Contract-Ausgabe.

## Erwarteter Umfang
Groß

## Aufwand für Realisierung
Hoch

## Priorität
P2

## Risiken
- Überabstraktion mit Verlust von Quellenbesonderheiten
- inkonsistente Qualitätsmetriken je Quelle

## Erfolgskriterium
Retrieval ist quellenübergreifend kompatibel, aber quellenspezifische Metadaten bleiben erhalten.

## Konzept

### Problem
Retrieval-Logik ist oft quellen- und mode-spezifisch verteilt. Dadurch entstehen inkonsistente Kandidatenmodelle, schwer vergleichbare Trefferqualität und uneinheitliche Provenienz.

### Ziel
- Einheitliche Retrieval-Schnittstelle für Repo-, Index-, Graph- und Web-Quellen.
- Gemeinsames Candidate-/Evidence-Format als Input für Foundation 08 (Ranking).
- Transparente Source-Policies und nachvollziehbare Retrieval-Entscheidungen.

### Nicht-Ziele
- Keine Vereinheitlichung aller quelleninternen Algorithmen.
- Kein Ersatz für Ranking/Scoring (das bleibt Foundation 08).
- Keine Vermischung mit Ausgabeformatierung (Foundation 10).

### Leitprinzipien
- Gemeinsames Austauschformat, quellennahe Besonderheiten bleiben als Metadaten erhalten.
- Retrieval liefert Optionen/Evidenz, nicht finale Relevanzurteile.
- Source-Scope und Policy-Regeln sind explizit.

## Spezifikation

### 1. Source-Typen (Kern)
Mindestens:
- `repo`
- `framework`
- `web_docs`
- `web_general`
- `external`

### 2. Retrieval-Request-Vertrag
Jeder Request enthält mindestens:
- `query_terms` (strukturierte Retrieval-Terme bzw. abgeleitete Suchsignale, nicht nur freier Suchtext)
- `target_scope` (z. B. code/docs/general)
- `source_scope` (`repo_only|framework_only|web_only|all|mixed_policy`)
- `budget_view` (aus Foundation 03)
- `policy_context` (aus Foundation 02/04)

### 3. Retrieval-Output-Vertrag
Jede Quelle liefert:
- `retrieval_contract_version`
- `candidates[]`
- `evidence_items[]`
- `retrieval_diagnostics[]`
- `source_usage` (welche Quellen aktiv waren)
- `status` (`ok|partial|blocked|error`)

Kandidatenfelder (mindestens):
- `path_or_url`
- `source_type` (Quellenklasse wie `repo|framework|web_docs|web_general|external`)
- `source_origin` (konkrete Herkunft, z. B. Indexname, Framework-Quelle, Domain, Adapter)
- `retrieval_signals` (Trefferarten)
- `raw_retrieval_score` (quelleninterner Rohwert, optional; kein quellenübergreifendes Relevanzurteil)

Evidenzfelder (mindestens):
- `path_or_url`
- `line` (falls vorhanden)
- `text`
- `term`
- `retrieval_source` (welcher konkrete Retriever/Adapter die Evidenz geliefert hat)
- `source_type`
- `source_origin`

### 4. Normalisierung und Deduplizierung
- Quellenübergreifende Normalisierung auf ein gemeinsames Schema.
- Für die Übergabe an Foundation 08 gilt:
  - `path_or_url` wird in ein einheitliches Feld `locator` überführt.
  - `locator_kind` kennzeichnet `path|url`.
  - Zusätzlich kann für lokale Quellen ein abgeleitetes `path` gesetzt werden.
- Deduplizierung über stabile Schlüssel (z. B. path/url + line + text hash).
- Deduplizierung darf Provenienz nicht verdecken; zusammengeführte Treffer müssen ihre beteiligten Quellen/Adapter nachvollziehbar behalten.
- Deduplizierungsentscheidungen müssen diagnostizierbar sein.

### 5. Source-Policy-Regeln
- Retrieval darf nur Quellen nutzen, die durch Policy/Settings freigegeben sind.
- Bei Policy-Block muss `retrieval_diagnostics` den Blockgrund tragen.
- Scope-Widening ist nur über explizite Orchestration-Entscheidung erlaubt.

### 6. Budget-Integration
- Retrieval muss geplante und tatsächliche Kosten melden (files/tokens/time/external calls).
- Bei Budgetgrenzen endet Retrieval mit strukturiertem Teilergebnis (`status=partial|blocked`) statt stillem Abbruch.

### 7. Qualitätsanforderungen
- Repo-first bei code-zentrierten Aufgaben, sofern starke Repo-Signale vorhanden.
- Web-Treffer müssen als solche explizit markiert sein.
- Keine stillen Source-Umschaltungen ohne Trace-Eintrag.

### 8. Determinismus
- Bei identischem Input, gleicher Source-Lage und gleicher Policy muss Retrieval reproduzierbar sein.
- Nichtdeterministische Quellen (z. B. Web) müssen in Outcome/Diagnostics als solche markiert werden.

## Design

### Zielstruktur (Vorschlag)
- `core/retrieval_foundation.py`
  - gemeinsamer Retrieval-Entry
  - Quellenselektion
  - Aggregation/Normalisierung
- `core/retrieval_sources.py`
  - Source-Adapter (`repo`, `index`, `graph`, `web`)
- `core/retrieval_normalization.py`
  - Kandidaten-/Evidenznormalisierung
  - Deduplizierung

### Datenmodelle (konzeptionell)
- `RetrievalRequest`
  - query_terms, target_scope, source_scope, budget_view, policy_context
  - `query_terms` als strukturierte Retrieval-Signale, nicht nur freier Text
- `RetrievalCandidate`
  - locator, locator_kind, source_type, source_origin, retrieval_signals, raw_retrieval_score, metadata
- `RetrievalEvidence`
  - locator, locator_kind, line, text, term, retrieval_source, source_type, source_origin
- `RetrievalOutcome`
  - candidates, evidence_items, retrieval_diagnostics, source_usage, status, budget_delta

### API-Skizze
- `run_retrieval(request, context) -> RetrievalOutcome`
- `select_sources(request, policy) -> list[SourceAdapter]`
- `normalize_retrieval(raw_results) -> RetrievalOutcome`
- `dedupe_retrieval(outcome) -> RetrievalOutcome`

### Integrationsregeln zu anderen Foundations
- Foundation 04 liefert Source-Policy- und Retrieval-Settings.
- Foundation 02 steuert source_scope-Änderungen und Retry/Replan.
- Foundation 03 liefert Budget-Kontext und erhält Budget-Deltas.
- Foundation 08 konsumiert normalisierte Candidates/Evidence.
- Foundation 10 übernimmt Source-Usage/Diagnostics in standardisierte Sections.
- Foundation 11 protokolliert Retrieval-Phasen und Source-Entscheidungen.

### Integrationsplan
1. Gemeinsamen Retrieval-Request/Outcome einführen.
2. Repo/Index-Retrieval migrieren.
3. Graph-Retrieval integrieren.
4. Web-Retrieval (bestehende Foundations) über Adapter anbinden.
5. Mode-lokale Retrieval-Duplikate entfernen.

### Migrationsstrategie
- Phase 1: Adapter um bestehende Retrieval-Pfade.
- Phase 2: gemeinsames Outcome-Format als Pflicht.
- Phase 3: zentrale Source-Policy- und Budget-Kopplung erzwingen.

### Risiken im Design
- zu generische Normalisierung verliert wichtige Quellensignale
- Source-Policies werden zu komplex
- hoher Integrationsaufwand bei Web/Graph

### Gegenmaßnahmen
- Pflicht-Metadaten für quellenspezifische Felder
- klare Source-Scope-Policy mit kleinem Kern
- schrittweise Migration mit Vergleichstraces

## Verbindlicher Vertragskern (jetzt)

Diese Punkte sind in Foundation 07 verpflichtend:
- einheitlicher Retrieval-Request/Outcome-Vertrag
- normalisierte Candidates/Evidence mit klarer Source-Provenienz und nachvollziehbarer Retriever-Herkunft
- explizite Source-Policy- und Budget-Integration
- diagnostizierbare Deduplizierung und Teilergebnisse
- klarer Retrieval-Status (`ok|partial|blocked|error`) im Outcome
- klare Übergabe an Foundation 08

## Bewusst verschoben (spätere Detailphasen)

Diese Punkte werden nachgelagert konkretisiert:
- semantische Retrieval-Verfahren (Embeddings, Hybrid Search)
- dynamische Source-Auswahl über lernende Policies
- tiefe Relevance-Feedback-Schleifen über mehrere Runs

## Detaillierungsregel

Foundation 07 definiert Retrieval-Verträge, Source-Policies und Normalisierungsgrenzen.  
Quellenspezifische Optimierungsalgorithmen werden in Feature-Dokumenten ausgearbeitet.

## V2-Erweiterungen (Retrieval für Änderungsrelevanz)

### V2-Konzept

#### Problem
Der v1-Retrieval-Vertrag liefert allgemeine Relevanzkandidaten, aber keine garantierte Änderungsnähe für Proposal-/Execution-Vorbereitung. Dadurch fehlen oft:
- belastbare Definition-Anker
- zusammengehörige Call-Sites
- passende Tests und Konfigurationsstellen
- Vergleichsimplementierungen für sichere Planung

#### Zielbild
V2 ergänzt Retrieval um einen expliziten Änderungsrelevanzpfad:
- zielgerichtete Retrieval-Objectives für Änderungsarbeit
- strukturierte Anker-Typen statt nur allgemeiner Trefferlisten
- nachvollziehbare Abdeckung („was wurde gefunden, was fehlt noch“)

#### Leitprinzipien (V2)
- Retrieval liefert strukturierte Änderungsbausteine, nicht nur Suchtreffer
- Abdeckung wird messbar und diagnostizierbar
- Repo-first bleibt Standard für code-zentrierte Proposal-Läufe
- fehlende Anker werden sichtbar gemacht, nicht still geschätzt

### V2-Spezifikation (Vertragskern)

#### 1. Retrieval-Objectives V2 (verbindlich)
Zusätzliche Objective-Typen:
- `definition_lookup`
- `call_site_lookup`
- `test_anchor_lookup`
- `config_anchor_lookup`
- `similar_implementation_lookup`
- `proposal_support`

`proposal_support` ist ein zusammengesetztes Objective und muss intern die Teilziele orchestrieren.

#### 2. Anker-Typen (verbindlich)
RetrievalEvidence erhält klassifizierte `anchor_type`:
- `definition`
- `call_site`
- `test_anchor`
- `config_anchor`
- `similar_impl`
- `supporting_context`

Regel:
- `anchor_type` darf nicht implizit aus freiem Text geschätzt werden, wenn keine evidenzbasierte Grundlage vorliegt.
- Unklassifizierbare Evidenz wird als `supporting_context` geführt.

#### 3. Proposal-Support-Mindestabdeckung (verbindlich)
Für Objective `proposal_support` muss Outcome mindestens versuchen:
- Definition(en)
- Call-Sites
- Testanker
- Konfigurationsanker

Ergebnis wird als `coverage_report` ausgegeben:
- `required_anchor_types`
- `found_anchor_types`
- `missing_anchor_types`
- `coverage_status` (`complete|partial|insufficient`)

`coverage_status=insufficient` darf nicht stillschweigend wie vollständige Abdeckung behandelt werden.

#### 4. Change-Relevance-Signale (verbindlich)
Outcome enthält `change_relevance_signals` je Candidate/Evidence:
- `definition_proximity`
- `call_graph_proximity` (heuristisch/graph-basiert)
- `test_relevance`
- `config_relevance`
- `similarity_signal`

Diese Signale sind Input für Foundation 08 und dürfen dort nicht als bereits finales Ranking missverstanden werden.

#### 5. Retrieval-Bündelung für zusammengehörige Ziele (verbindlich)
Für Änderungsfälle müssen zusammengehörige Treffer gruppierbar sein über:
- `target_group_id`
- `group_role` (`primary|dependent|verification|configuration`)

Damit können Definition + Call-Sites + Tests + Config als zusammenhängendes Paket weitergegeben werden.

#### 6. Failure-/Gap-Semantik V2 (verbindlich)
Bei fehlenden Kernankern:
- keine stille Degradierung auf generische Trefferliste
- Pflichtdiagnose mit `missing_anchor_types`
- empfohlene nächste Retrieval-Aktion (`retry_objective|widen_scope|fallback_analysis_only`)

#### 7. Source-Policy für Änderungsrelevanz (verbindlich)
Bei code-zentrierten Änderungsobjectives:
- `repo` muss priorisiert sein
- `web_*` nur ergänzend, sofern Policy erlaubt

Wenn ausschließlich Web-Evidenz verfügbar ist, muss dies als Risiko diagnostiziert werden (`repo_anchor_missing`).

#### 8. Trace-Kern V2 (verbindlich)
Zusätzlich zu v1:
- `retrieval_objective`
- `anchor_type_distribution`
- `coverage_report`
- `target_group_count`
- `change_relevance_signal_summary`

### V2-Design (Integrationspunkte)

#### Zielstruktur (Erweiterung)
- `core/retrieval_foundation.py`
  - `ObjectiveRetrievalPlanner`
  - `AnchorClassifier`
  - `CoverageEvaluator`
- `core/retrieval_change_support.py`
  - Retrieval-Pipelines für `proposal_support`
  - Zielgruppen-Bündelung

#### Modell-Erweiterungen
- `RetrievalRequest`
  - ergänzt um `retrieval_objective`, `required_anchor_types`, `proposal_context`
- `RetrievalEvidence`
  - ergänzt um `anchor_type`, `target_group_id`, `group_role`
- `RetrievalOutcome`
  - ergänzt um `coverage_report`, `change_relevance_signals`, `target_groups`

#### API-Erweiterungen
- `run_objective_retrieval(request, context) -> RetrievalOutcome`
- `classify_anchor_type(evidence, context) -> AnchorType`
- `evaluate_retrieval_coverage(outcome, required_anchor_types) -> CoverageReport`
- `build_target_groups(outcome) -> list[TargetGroup]`

#### Integrationspunkte zu anderen Foundations
- Foundation 02:
  - Orchestration entscheidet über Retry/Widening auf Basis von `coverage_status`
- Foundation 08:
  - konsumiert `change_relevance_signals` als eigenständige Ranking-Komponenten
- Foundation 09:
  - nutzt `target_groups` und `anchor_type` für präzisere Zielauflösung
- Foundation 10:
  - gibt `coverage_report` und `anchor_type_distribution` sichtbar aus
- Foundation 11:
  - eventet Objective-Wechsel, Coverage-Gaps und Scope-Widening
- Foundation 13:
  - Proposal-Planung nutzt anchor-gebündelte Retrieval-Pakete als Basis

#### Migrationsansatz (V2)
1. `anchor_type` und `coverage_report` zunächst diagnostisch ergänzen.
2. `definition_lookup` und `call_site_lookup` als erste Objectives aktivieren.
3. Test-/Config-Anker sukzessive als Pflicht für `proposal_support` zuschalten.
4. Target-Gruppierung in Übergabe an 08/09 integrieren.
5. Alte unstrukturierte Retrieval-Pfade für Proposal-Kontexte abbauen.

#### Verbindliche V2-Regel
Für `proposal_support` müssen Definitionen, Call-Sites, Testanker und Konfigurationsanker als getrennte Anker-Typen und mit explizitem Coverage-Status ausweisbar sein.
