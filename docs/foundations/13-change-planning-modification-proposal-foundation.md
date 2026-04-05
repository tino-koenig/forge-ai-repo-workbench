# Foundation 13: Change Planning / Modification Proposal Foundation

## Zweck
Standardisierter Vertrag für belastbare Änderungsvorschläge vor jeder optionalen Umsetzung.

## Kernidee
Forge erzeugt zuerst strukturierte Proposals (was/warum/wo/wie/risiko), statt direkt zu mutieren.

## Was sie umfasst
- Proposal-Request (`intent`, `goal`, `constraints`, `scope`, `mode`)
- Proposal-Status (`proposed|partial|blocked|uncertain`)
- betroffene Targets (Dateien/Symbole/Tests/Config)
- Änderungsintentionen (`add|extract|replace|wire|remove|move|adapt_tests|...`)
- empfohlene Schrittfolge
- Impact-/Abhängigkeitsanalyse
- Risiken/Unsicherheiten/Annahmen
- Alternativen
- Confidence / Proposal-Qualität
- Human-review-Signal
- Abgrenzung zu echter Mutation

## Erwarteter Umfang
Groß

## Aufwand für Realisierung
Hoch

## Priorität
P1

## Risiken
- Proposal-Outputs sind zu vage und nicht umsetzbar
- Proposal wirkt mutierend, obwohl nur planend gemeint
- fehlende Evidenzketten führen zu Scheinsicherheit

## Erfolgskriterium
Jeder Änderungsvorschlag ist evidenzgebunden, risikoklassifiziert, alternativfähig und klar von Mutation getrennt.

## Konzept

### Problem
Ohne formalen Proposal-Vertrag springen Systeme von Analyse direkt zu Ausführung oder erzeugen unverbindliche Empfehlungen ohne klare Umsetzbarkeit.

### Ziel
Belastbare, auditierbare Änderungsplanung als Brücke zwischen Verstehen (07/08/09) und Ausführen (16).

### Nicht-Ziele
- Keine direkte Dateiänderung.
- Kein Ersatz für Policy-Entscheidung (14) oder Mutation (16).
- Keine reine Freitext-Empfehlung ohne strukturierten Vertrag.

### Leitprinzipien
- proposal first, execution second
- evidenzgebundene Schritte
- explizite Unsicherheit statt impliziter Annahmen
- Human-Review als kontrollierter Übergabepunkt

## Spezifikation

### 1. Proposal-Vertrag
Pflichtfelder:
- `proposal_id`
- `proposal_contract_version`
- `status` (`proposed|partial|blocked|uncertain`)
- `intent`
- `scope`
- `targets[]`
- `steps[]`
- `risks[]`
- `assumptions[]`
- `alternatives[]`
- `confidence`
- `human_review_required`

### 2. Step-Vertrag
Jeder Schritt enthält mindestens:
- `step_id`
- `change_intent` (`add|extract|replace|wire|remove|move|adapt_tests|...`)
- `target_refs[]`
- `rationale`
- `evidence_refs[]`
- `preconditions[]`
- `verification_hint`

### 3. Qualitäts- und Gating-Regeln
- Jeder Schritt muss auf mindestens eine Evidenzreferenz zeigen.
- Blocker müssen als eigene Einträge mit Blockgrund codiert sein.
- `status=proposed` ist nur zulässig, wenn keine harten Blocker offen sind.
- Proposal ohne `human_review_required`-Bewertung darf nicht in Mutation übergehen.
- `status=blocked|uncertain` darf nicht als execution-ready interpretiert werden.

### 4. Impact- und Abhängigkeitsmodell
Proposal enthält:
- `impact_scope` (betroffene Komponenten)
- `dependency_touchpoints[]`
- `test_implications[]`
- `config_implications[]`

### 5. Alternativen-Vertrag
Wenn Alternativen vorhanden:
- jede Alternative enthält `tradeoffs`, `risk_delta`, `effort_hint`
- eine `recommended_option` ist optional, aber begründungspflichtig

### 6. Abgrenzung zu Mutation
- Proposal darf keine write-affecting Operation enthalten.
- Jede mögliche Umsetzung muss als Übergabeobjekt für Foundation 16 formuliert sein.

## Design

### Zielstruktur (Vorschlag)
- `core/proposal_foundation.py`
- `core/proposal_models.py`
- `core/proposal_quality.py`
- `core/proposal_diagnostics.py`

### API-Skizze
- `build_change_proposal(request, context) -> ProposalResult`
- `evaluate_proposal_quality(proposal) -> ProposalQuality`
- `validate_proposal_transition(proposal, policy_context) -> TransitionDecision`
- `summarize_proposal_risks(proposal) -> ProposalRiskSummary`

### Integrationspunkte
- Foundation 07/08/09: liefert Evidenz, Ranking, Zielauflösung
- Foundation 10: standardisierte Proposal-Sections
- Foundation 11: Proposal-Events und Entscheidungsdiagnostik
- Foundation 14: normative Prüfungen vor Transition
- Foundation 16: nutzt Proposal als Eingabe für kontrollierte Execution

## Verbindlicher Vertragskern (jetzt)

Diese Punkte sind in Foundation 13 verpflichtend:
- standardisiertes, statusbasiertes Proposal-Format
- evidenzgebundene Schrittstruktur mit Zielreferenzen
- explizite Risiko-/Annahmen-/Alternativenfelder
- klare Transition-Grenze zu Foundation 16 mit Human-Review-Signal

## Bewusst verschoben (spätere Detailphasen)

- automatische Alternativen-Generierung mit tiefer Kostenabschätzung
- proposal ranking über historische Erfolgsdaten
- teilautomatische Vorschlagskonsolidierung über mehrere Runs

## Detaillierungsregel

Foundation 13 definiert Planung, nicht Ausführung.
