# Foundation 08: Evidence & Ranking Foundation

## Zweck
Gemeinsame Evidenz-Modelle und nachvollziehbares Ranking über Modes hinweg.

## Kernidee
- Treffer sammeln und Treffer bewerten sind getrennte Schritte
- Score-Komponenten sind sichtbar und erklärbar
- symbolnahe Treffer können gezielt priorisiert werden

## Was sie umfasst
- gemeinsame Evidenztypen
- Ranking-Pipeline mit Komponenten (source match, symbol match, intent fit, freshness, etc.)
- Rerank-Hooks (z. B. explain feedback)

## Beispiel
Bei „Wo ist `enrich_detailed_context` definiert?“ erhält ein direkter Symboltreffer höheres Gewicht als generische `function`-Treffer.

## Erwarteter Umfang
Groß

## Aufwand für Realisierung
Hoch

## Priorität
P1

## Risiken
- intransparente Score-Regeln
- zu viele implizite Heuristiken statt klarer Komponenten

## Erfolgskriterium
Für Top-Kandidaten ist jederzeit nachvollziehbar, warum sie oben stehen.

## Konzept

### Problem
Trefferbewertung entsteht oft aus verteilten Heuristiken. Dadurch werden Rankings schwer nachvollziehbar, schwer testbar und zwischen Modes inkonsistent.

### Ziel
- Einheitliches Evidenzmodell und ein deklaratives Ranking-System.
- Trennung von Retrieval (Treffer sammeln) und Ranking (Treffer bewerten).
- Jeder Top-Treffer muss durch Score-Komponenten erklärbar sein.

### Nicht-Ziele
- Keine universelle „eine Formel für alle Fälle“.
- Keine Black-Box-Rankings ohne Komponentenaufschlüsselung.
- Keine Vermischung mit Output-Rendering.

### Leitprinzipien
- Komponentenbasiertes Scoring statt monolithischer Punktzahl.
- Nachvollziehbarkeit vor kurzfristiger Heuristik-Optimierung.
- Mode-spezifische Gewichtung möglich, aber über deklarierte Policies.

## Spezifikation

### 1. Evidenzmodell (Kern)
Jede Evidenz enthält mindestens:
- `locator` (`path` oder `url`)
- `locator_kind` (`path|url`)
- `line`
- `text`
- `term`
- `retrieval_source` (z. B. `content_match`, `symbol_match`, `path_match`, `summary_match`, `graph_match`)
- `source_type` (z. B. `repo`, `framework`, `web_docs`, `external`)
- `source_origin` (Provenienz der Quelle)

### 2. Candidate-Modell
Jeder Kandidat enthält mindestens:
- `locator` (`path` oder `url`)
- `evidence[]`
- `score_total` (aggregierter Rankingwert, kein semantischer Wahrheitswert)
- `score_components[]`
- `ranking_policy_id`
- `status` (`ok|partial|error`)

### 3. Score-Komponenten (verbindlich)
Mindestens:
- `symbol_match_score`
- `content_match_score`
- `path_match_score`
- `intent_fit_score`
- `source_type_score`
- `quality_penalty` (z. B. noisige/irrelevante Quellen)

Optional:
- `freshness_score`
- `framework_fit_score`
- `resolution_anchor_score` (aus Foundation 09)
- `llm_task_signal_score` (aus Foundation 06, strikt getrennt)

### 4. Gewichtungsregeln
- Komponenten werden über deklarative Policy gewichtet.
- Gewichte sind runtime-konfigurierbar (über Foundation 04), aber mit sicheren Defaults.
- Gewichtsänderungen müssen im Trace/Contract sichtbar sein (`ranking_policy_id`, `policy_version`, optional `weights_source`).

### 5. Explainability-Vertrag
Für Top-N Kandidaten muss ausgebbar sein:
- Komponentenwerte
- Gesamtwert
- wichtigste Evidenzanker
- rationale Kurzbegründung
- angewandte Tie-break-Regeln (falls relevant)

### 6. Rerank-Vertrag
Rerank ist erlaubt, aber geregelt:
- Rerank darf nur deklarierte Komponenten verändern.
- Rerank-Schritte werden als eigene Ranking-Phase protokolliert.
- Rerank muss idempotent bei gleichen Inputs/Settings sein.
- Rerank darf das Kernranking nicht durch verdeckte Ersatzlogik umgehen; alle Änderungen müssen über deklarierte Komponenten, Policies oder Tie-break-Regeln erklärbar bleiben.

### 7. Determinismus
- Gleiches Input-Set + gleiche Policy + gleiche Settings -> gleiches Ranking.
- LLM-unterstützte Signale (falls genutzt) müssen als separate Komponente markiert werden und dürfen Kernclaims nicht verdecken.
- Tie-break-Verhalten muss bei gleichen Inputs/Policies stabil und nachvollziehbar sein.

### 8. Qualitätsanforderungen
- Ranking darf relevante Symboltreffer nicht systematisch hinter generischen Treffern verstecken.
- Docs-/Web-Treffer müssen bei code-zentrierten Fragen kontrolliert niedriger priorisiert werden, wenn starke Repo-Evidenz vorhanden ist.

## Design

### Zielstruktur (Vorschlag)
- `core/evidence_foundation.py`
  - gemeinsame Evidenz- und Candidate-Modelle
- `core/ranking_foundation.py`
  - Komponentenberechnung
  - Gewichtsaggregation
  - Tie-break-Regeln
- `core/rerank_foundation.py`
  - deklarierte Rerank-Phasen
  - Rerank-Trace

### Datenmodelle (konzeptionell)
- `EvidenceItem`
  - locator, locator_kind, line, text, term, retrieval_source, source_type, source_origin
- `ScoreComponent`
  - name, raw_value, weight, weighted_value, rationale
- `RankedCandidate`
  - locator, locator_kind, score_total, score_components, evidence, ranking_policy_id, status
- `RankingOutcome`
  - candidates, policy_id, policy_version, diagnostics, rerank_steps

### API-Skizze
- `build_candidates(evidence_items, context) -> list[Candidate]`
- `score_candidates(candidates, policy, context) -> list[RankedCandidate]`
- `rerank_candidates(candidates, rerank_policy, context) -> list[RankedCandidate]`
- `explain_ranking(candidates, top_n) -> list[RankingExplanation]`

### Integrationsregeln zu anderen Foundations
- Foundation 07 liefert normalisierte Retrieval-Evidenz.
- Foundation 04 liefert Ranking-Policy-Einstellungen.
- Foundation 10 übernimmt Ranking-Erklärung in `sections` (`why`/`explain_feedback` o. ä.).
- Foundation 11 protokolliert Ranking- und Rerank-Phasen.
- Foundation 09 liefert ggf. `evidence_anchors` aus der Zielauflösung; diese dürfen als eigene Komponente (`resolution_anchor_score`) in das Ranking einfließen, aber nicht die Kernkomponenten ersetzen.
- Foundation 06 darf LLM-abgeleitete Signale nur über explizit deklarierte Komponenten einspeisen (`llm_task_signal_score`), stets getrennt von deterministischen Kernkomponenten.

### Integrationsplan
1. Gemeinsame Evidenzmodelle einführen.
2. Query-Ranking auf Komponentenmodell migrieren.
3. Explain/Review-Ranking schrittweise angleichen.
4. Mode-lokale Scoring-Duplikate abbauen.

### Migrationsstrategie
- Phase 1: alter und neuer Score parallel berechnen (vergleichend).
- Phase 2: neuer Score wird führend, alter nur als Diagnose.
- Phase 3: alte Heuristikpfade entfernen.

### Risiken im Design
- Komponentenexplosion macht Ranking unübersichtlich
- zu aggressive Konfigurierbarkeit destabilisiert Defaults
- Rerank kann ungewollt Kernranking überschreiben

### Gegenmaßnahmen
- kleiner verpflichtender Komponenten-Kern
- klare Policy-IDs und Quellenangabe
- Rerank nur über explizit erlaubte Komponenten

## Verbindlicher Vertragskern (jetzt)

Diese Punkte sind in Foundation 08 verpflichtend:
- gemeinsames Evidenz- und Candidate-Modell
- komponentenbasiertes Scoring mit sichtbarer Aufschlüsselung
- deklarierte Ranking-Policy mit stabiler ID und sichtbarer Version
- erklärbares Top-N-Ranking
- stabile und nachvollziehbare Tie-break-Logik
- deterministisches Verhalten bei identischem Input

## Bewusst verschoben (spätere Detailphasen)

Diese Punkte werden nachgelagert konkretisiert:
- lernende Gewichtsanpassung über historische Runs
- query- oder repo-spezifische Auto-Tuning-Strategien
- fortgeschrittene Hybrid-Ranker (z. B. semantische Embeddings)

## Detaillierungsregel

Foundation 08 definiert Ranking-Verträge, Komponenten und Explainability.  
Heuristik-Tuning und Gewichtsoptimierung werden in Feature-Dokumenten konkretisiert.

## V2-Erweiterungen (Ranking für Änderungsrelevanz)

### V2-Konzept

#### Problem
Ein Ranking, das nur allgemeine Text-/Symbolrelevanz bewertet, reicht für Proposal-/Execution-Vorbereitung nicht aus. In Änderungsfällen müssen zusätzlich berücksichtigt werden:
- Nähe zur tatsächlichen Änderungsstelle
- Abhängigkeitswirkung
- Testabdeckung/-auswirkung
- Konfigurationsbezug

Ohne diese Sicht werden „sprachlich passende“ Treffer zu hoch priorisiert und operativ relevante Targets zu niedrig.

#### Zielbild
V2 ergänzt das Ranking um einen eigenen Änderungsrelevanzraum:
- allgemeine Relevanz (v1-Kern)
- change relevance (v2-Komponenten)

Beide Räume werden transparent kombiniert, ohne deterministische Kernkomponenten zu verdecken.

#### Leitprinzipien (V2)
- Änderungsnähe ist explizit, messbar und erklärbar
- Proposal-Kontext hat andere Priorisierung als reine Analyse
- Komponenten bleiben getrennt und nachvollziehbar
- Ranking bleibt policy-gesteuert und reproduzierbar

### V2-Spezifikation (Vertragskern)

#### 1. Change-Relevance-Komponenten (verbindlich)
Zusätzliche Komponenten:
- `change_proximity_score`
- `dependency_impact_score`
- `test_relevance_score`
- `config_relevance_score`
- `anchor_coverage_score` (aus Foundation 07 coverage/anchor-Typen)

Optional:
- `change_risk_alignment_score`
- `verification_readiness_score`

#### 2. Kontextabhängige Policy-Profile (verbindlich)
Ranking-Policy muss mindestens zwischen folgenden Kontexten unterscheiden:
- `analysis_context`
- `proposal_context`
- `execution_context` (optional, falls aktiv)

Regel:
- Im `proposal_context` müssen Change-Relevance-Komponenten aktiv und im Explain-Output sichtbar sein.
- Im `analysis_context` dürfen sie reduziert, aber nicht implizit als 0 ohne Kennzeichnung behandelt werden.

#### 3. Kombinationsregeln (verbindlich)
Gesamtwertung wird als zwei explizite Teilwerte geführt:
- `general_relevance_total`
- `change_relevance_total`

`score_total` muss herleitbar sein über deklarierte Kombination:
- z. B. gewichtete Summe mit Kontextprofil
- kein verdecktes Überschreiben einer Teilwertung

#### 4. Mindestschutz gegen Fehlpriorisierung (verbindlich)
Im `proposal_context` gilt:
- Kandidaten mit starker allgemeiner Relevanz, aber fehlender Änderungsnähe dürfen nicht systematisch vor Kandidaten mit belastbarer Änderungsnähe liegen.

Pflichtdiagnose bei möglicher Fehlpriorisierung:
- `proposal_priority_conflict`
- inkl. referenzierter Kandidaten und Konfliktkomponenten

#### 5. Abdeckungsintegration aus Retrieval (verbindlich)
Wenn Foundation 07 `coverage_status` liefert:
- `coverage_status=insufficient` muss als Ranking-Risiko signalisiert werden
- `anchor_coverage_score` muss entsprechend reduziert/markiert werden

Ranking darf bei unzureichender Abdeckung keine Scheinsicherheit suggerieren.

#### 6. Tie-break-Regeln V2 (verbindlich)
Tie-break im Proposal-Kontext priorisiert:
1. `change_relevance_total`
2. `general_relevance_total`
3. stabile technische Reihenfolge (z. B. locator-ordnung)

Abweichende Tie-break-Policy muss explizit dokumentiert sein.

#### 7. Explainability-Vertrag V2 (verbindlich)
Top-N-Erklärung muss zusätzlich enthalten:
- getrennte Teilwerte (`general_relevance_total`, `change_relevance_total`)
- dominante Change-Komponenten
- Coverage-/Risikosignale aus 07
- angewandtes Kontextprofil

#### 8. Determinismus und Grenzen (verbindlich)
- Gleicher Input + gleiches Kontextprofil + gleiche Policy => identisches Ergebnis.
- LLM-Signale (Foundation 06) bleiben separat (`llm_task_signal_score`) und dürfen Change-Kernkomponenten nicht ersetzen.

### V2-Design (Integrationspunkte)

#### Zielstruktur (Erweiterung)
- `core/ranking_foundation.py`
  - `ContextualRankingPolicyResolver`
  - `ChangeRelevanceScorer`
  - `RankingConflictDetector`
- `core/ranking_explainability.py`
  - Zweiraum-Erklärungen (`general` vs. `change`)

#### Modell-Erweiterungen
- `ScoreComponent`
  - ergänzt um `component_group` (`general|change|aux`)
- `RankedCandidate`
  - ergänzt um `general_relevance_total`, `change_relevance_total`, `ranking_risks[]`
- `RankingOutcome`
  - ergänzt um `context_profile`, `priority_conflicts[]`

#### API-Erweiterungen
- `resolve_ranking_context_profile(context, settings) -> RankingContextProfile`
- `score_change_relevance(candidates, evidence, context_profile) -> list[ScoreComponent]`
- `detect_ranking_priority_conflicts(candidates, context_profile) -> list[RankingConflict]`
- `explain_contextual_ranking(candidates, top_n, context_profile) -> list[RankingExplanation]`

#### Integrationspunkte zu anderen Foundations
- Foundation 07:
  - liefert `change_relevance_signals`, `anchor_type`, `coverage_report`
- Foundation 04:
  - liefert Kontextprofile und Gewichte
- Foundation 09:
  - liefert Auflösungsanker für `resolution_anchor_score`
- Foundation 10:
  - Ausgabe der Zweiraum-Scores und Konfliktdiagnosen
- Foundation 11:
  - Events zu Profilwahl, Konfliktdetektion, Rerank-Phasen
- Foundation 13:
  - Proposal-Planung konsumiert priorisierte Kandidaten mit expliziter Änderungsrelevanz

#### Migrationsansatz (V2)
1. Zweiraum-Scores zunächst diagnostisch parallel berechnen.
2. Proposal-Kontext auf V2-Kontextprofil umstellen.
3. Konfliktdetektion und Explainability verpflichtend aktivieren.
4. Alte monolithische Rankingpfade für Proposal-Läufe abbauen.
5. Quality Gates für Fehlpriorisierungen im Proposal-Kontext ergänzen.

#### Verbindliche V2-Regel
Im Proposal-Kontext muss Ranking Änderungsnähe explizit und getrennt von allgemeiner Relevanz ausweisen; reine Textrelevanz darf den Endrang nicht allein dominieren.
