# Foundation 14: Trust & Safety / Policy Foundation

## Zweck
Zentrale normative Regeln für Zugriff, Schreiben, externe Quellen, Write-Scopes und Block-Entscheidungen.

## Kernidee
Policy ist eine eigene normative Schicht und darf nicht verteilt in Modes/Helpers versteckt sein.

## Was sie umfasst
- Access-Policies (`web`, `repo`, `docs`, `index`, `external`)
- Write-Policies (`none|proposal_only|patch_only|apply`)
- Write-Scopes (repo/pfad/datei, später symbol-nah)
- Transition-/Mode-Gates
- Policy-Entscheidungen (`allowed|blocked|limited`)
- Policy-Provenienz, Version, Rule-ID
- normierte Policy-Diagnostics
- Integrationsregeln zu 02/10/11/16

## Erwarteter Umfang
Groß

## Aufwand für Realisierung
Hoch

## Priorität
P1

## Risiken
- Policy-Regeln sind zu breit und blockieren legitime Flows
- verteilte Sonderregeln umgehen den zentralen Policy-Kern
- uneinheitliche Policy-Diagnosen erschweren Audit und Debugging

## Erfolgskriterium
Jede Block-/Limit-/Allow-Entscheidung ist zentral, versioniert und mit Rule-ID nachvollziehbar.

## Konzept

### Problem
Wenn normative Regeln in einzelnen Modes/Helpern verteilt sind, entstehen Inkonsistenzen und nicht reproduzierbare Sicherheitsentscheidungen.

### Ziel
- Eine zentrale normative Kontrollschicht für Read/Write/Network/Transition.
- Einheitliche Entscheidungen und Diagnosen für alle Foundations.
- Klare Trennung von Policy-Entscheidung (14) und technischer Ausführung (19/20/16).

### Nicht-Ziele
- Keine Fachlogik-Entscheidungen (Ranking/Retrieval/etc.).
- Kein stilles Auto-Heilen von Policy-Verstößen.

### Leitprinzipien
- normative first
- deny by default where unclear
- versioned rules, stable diagnostics
- policy decisions are explicit artifacts

## Spezifikation

### 1. Policy-Entscheidungsvertrag
Pflichtfelder:
- `decision` (`allowed|blocked|limited`)
- `policy_version`
- `rule_id`
- `scope`
- `reason_code`
- `diagnostics[]`

### 2. Policy-Dimensionen
Mindestens:
- `access_policy` (`repo|web|docs|index|external`)
- `write_policy` (`none|proposal_only|patch_only|apply`)
- `network_policy`
- `transition_policy` (mode-/phase-übergänge)

### 3. Durchsetzungsregeln
- keine Write-Aktion ohne positive Write-Policy
- keine Scope-Überschreitung ohne Block
- policy block ist normativer terminaler Zustand
- `limited` muss konkret ausweisen, welche Teiloperationen erlaubt bleiben

### 4. Policy-Transparenz
- Jede Entscheidung enthält `policy_source` (woher Regel stammt).
- Kaskadierte Regelanwendung muss in diagnostischer Reihenfolge nachvollziehbar sein.

### 5. Konfliktauflösung
Bei konkurrierenden Regeln:
- deterministische Priorität (`block > limited > allow`)
- Konflikt als `policy_conflict_resolved` diagnostizieren

### 6. Integritätsregeln
- Policy-Entscheidungen sind immutable pro Entscheidungsschritt.
- Nachträgliche Überschreibung ohne neue Entscheidung ist unzulässig.

## Design

### Zielstruktur (Vorschlag)
- `core/policy_foundation.py`
- `core/policy_rules.py`
- `core/policy_diagnostics.py`
- `core/policy_resolution.py`

### API-Skizze
- `evaluate_policy(action, context) -> PolicyDecision`
- `validate_write_scope(targets, policy) -> PolicyDecision`
- `resolve_policy_conflicts(rule_results) -> PolicyDecision`
- `explain_policy_decision(decision) -> PolicyExplanation`

### Integrationspunkte
- Foundation 02: terminale normative Gründe und Gate-Steuerung
- Foundation 10: Policy-Verletzungen und Limits im Output-Vertrag
- Foundation 11: Policy-Events, Rule-IDs, Entscheidungspfad
- Foundation 16/19/20/21: write-/execution-/vcs-pfade nur mit positivem Policy-Bescheid

## Verbindlicher Vertragskern (jetzt)

Diese Punkte sind in Foundation 14 verpflichtend:
- zentrale Policy-Entscheidung mit Version/Rule-ID/Reason-Code
- einheitliche `allowed|blocked|limited`-Semantik
- deterministische Konfliktauflösung
- standardisierte Policy-Diagnostics mit Herkunft
- keine implizite Ausführung ohne vorgelagerte Policy-Entscheidung

## Bewusst verschoben (spätere Detailphasen)

- feinere symbol-/diff-basierte Write-Scopes
- policy simulation und what-if checks
- policy impact analytics über Run-Historie

## Detaillierungsregel

Foundation 14 ist die normative Kontrollschicht für alle read/write-pfade.
