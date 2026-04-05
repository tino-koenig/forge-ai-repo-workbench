# Foundation 09: Target Resolution Foundation

## Zweck
Einheitliche Auflösung von Datei-, Symbol- und From-Run-Zielen.

## Kernidee
- zentraler Resolver für path/symbol/run-reference
- konsistente Fehlerbilder und Fallbackregeln
- klare Auflösungsprovenienz

## Was sie umfasst
- Zieltyp-Erkennung
- symbolische Auflösung mit Evidenz-Anker
- from-run Übergabeauflösung mit Transition-Gates

## Beispiel
`forge explain log_llm_event` und `forge review log_llm_event` lösen zum selben Ziel mit gleichem Auflösungsstatus auf.

## Erwarteter Umfang
Mittel

## Aufwand für Realisierung
Mittel

## Priorität
P2

## Risiken
- unterschiedliche Fallbackstrategien je Mode
- unklare Priorität bei Mehrdeutigkeiten

## Erfolgskriterium
Zielauflösung ist modeübergreifend konsistent und im Contract dokumentiert.

## Konzept

### Problem
Target-Auflösung (Pfad, Symbol, from-run) wird in Modes oft unterschiedlich behandelt. Das führt zu inkonsistenten Ergebnissen, schwer erklärbaren Fallbacks und uneinheitlichen Fehlerbildern.

### Ziel
- Eine zentrale, deterministische Target-Resolution.
- Einheitliche Prioritäts- und Ambiguitätsregeln.
- Vollständige Auflösungsprovenienz im Output-Contract.

### Nicht-Ziele
- Keine semantische Codeanalyse als Ersatz für Ranking/Retrieval.
- Keine mode-spezifischen Sonderregeln im Resolver-Kern.

### Leitprinzipien
- Explizite Auflösungsstrategie vor impliziter Heuristik.
- Ambiguitäten werden sichtbar gemacht, nicht versteckt.
- Resolver liefert Status + Begründung + Evidenzanker.

## Spezifikation

### 1. Unterstützte Target-Typen
Mindestens:
- `path`
- `symbol`
- `directory`
- `repo`
- `from_run_reference`

### 2. Auflösungspriorität (verbindlich)
Standardreihenfolge:
1. expliziter gültiger Pfad
2. explizite from-run Referenz (wenn gesetzt)
3. eindeutiger Symboltreffer
4. directory/repo fallback (nur wenn modekonform)

Mode-spezifische Einschränkungen (z. B. kein repo-fallback bei explizitem unresolved target) müssen zentral konfigurierbar sein.

### 3. Ambiguitätsregeln
Wenn mehrere Kandidaten gleichwertig sind:
- Status `ambiguous`
- Kandidatenliste mit Ranking und Begründung
- kein stiller „best guess“ ohne Ambiguitätsmarkierung

### 4. Ergebnisvertrag
Auflösung liefert mindestens:
- `resolution_contract_version`
- `resolved_kind`
- `resolved_path` (falls vorhanden)
- `resolved_symbol` (falls vorhanden)
- `resolution_source` (`explicit_path|symbol_match|from_run|fallback`)
- `resolution_strategy` (`exact|policy_fallback|best_effort_heuristic`)
- `resolution_status` (`resolved|unresolved|ambiguous|blocked`)
- `evidence_anchors` (minimale Auflösungsanker mit path/line/text, falls vorhanden)
- `diagnostics`
- `ambiguity_top_k` (falls `resolution_status=ambiguous`)

### 5. From-Run-Vertrag
Bei `from_run_reference`:
- Transition-Gates müssen zentral geprüft werden.
- Handoff-/Transition-Metadaten werden übernommen und als validierte Transition-Provenienz ausgegeben (run id, source capability, strategy).
- Nicht erlaubte Transition -> `blocked` mit Policy-Diagnose.

### 6. Fehler- und Fallback-Semantik
Pflichtfälle:
- `unresolved_path`
- `unresolved_symbol`
- `ambiguous_target`
- `transition_blocked`
- `io_unreadable_target`

Fallback darf nur erfolgen, wenn für Capability/Mode ausdrücklich erlaubt.

### 7. Determinismus
- Gleiches Input-Set + gleiche Repo-/Index-Lage + gleiche Settings -> gleiches Ergebnis.
- Best-effort-Heuristiken müssen als solche markiert werden.

## Design

### Zielstruktur (Vorschlag)
- `core/target_resolution_foundation.py`
  - Resolver-Entry
  - Prioritätslogik
  - Ambiguitätsbehandlung
- `core/target_resolution_policies.py`
  - mode-/capability-spezifische Fallback-/Transition-Regeln
- `core/target_resolution_diagnostics.py`
  - standardisierte Fehler-/Diagnosecodes

### Datenmodelle (konzeptionell)
- `TargetRequest`
  - raw_target, capability, profile, from_run(optional), constraints, target_hints(optional)
- `TargetCandidate`
  - kind, path, symbol, resolution_priority, rationale, source
- `TargetResolutionResult`
  - resolution_status, resolved_kind, resolved_target, resolved_path, resolved_symbol, resolution_source, resolution_strategy, candidates, evidence_anchors, diagnostics, ambiguity_top_k, transition_meta

### API-Skizze
- `resolve_target(request, context) -> TargetResolutionResult`
- `resolve_from_run_reference(request, context) -> TargetResolutionResult`
- `order_target_candidates_for_resolution(candidates, policy) -> list[TargetCandidate]`
- `validate_transition(source_mode, target_mode, context) -> TransitionDecision`

Hinweis:
- Diese Ordnung dient ausschließlich der Auflösungsauswahl (`resolved|ambiguous|unresolved`) und ist kein fachliches Dokument-/Code-Ranking.
- Fachliches Ranking/Scoring verbleibt in Foundation 08.
- `resolved_target` ist die normalisierte Zielrepräsentation des Resolver-Ergebnisses; spezialisierte Felder wie `resolved_path` und `resolved_symbol` konkretisieren diese Repräsentation.

### Integrationsregeln zu anderen Foundations
- Foundation 04 liefert Auflösungs- und Transition-Policy-Settings.
- Foundation 10 übernimmt `resolved_target` + `resolution_status` + diagnostics in standardisierte Sections.
- Foundation 11 protokolliert Resolution-Phasen und Blockgründe.
- Foundation 08 kann Candidate-Ranking für Ambiguitätsfälle nutzen.

### Integrationsplan
1. Zentrale Resolver-API einführen.
2. `explain/review/describe` auf Resolver umstellen.
3. `query`-nahe Symbolauflösung und from-run-Auflösung anbinden.
4. Mode-lokale Auflösungsduplikate entfernen.

### Migrationsstrategie
- Phase 1: Resolver parallel nutzen, Ergebnisse vergleichen.
- Phase 2: zentrale Auflösung wird führend.
- Phase 3: alte mode-lokale Resolver entfernen.

### Risiken im Design
- zu aggressive Fallbacks verfälschen Nutzerintention
- Ambiguitätsausgaben werden zu laut/unübersichtlich
- unterschiedliche Repo-Zustände beeinträchtigen Reproduzierbarkeit

### Gegenmaßnahmen
- strikte Fallback-Policies pro Capability
- Ambiguitätsausgabe auf Top-K begrenzen, aber transparent im Ergebnisvertrag halten
- Resolution-Status + Source immer explizit ausgeben

## Verbindlicher Vertragskern (jetzt)

Diese Punkte sind in Foundation 09 verpflichtend:
- einheitliche Prioritäts- und Ambiguitätsregeln
- strukturierter Resolution-Status mit Diagnosen
- zentrale from-run Transition-Validierung
- deterministische Auflösung bei identischem Kontext
- standardisierte Contract-Ausgabe der Auflösungsprovenienz inklusive Fallback-/Heuristik-Sichtbarkeit

## Bewusst verschoben (spätere Detailphasen)

Diese Punkte werden nachgelagert konkretisiert:
- tiefere semantische Symbolauflösung über zusätzliche Indexarten
- cross-repo Referenzauflösung
- interaktive Ambiguitätsauflösung mit Nutzerfeedback

## Detaillierungsregel

Foundation 09 definiert den stabilen Auflösungsvertrag.  
Heuristische Verbesserungen und tiefe semantische Auflösung werden in Feature-Dokumenten konkretisiert.

## V2-Erweiterungen (Änderungskontext und Multi-Target)

### V2-Konzept

#### Problem
v1 fokussiert auf Einzelauflösung (`ein Ziel -> ein Ergebnis`). Für Proposal-/Execution-nahe Flows reicht das nicht, weil Änderungskontexte typischerweise aus zusammenhängenden Zielmengen bestehen:
- Definition(en)
- relevante Call-Sites
- betroffene Tests
- Konfigurationsanker
- ggf. konkrete betroffene Regionen

Ohne Multi-Target-Auflösung bleiben Übergaben an Ranking/Proposal fragmentiert.

#### Zielbild
Target Resolution unterstützt in V2 explizit Zielpakete:
- mehrere aufgelöste Targets
- bekannte Beziehungen zwischen Targets
- klarer Gesamtstatus für das Paket (nicht nur pro Einzelziel)

#### Leitprinzipien (V2)
- Einzelauflösung bleibt Basis, Multi-Target ist ein klarer Erweiterungspfad
- Beziehungen sind explizit und prüfbar, nicht implizit
- unvollständige Zielpakete werden diagnostiziert, nicht kaschiert
- Auflösung bleibt deterministisch und policy-konform

### V2-Spezifikation (Vertragskern)

#### 1. Erweiterte Zielarten (verbindlich)
Zusätzliche `resolved_kind`-Typen:
- `definition`
- `call_site`
- `config_anchor`
- `test_anchor`
- `affected_region`

Diese Zielarten ergänzen, ersetzen aber nicht die v1-Basistypen (`path|symbol|directory|repo|from_run_reference`).

#### 2. Multi-Target-Request (verbindlich)
`TargetRequest` kann enthalten:
- `target_objective` (`single_target|proposal_bundle|execution_bundle`)
- `required_target_kinds[]`
- `group_constraints` (z. B. gleiche Datei, gleicher Modulkontext, gleicher symbolischer Ursprung)

Wenn `target_objective != single_target`, muss der Resolver einen Paketstatus liefern.

#### 3. Multi-Target-Result-Vertrag (verbindlich)
`TargetResolutionResult` wird erweitert um:
- `resolved_targets[]`
- `target_groups[]`
- `group_relationships[]`
- `bundle_status` (`complete|partial|insufficient|blocked`)
- `missing_target_kinds[]`

`resolved_targets[]` Einträge müssen pro Ziel enthalten:
- `target_id`
- `resolved_kind`
- `resolved_path`
- `resolved_symbol` (optional)
- `resolution_status`
- `evidence_anchors`

#### 4. Beziehungsmodell (verbindlich)
`group_relationships[]` muss mindestens Typen unterstützen:
- `definition_to_call_site`
- `code_to_test`
- `code_to_config`
- `region_to_definition`

Jede Beziehung enthält:
- `from_target_id`
- `to_target_id`
- `relationship_type`
- `confidence`
- `evidence_refs[]`

#### 5. Bundle-Vollständigkeitsregeln (verbindlich)
Für `proposal_bundle` muss mindestens versucht werden:
- `definition`
- `call_site`
- `test_anchor`
- `config_anchor`

Wenn Pflichtzielarten fehlen:
- `bundle_status=partial|insufficient`
- `missing_target_kinds[]` verpflichtend
- kein stillschweigendes „resolved“ auf Bundle-Ebene

#### 6. Ambiguität in Multi-Target-Kontext (verbindlich)
Ambiguität wird zweistufig geführt:
- pro Ziel (`resolution_status=ambiguous`)
- auf Bundle-Ebene (`bundle_status=partial|insufficient`)

Resolver darf bei Bundle-Zielen keinen unmarkierten „best guess“ erzeugen.

#### 7. From-Run- und Transition-Kopplung V2 (verbindlich)
Bei `from_run_reference` + Bundle-Ziel:
- Übergangsvalidierung muss für das gesamte Zielpaket gelten
- inkompatible Teilziele führen zu `bundle_status=blocked` oder `partial` mit klarer Diagnose

#### 8. Trace-Kern V2 (verbindlich)
Zusätzlich zu v1:
- `target_objective`
- `bundle_status`
- `resolved_target_count`
- `missing_target_kinds`
- `relationship_count`
- `bundle_policy_id`

### V2-Design (Integrationspunkte)

#### Zielstruktur (Erweiterung)
- `core/target_resolution_foundation.py`
  - `MultiTargetResolver`
  - `TargetBundleAssembler`
  - `RelationshipInferencer`
- `core/target_resolution_bundle_policies.py`
  - Bundle-Anforderungen und Vollständigkeitsregeln

#### Modell-Erweiterungen
- `TargetRequest`
  - ergänzt um `target_objective`, `required_target_kinds`, `group_constraints`
- `ResolvedTarget`
  - eigenständiges Modell für Einträge in `resolved_targets[]`
- `TargetBundle`
  - `targets`, `relationships`, `bundle_status`, `missing_target_kinds`
- `TargetResolutionResult`
  - ergänzt um `resolved_targets[]`, `target_groups[]`, `group_relationships[]`, `bundle_status`

#### API-Erweiterungen
- `resolve_target_bundle(request, context) -> TargetResolutionResult`
- `assemble_target_groups(resolved_targets, constraints) -> list[TargetGroup]`
- `infer_target_relationships(groups, evidence) -> list[TargetRelationship]`
- `evaluate_bundle_completeness(bundle, required_target_kinds) -> BundleStatusReport`

#### Integrationspunkte zu anderen Foundations
- Foundation 07:
  - liefert Anchor-Typen und Coverage-Signale als Auflösungsinput
- Foundation 08:
  - nutzt Bundle-Targets und Beziehungen für kontextstärkeres Ranking
- Foundation 10:
  - Ausgabe von `bundle_status`, Zielpaketen und Beziehungsdiagnostik
- Foundation 11:
  - Events zu Bundle-Auflösung, Ambiguität und Missing-Kinds
- Foundation 13:
  - Proposal-Planung nutzt aufgelöste Zielpakete statt Einzelziele
- Foundation 16:
  - Execution darf nur auf explizit aufgelösten, policy-konformen Zielpaketen aufsetzen

#### Migrationsansatz (V2)
1. Multi-Target-Felder zunächst diagnostisch ergänzen.
2. `proposal_bundle` für nicht-mutierende Flows aktivieren.
3. Relationship-Inferenz und Bundle-Status verpflichtend schalten.
4. Mode-lokale Sammelheuristiken durch zentrale Bundle-Auflösung ersetzen.
5. Für Execution-nahe Flows Bundle-Policy als harte Voraussetzung aktivieren.

#### Verbindliche V2-Regel
Für Proposal-/Execution-nahe Flows muss Target Resolution zusammengehörige Ziele als explizites Bundle mit Beziehungen und Bundle-Status ausweisen; Einzelauflösung allein ist dort nicht ausreichend.
