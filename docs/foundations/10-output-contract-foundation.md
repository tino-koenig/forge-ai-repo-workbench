# Foundation 10: Output Contract Foundation

## Zweck
Standardisierte Ausgabe-Sektionen für JSON und Human-Views.

## Kernidee
- wiederkehrende Blöcke zentral bauen
- Modes liefern nur ihre fachlichen Inhalte
- konsistente Contract-Struktur vereinfacht Tests, UI und Automations

## Was sie umfasst
- Section-Builder für `llm_usage`, `provenance`, `action_orchestration`, `limits`, `policy_violations`
- helpers für view-spezifische Ausgabe (`compact`, `standard`, `full`)

## Beispiel
`query`, `review`, `describe`, `explain` liefern alle dieselbe `action_orchestration`-Struktur.

## Erwarteter Umfang
Mittel

## Aufwand für Realisierung
Mittel

## Priorität
P1

## Risiken
- zu starres Schema behindert mode-spezifische Details
- unsaubere Migration mit gemischten Alt-/Neu-Sections

## Erfolgskriterium
Wiederkehrende Contract-Abschnitte kommen ausschließlich aus zentralen Buildern.

## Konzept

### Problem
Mehrere Modes bauen ähnliche Contract-Sektionen selbst zusammen. Das führt zu strukturellen Abweichungen, erschwert Tests/Automations und senkt Auditierbarkeit.

### Ziel
- Einheitlicher Output-Vertrag für JSON und Human-Views.
- Wiederkehrende Sektionen kommen nur aus zentralen Section-Buildern.
- Modes liefern primär fachliche Inhalte, nicht Contract-Mechanik.

### Nicht-Ziele
- Keine Vereinheitlichung sämtlicher mode-spezifischer Inhalte.
- Keine starre Verhinderung sinnvoller, mode-spezifischer Zusatzsektionen.

### Leitprinzipien
- Stabiler Kernvertrag, erweiterbar über versionierte Zusatzsektionen.
- JSON-Vertrag ist führend; Human-View ist daraus abgeleitet.
- Änderung am Kernvertrag ist immer versioniert.

## Spezifikation

### 1. Vertragskern (verbindlich)
Jeder Mode-Output enthält mindestens:
- `capability`
- `profile`
- `summary`
- `evidence`
- `uncertainty`
- `next_step`
- `sections`

Mindestsemantik des Kernvertrags:
- `summary`: kompakte, fachliche Zusammenfassung des Ergebnisses
- `evidence`: strukturierte Belegbasis für zentrale Aussagen
- `uncertainty`: strukturierte Unsicherheiten, offene Punkte oder Vertrauensgrenzen
- `next_step`: klarer nächster fachlicher oder operativer Schritt

### 2. Pflichtsektionen (zentral gebaut)
In `sections` müssen zentrale Kernsektionen als stabile Keys in einem Mapping geführt werden. Nicht anwendbare Sektionen werden nicht frei weggelassen, sondern mit klarem Status transportiert (z. B. `not_applicable` oder `omitted`).

- `action_orchestration`
- `budget`
- `llm_usage`
- `provenance`
- `diagnostics`
- `limits`
- `runtime_settings`
- `policy_violations`

### 3. Section-Vertrag
Jede zentrale Section benötigt:
- stabiles Schema
- semantische Felddefinition
- versionierten Abschnittskopf (mindestens intern)
- klaren Section-Status (`available|not_applicable|omitted|fallback`)

Verbindliche Mindestsemantik:
- `action_orchestration`: Entscheidungsfluss, relevante Action-/Replan-/Recovery-/Handoff-Informationen und `done_reason` (falls orchestriert)
- `provenance`: nachvollziehbare Herkunft fachlich relevanter Quellen, Retriever-/Resolver-/Ranking-Provenienz (wo anwendbar)
- `budget`: limits/usage/remaining/exhausted + per-iteration snapshots (falls orchestriert)
- `llm_usage`: Task-/Provider-bezogene Usage-, Cost- und Herkunftsinformationen (wo LLM beteiligt war)
- `runtime_settings`: resolved values (wo sinnvoll), sources, diagnostics-codes
- `diagnostics`: technische, validatorische und kausale Diagnoseinformationen inkl. Ursachenketten und Fallback-Hinweisen; keine freie Dublette normativer Policy-Verstöße
- `policy_violations`: ausschließlich normative Verstöße gegen definierte Policies/Regeln
- `limits`: Budget-, Capability- oder Ausführungsgrenzen, auch ohne Policy-Verstoß

Status-Semantik (verbindlich):
- normative Status- und `done_reason`-Semantik folgt unverändert Foundation 02
- terminale normative Gründe (z. B. `policy_blocked`) werden nicht in freie Texte umgeschrieben, abgeschwächt oder neu interpretiert

### 4. Kompatibilität und Versionierung
- Der Contract hat eine `contract_version`.
- Breaking Changes erhöhen Major-Version.
- Additive Felder sind Minor-kompatibel.
- Deprecated Felder bleiben mindestens einen Übergangszyklus lesbar.

### 5. Human-View-Ableitung
- `compact`, `standard`, `full` werden aus dem JSON-Vertrag abgeleitet.
- View-Logik darf Informationen verdichten oder weglassen, aber keine zusätzlichen fachlichen Aussagen erzeugen, keine Contract-Semantik umdeuten und keine neue Statuslogik berechnen, die nicht im Contract liegt.

### 6. Fehler- und Fallback-Verhalten
- Bei unvollständigen Daten werden Pflichtsektionen nicht „erfunden“, sondern mit klaren Fallback-Indikatoren ausgegeben.
- Fallback-Gründe sind maschinenlesbar.

### 7. Qualitätsanforderungen
- Konsistenz: gleiche Sektion, gleiche Semantik über alle Modes.
- Auditierbarkeit: jede zentrale Sektion enthält Herkunft/Status (z. B. `used`, `attempted`, `fallback_reason`).
- Testbarkeit: Schema-Validation pro Mode gegen denselben Kernvertrag.

## Design

### Zielstruktur (Vorschlag)
- `core/output_contract_foundation.py`
  - Kernvertrag-Assembler
  - Contract-Versionierung
- `core/output_sections.py`
  - zentrale Section-Builder
- `core/output_views.py`
  - reine Darstellung aus Contract (keine neue Semantik)

### Datenmodelle (konzeptionell)
- `OutputContract`
  - capability, profile, summary, evidence, uncertainty, next_step, sections (Mapping), contract_version
- `SectionBuilderResult`
  - section_name, payload, status, diagnostics, section_version
- `ContractDiagnostic`
  - code, message, severity, section

### API-Skizze
- `build_contract_core(...) -> OutputContract`
- `build_section_action_orchestration(...) -> dict`
- `build_section_budget(...) -> dict`
- `build_section_llm_usage(...) -> dict`
- `build_section_provenance(...) -> dict`
- `build_section_diagnostics(...) -> dict`
- `build_section_runtime_settings(...) -> dict`
- `validate_contract_schema(contract) -> list[ContractDiagnostic]`
- `render_view(contract, view) -> str`

### Integrationsplan
1. Bestehende zentrale `build_contract`-Nutzung auf Kernvertrag + Section-Builder schärfen.
2. `query` migrieren (höchster Nutzen durch komplexe Sections).
3. `explain`, `review`, `describe`, `ask` migrieren.
4. Mode-lokale Duplikate für Kernsektionen entfernen.

### Migrationsstrategie
- Phase 1: parallele Ausgabe (alter + neuer Builder) intern vergleichen.
- Phase 2: neue Section-Builder als alleinige Quelle.
- Phase 3: Schema-Gates in CI verpflichtend.

### Risiken im Design
- zu starres Schema kann Mode-Innovation bremsen
- Mischzustand alter/neuer Sections erzeugt Inkonsistenz

### Gegenmaßnahmen
- stabiler Kern + klar definierte Erweiterungszonen
- versionierte Schema-Validation in Quality Gates
- schrittweise Migration mit Vergleichs-Checks

## Verbindlicher Vertragskern (jetzt)

Diese Punkte sind in Foundation 10 verpflichtend:
- einheitlicher Kernvertrag mit `contract_version`
- zentrale Builder für wiederkehrende Sektionen
- schema-validierbare Pflichtsektionen
- `sections` als Mapping mit stabilen Section-Keys und explizitem Section-Status
- Human-Views als reine Contract-Ableitung
- `budget` und `runtime_settings` als zentrale, nicht mode-lokale Kernsektionen
- `diagnostics` als zentrale Sektion für technische Ursachenanalyse
- unveränderte Übernahme normativer Status- und Done-Reason-Semantik aus Foundation 02

## Bewusst verschoben (spätere Detailphasen)

Diese Punkte werden nachgelagert konkretisiert:
- vollständige maschinenlesbare JSON-Schema-Dateien je Minor-Version
- automatische Contract-Migrationshelfer zwischen Major-Versionen
- erweiterte UI-spezifische Rendering-Optimierungen

## Detaillierungsregel

Foundation 10 definiert den stabilen Output-Vertrag und die Builder-Grenzen.  
Mode-spezifische inhaltliche Ausgestaltung bleibt außerhalb des Kernvertrags.

## V2-Erweiterungen (Analyse vs. Proposal vs. Execution Output)

### V2-Konzept

#### Problem
Im v1-Vertrag sind Analyse, Empfehlung und Ausführung noch nicht als strikt getrennte Ergebnisarten formalisiert. Dadurch entstehen Risiken:
- recommendation-ähnliche Outputs wirken wie Ausführungsresultate
- unklare Bedeutung von Sections in proposal-nahen Läufen
- erschwerte Automations-/UI-Auswertung bei gemischten Zuständen

#### Zielbild
Der Output-Contract führt in v2 eine klare Ergebnis-Klassifikation ein:
- `analysis`
- `recommendation`
- `execution_result`
- `failure`

Zusätzlich werden Proposal-/Planungsartefakte als standardisierte Sections geführt, mit klarer Gültigkeit je Ergebnisart.

#### Leitprinzipien (V2)
- Ergebnisart ist explizit und maschinenlesbar
- Section-Sichtbarkeit folgt klaren Regeln pro Ergebnisart
- keine semantische Überdehnung von Proposal als Execution
- Human-Views bleiben reine Ableitung aus dem Contract

### V2-Spezifikation (Vertragskern)

#### 1. Ergebnis-Klassifikation (verbindlich)
`OutputContract` enthält:
- `result_type` (`analysis|recommendation|execution_result|failure`)
- `result_status` (`success|partial|blocked|error`)
- `maturity_state` (übernommen aus Foundation 02, falls vorhanden)

Mapping-Hinweis zu Foundation 02:
- `outcome_type=proposal` entspricht im Output-Vertrag `result_type=recommendation`.

Regeln:
- `analysis`: Analyse abgeschlossen, kein belastbares Proposal erforderlich oder vorhanden
- `recommendation`: Proposal-/Planungsartefakte vorhanden, keine Mutation ausgeführt
- `execution_result`: tatsächliche Mutation/Execution wurde ausgeführt und berichtet
- `failure`: terminaler Fehler-/Blockpfad

#### 2. Proposal-/Plan-Sections (verbindlich)
Neue zentrale Sections:
- `change_proposal`
- `affected_targets`
- `impact_analysis`
- `alternatives`
- `implementation_plan`

Jede Section führt:
- `status` (`available|partial|not_applicable|omitted|fallback`)
- `section_version`
- `payload`
- `diagnostics` (optional)

#### 3. Ergebnisart-zu-Section-Regeln (verbindlich)
Mindestzuordnung:
- `analysis`:
  - Proposal-Sections optional, falls vorhanden klar als vorbereitend markiert
- `recommendation`:
  - mindestens `change_proposal` + `affected_targets` erforderlich (oder `partial` mit Diagnose)
- `execution_result`:
  - Proposal-Sections optional als Referenz
  - zusätzlich Execution-bezogene Ergebnisfelder verpflichtend (siehe Punkt 4)
- `failure`:
  - keine erfundenen Fachsections; klare Fallback-/Blockdiagnostik

#### 4. Execution-Result-Vertrag (verbindlich)
Bei `result_type=execution_result` müssen mindestens enthalten sein:
- `execution_summary`
- `execution_scope`
- `execution_artifacts` (z. B. patch refs, changed targets)
- `execution_verification` (z. B. checks/tests status)
- `execution_outcome_status`

Ohne diese Felder ist `execution_result` unzulässig.

#### 5. Normative Kopplung an Mutation (verbindlich)
`execution_result` darf nur gesetzt werden, wenn eine validierte Execution aus Foundation 16 vorliegt.

Pflichtnachweis:
- `execution_ref` (opaque, nachvollziehbare Referenz)
- `mutation_policy_status`
- `write_scope_status`

Fehlt der Nachweis:
- `result_type` muss auf `recommendation` oder `failure` fallen
- Diagnosecode `execution_claim_without_mutation` verpflichtend

#### 6. Konsistenzregeln für Status und Done-Reason (verbindlich)
- `done_reason`-Semantik aus Foundation 02 bleibt normativ führend.
- `result_type` darf `done_reason` nicht widersprechen.
- Widersprüche werden als `contract_semantic_conflict` diagnostiziert.

#### 7. Section-Contribution-Mapping (verbindlich)
V2 verlangt explizite Mapping-Regeln:
- analysis-contributions -> Analyse-Sections
- proposal-contributions -> Proposal-Sections
- execution-contributions -> Execution-Sections

Mis-Mapping (z. B. execution payload in proposal section) muss validierungsrelevant sein.

#### 8. Human-View-Regeln V2 (verbindlich)
Human-Views müssen klar anzeigen:
- Ergebnisart (`analysis|recommendation|execution_result|failure`)
- verfügbare vs. nicht anwendbare Sections
- zentrale Block-/Fallback-Hinweise

Views dürfen nie aus `recommendation` implizit ein `execution_result` formulieren.

### V2-Design (Integrationspunkte)

#### Zielstruktur (Erweiterung)
- `core/output_contract_foundation.py`
  - `ResultTypeClassifier`
  - `SectionApplicabilityResolver`
  - `ContractSemanticValidator`
- `core/output_sections_proposal.py`
  - Builder für Proposal-/Plan-Sections
- `core/output_sections_execution.py`
  - Builder für Execution-Sections

#### Modell-Erweiterungen
- `OutputContract`
  - ergänzt um `result_type`, `result_status`, `maturity_state`, `execution_ref` (optional)
- `SectionBuilderResult`
  - ergänzt um `applicability_reason`, `source_phase`
- `ContractDiagnostic`
  - ergänzt um `semantic_conflict_scope`, `expected_result_type`, `actual_result_type`

#### API-Erweiterungen
- `classify_result_type(run_state, orchestration_outcome, execution_state) -> ResultType`
- `resolve_section_applicability(result_type, section_name) -> SectionStatus`
- `validate_contract_semantics(contract) -> list[ContractDiagnostic]`
- `build_execution_result_section(...) -> dict`
- `build_proposal_sections(...) -> dict[str, SectionBuilderResult]`

#### Integrationspunkte zu anderen Foundations
- Foundation 01:
  - liefert phasenbezogene section contributions
- Foundation 02:
  - liefert Reifegrad-/Done-Reason-Semantik
- Foundation 06:
  - liefert Proposal-/Impact-/Alternative-/Plan-Artefakte
- Foundation 11:
  - Eventing für Result-Type-Klassifikation und Contract-Validation
- Foundation 13:
  - Proposal-Sections folgen Proposal-Vertrag
- Foundation 16:
  - liefert Execution-Nachweise für `execution_result`

#### Migrationsansatz (V2)
1. `result_type` zunächst diagnostisch ergänzen.
2. Proposal-Sections zentral einführen und mode-lokale Varianten ablösen.
3. Semantic-Validator für `result_type` vs. `done_reason` aktivieren.
4. `execution_result` nur noch mit Foundation-16-Nachweis erlauben.
5. Human-Views auf explizite Ergebnisartdarstellung umstellen.

#### Verbindliche V2-Regel
Ein Contract darf nur dann `result_type=execution_result` tragen, wenn eine valide Execution aus Foundation 16 nachweisbar ist; andernfalls ist mindestens auf `recommendation` zurückzustufen.
