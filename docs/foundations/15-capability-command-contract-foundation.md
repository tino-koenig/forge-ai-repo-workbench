# Foundation 15: Capability / Command Contract Foundation

## Zweck
Formaler Vertrag für Forge-Capabilities (`query`, `explain`, `describe`, `review`, später `propose`, `implement`, `apply`).

## Kernidee
Interne Foundations können nur dann stabil wirken, wenn die äußere Capability-Schnittstelle ebenso formal ist.

## Was sie umfasst
- Capability-ID + Version
- Input-Verträge
- Output-Verträge pro Capability
- erlaubte Modes/Stages/Tasks/Foundation-Nutzung
- verpflichtende Output-Sections
- capability-spezifische Constraints
- Migration/Deprecation-Regeln

## Erwarteter Umfang
Mittel bis groß

## Aufwand für Realisierung
Mittel bis hoch

## Priorität
P1

## Risiken
- Capability-Grenzen bleiben unscharf und überlappen
- Breaking Changes erfolgen ohne saubere Versionierung
- Required Sections driften zwischen Capabilities auseinander

## Erfolgskriterium
Jede Capability ist versioniert, validierbar und mit klaren Input-/Output-Verträgen sowie Scope-Grenzen definiert.

## Konzept

### Problem
Ohne formalen Capability-Vertrag bleiben CLI/API-Oberflächen und interne Ausführungsgrenzen instabil. Das führt zu Inkompatibilitäten und erschwert Migration.

### Ziel
- Formale Capability-Definition als verlässliche Außenkante.
- Klare Zuordnung: Welche Capability darf welche Stages/Tasks/Sections nutzen.
- Versionierte Evolution ohne stilles Brechen.

### Nicht-Ziele
- Keine Vorgabe der internen Implementierungsdetails pro Mode.
- Kein Ersatz für Output-Contract-Semantik (Foundation 10).

### Leitprinzipien
- contract-first interface
- explicit capability boundaries
- versioned compatibility
- stable validation paths

## Spezifikation

### 1. Capability-Vertrag
Pflicht:
- `capability_id`
- `capability_version`
- `input_schema_ref`
- `output_schema_ref`
- `allowed_actions`
- `required_sections`
- `allowed_foundations`
- `result_type_support` (z. B. `analysis|recommendation|execution_result`; `recommendation` entspricht Orchestration-`proposal`)

### 2. Kompatibilität und Versionierung
- breaking changes nur über neue Capability-Version
- alte Versionen mit klaren Deprecation-Fenstern
- additive Felder/Sections sind minor-kompatibel

### 3. Eingabevertrag
- Input muss gegen `input_schema_ref` validiert werden.
- capability-spezifische Constraints (z. B. Target-Pflicht) sind Teil des Vertrags.

### 4. Ausgabevertrag
- Output muss `output_schema_ref` erfüllen.
- `required_sections` sind capability-spezifisch verpflichtend oder mit `not_applicable` zu kennzeichnen.

### 5. Allowed-Actions-/Foundation-Grenzen
- Capability darf nur deklarierte Actions und Foundations nutzen.
- Verstöße sind als `capability_contract_violation` zu diagnostizieren.

### 6. Deprecation-Vertrag
- Deprecated Versionen tragen Ablaufdatum/Fenster.
- Migrationhinweise müssen maschinenlesbar referenzierbar sein.

## Design

### Zielstruktur (Vorschlag)
- `core/capability_contracts.py`
- `core/capability_registry.py`
- `core/capability_validation.py`

### API-Skizze
- `resolve_capability_contract(capability, version) -> CapabilityContract`
- `validate_capability_io(capability_contract, payload) -> ValidationResult`
- `validate_capability_execution_scope(contract, plan) -> ScopeValidationResult`
- `resolve_capability_deprecation(contract, now) -> DeprecationStatus`

### Integrationspunkte
- Foundation 01/02: erlaubte Stages/Actions aus Capability-Vertrag
- Foundation 10: required sections und result_type support
- Foundation 14: capability-bezogene normative Grenzen
- Foundation 11: Telemetrie zu Contract-Verstößen/Deprecation-Nutzung

## Verbindlicher Vertragskern (jetzt)

Diese Punkte sind in Foundation 15 verpflichtend:
- versionierte Capability-Verträge mit klarer Scope-Definition
- Input/Output-Validation gegen Vertrag
- deklarierte Required-Sections und allowed foundations/actions
- kompatible Evolutionsregeln mit Deprecation-Fenstern

## Bewusst verschoben (spätere Detailphasen)

- capability-spezifische Compatibility-Tools
- automatische Migrationshinweise für Nutzer
- capability profile negotiation für API-Clients

## Detaillierungsregel

Foundation 15 definiert die äußere Systemoberfläche, nicht deren interne Implementierung.
