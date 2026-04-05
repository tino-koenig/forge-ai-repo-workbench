# Foundation 04: Runtime Settings Foundation

## Zweck
Zentrale, typisierte Auflösung von Runtime-Settings mit validierten Grenzen und klarer Quellen- und Diagnoseangabe.

## Kernidee
- ein Resolver für `int/float/bool/enum/str`
- einheitliches Verhalten bei Defaults, Invalid-Values, Unknown Keys und Bounds
- effektive Quelle immer sichtbar (`default`, `repo`, `local`, `cli`)
- fehlgeschlagene Quellenversuche nachvollziehbar

## Was sie umfasst
- Parser/Validator
- Bound-Handling
- Source-Tracking
- Diagnostics mit stabilen Codes
- typisierte Setting-Schemas
- Registry für zentrale Defaults und Regeln

## Beispiel
`review.findings.max_items` und `explain.edges.max_items` werden über denselben Resolver validiert.

## Erwarteter Umfang
Klein bis mittel

## Aufwand für Realisierung
Klein bis mittel

## Priorität
P1

## Risiken
- zu permissive Fallbacks verstecken Konfigurationsfehler
- inkonsistente Schemas pro Mode
- unklare Ownership der zentralen Registry

## Erfolgskriterium
Keine mode-lokalen `_resolve_runtime_*`-Doppelungen mehr.

## Konzept

### Problem
Aktuell existieren mehrere mode-lokale Resolver (`_resolve_runtime_int`, `_resolve_runtime_bool`, `_resolve_runtime_number`) mit leicht unterschiedlichem Verhalten. Dadurch entstehen Inkonsistenzen bei Defaults, Grenzwerten, Fehlerbehandlung, Unknown Keys und Source-Tracking.

### Ziel
- Einheitliche Runtime-Settings-Auflösung für alle Modes.
- Klare, nachvollziehbare Herkunft jedes effektiven Werts.
- Vorhersagbares Verhalten bei ungültigen Werten.
- Eine zentrale Quelle der Wahrheit für Defaults, Bounds und erlaubte Werte.

### Nicht-Ziele
- Keine neue Konfigurationssprache.
- Keine versteckte Auto-Korrektur komplexer Fehler.
- Keine mode-spezifische Fachlogik in der Foundation.
- Kein freies Transformationssystem für beliebige Normalisierungen.

### Leitprinzipien
- Explizit statt implizit.
- Typisiert statt String-basiert.
- Fehlertolerant, aber nicht stumm (Warnings/Diagnostics statt stilles Verschlucken).
- Resolver-Kern rein funktional: keine Ausgabe, kein Logging, keine Seiteneffekte.

## Spezifikation

### 1. Scope und Typen
Die Foundation muss mindestens unterstützen:
- `int`
- `float`
- `bool`
- `enum` (Whitelist)
- `str`

Optional später:
- `list[str]`

`float` ist zunächst ein technischer Zahlentyp. Fachlich präzisere Numerik ist nicht Teil dieser Foundation.

### 2. Input-Quellen und Priorität
Verbindliche Priorität (höchste zuerst):
1. CLI/runtime override
2. `.forge/config.local.toml`
3. `.forge/config.toml`
4. Default (Schema)

Jede Auflösung liefert den effektiven Wert plus `source`.
Zusätzlich müssen fehlgeschlagene Quellenversuche diagnostisch nachvollziehbar bleiben.

### 3. Validierung
Je Setting müssen Schema-Regeln definierbar sein:
- Typ
- optional `min`/`max` für numerische Werte
- optional erlaubte Werte für `enum`
- optionale einfache Normalisierung (`strip`, `lowercase`)
- optional Steuerung, ob Default-Fallback erlaubt ist

### 4. Verhalten bei Invalid-Input
- Bei ungültigem Wert gilt: Fallback auf nächstniedrigere Quelle.
- Wenn keine Quelle gültig ist: Fallback auf Schema-Default, sofern erlaubt.
- Diagnose-Eintrag wird erzeugt (mindestens key, raw_value, source, reason, fallback_source, code).
- Runtime-Auflösung bleibt tolerant; Validierung/Doctor darf dieselben Fälle strenger als Fehler bewerten.

### 5. Unknown Keys
- Keys ohne Registry-Eintrag werden zur Runtime ignoriert, aber diagnostiziert.
- `doctor/config validate` muss Unknown Keys als validierungsrelevanten Befund sichtbar machen.

### 6. Ergebnisformat
Resolver-Ausgabe pro Key:
- `value` (typisiert)
- `source` (`cli|local|repo|default`)
- `diagnostics` (0..n Einträge)

Diagnostics sollen stabile Codes verwenden, z. B. `invalid_type`, `out_of_bounds`, `unknown_enum_value`, `unknown_key`.

### 7. Stabilitätsanforderung
- Gleiches Input-Set muss deterministisch gleiches Ergebnis liefern.
- Keine mode-spezifischen Sonderfälle im Resolver-Kern.
- Defaults, Bounds und Allowed Values kommen ausschließlich aus Registry/Schema.

## Design

### Zielstruktur (Vorschlag)
- `core/runtime_settings.py`
  - zentrale Resolve-API
  - Schema- und Typ-Modelle
  - Diagnosemodell
- `core/runtime_settings_registry.py`
  - Key-Registry + Defaults + Bounds
  - modeübergreifende Deklaration

### Datenmodelle (konzeptionell)
- `SettingSpec`
  - `key`, `kind`, `default`, `min`, `max`, `allowed_values`, `normalize`, `allow_default_fallback`
- `ResolvedSetting`
  - `key`, `value`, `source`, `diagnostics`
- `SettingDiagnostic`
  - `key`, `raw_value`, `source`, `reason`, `fallback_source`, `code`

### Registry-Regeln
- Jeder Setting-Key wird genau einmal zentral definiert.
- Keine Schatten-Definitionen in Modes.
- Änderungen an Defaults, Bounds oder Allowed Values erfolgen nur über Registry/Schema.

### API-Skizze
- `resolve_setting(key, sources, registry) -> ResolvedSetting`
- `resolve_settings(keys, sources, registry) -> dict[str, ResolvedSetting]`

### Integrationsplan
1. Foundation implementieren und mit Unit-Tests absichern.
2. `query` auf zentralen Resolver migrieren.
3. `explain`, `describe`, `review`, `ask` migrieren.
4. Mode-lokale `_resolve_runtime_*` entfernen.
5. Diagnostics in `doctor/config validate` sichtbar machen.
6. Runtime-Settings-Auflösung und Diagnostics in `sections.runtime_settings` (Foundation 10) standardisieren.

### Migrationsstrategie
- In Phase 1 Parallelbetrieb erlauben (alte Helper + neue Foundation).
- In Phase 2 harte Umschaltung pro Mode.
- In Phase 3 Altcode löschen und Quality Gates auf zentrale Nutzung setzen.

### Risiken im Design
- Zu breite Registry ohne klare Ownership.
- Zu viele optionale Schema-Felder erschweren Konsistenz.
- Zu tolerante Runtime-Nutzung verdeckt fehlerhafte Repo-Konfiguration.

### Gegenmaßnahmen
- Klare Registry-Konventionen pro Key.
- Pflichtfelder pro Setting (`key`, `kind`, `default`).
- Quality-Gate: keine neuen mode-lokalen Runtime-Resolver.
- Klare Trennung zwischen toleranter Runtime-Auflösung und strenger Validierung.

## Verbindlicher Vertragskern (jetzt)

Diese Punkte sind in Foundation 04 verpflichtend:
- zentraler typisierter Resolver mit stabiler Quellenpriorität
- einheitliche Schema-/Bound-Validierung
- strukturierte Diagnostics mit stabilen Codes
- zentrale Registry als einzige Quelle für Defaults/Bounds/Allowed Values
- standardisierte Ausgabe in `sections.runtime_settings` (Foundation 10)

## Bewusst verschoben (spätere Detailphasen)

Diese Punkte werden nachgelagert konkretisiert:
- erweiterte Typen (z. B. verschachtelte Strukturen)
- differenzierte Modusprofile für strikte/tolerante Runtime-Auflösung
- automatische Konfigurationsvorschläge aus Diagnosen

## Detaillierungsregel

Foundation 04 definiert den stabilen Runtime-Settings-Vertrag.  
Erweiterte Schematypen und Komfortmechanismen werden in Feature-Dokumenten konkretisiert.

## V2-Erweiterungen (Proposal-/Mutation-bezogene Settings)

### V2-Konzept

#### Problem
Mit Einführung von Proposal- und Execution-Pfaden reichen rein technische Runtime-Settings nicht mehr aus. Es fehlen:
- explizite Settings für Proposal-Tiefe und Impact-Granularität
- konsistente Steuerung erlaubter Änderungsintentionen
- klare Wirksamkeitsgrenzen für mutation-nahe Settings ohne Policy-Kontext

Ohne diese Trennung entsteht Konfigurationsdrift zwischen „Analyse-Settings“ und „Change-Settings“.

#### Zielbild
Runtime-Settings werden in V2 domänenspezifisch gegliedert:
1. `analysis.*`
2. `proposal.*`
3. `execution.*`
4. `write_scope.*` und `mutation.*` (nur wirksam im Policy-/Execution-Kontext)

Zusätzlich wird pro Setting nicht nur der Wert, sondern auch die Wirksamkeit (`effective|limited|blocked`) geführt.

#### Leitprinzipien (V2)
- settings sind deklarativ und typisiert, nicht implizit
- mutation-nahe settings sind niemals autonom wirksam
- gleiche Auflösungssystematik für alle Settings, unabhängig vom Mode
- begrenzte, transparente Normalisierung statt stiller Umdeutung

### V2-Spezifikation (Vertragskern)

#### 1. V2-Setting-Domänen (verbindlich)
Neue Gruppen im Registry-Schema:
- `proposal.depth`
- `proposal.impact.depth`
- `proposal.alternatives.max`
- `proposal.allowed_change_intents`
- `execution.mode`
- `execution.guard_level`
- `write_scope.paths`
- `write_scope.targets`
- `mutation.mode` (`none|proposal_only|patch_only|apply`)
- `mutation.require_human_review` (bool)

Regel:
- Jede Gruppe ist zentral registriert.
- Mode-lokale Ad-hoc-Settings für dieselbe Semantik sind unzulässig.

#### 2. Wirksamkeitsstatus je Setting (verbindlich)
`ResolvedSetting` wird erweitert um:
- `effect_status`: `effective|limited|blocked`
- `effect_reason_code`
- `required_contexts[]` (z. B. `policy`, `execution_phase`, `human_approval`)

Damit kann ein Setting formal „gesetzt“, aber im aktuellen Lauf nicht wirksam sein.

#### 3. Kontextgebundene Wirksamkeit (verbindlich)
Mutation-nahe Settings (`write_scope.*`, `mutation.*`) sind nur wirksam, wenn:
- Foundation 14 Policy-Kontext aktiv und positiv
- Foundation 16 Execution-Kontext aktiv
- erforderliche Freigaben erfüllt

Wenn nicht erfüllt:
- `effect_status=limited` oder `blocked`
- Diagnose mit stable code, z. B. `context_missing_policy`, `context_missing_execution_phase`, `context_missing_human_approval`

#### 4. Proposal-Tiefensteuerung (verbindlich)
Proposal-relevante Settings müssen mindestens folgende steuerbare Achsen besitzen:
- Tiefengrad (`shallow|standard|deep`)
- Impact-Tiefe (`low|medium|high`)
- Alternativenumfang (`0..N`)

Diese Settings dürfen:
- LLM-Taskauswahl (Foundation 06) beeinflussen
- Output-Sections (Foundation 10) erweitern/reduzieren

Sie dürfen nicht:
- deterministische Sicherheits-/Policy-Entscheidungen übersteuern

#### 5. Allowed-Intents-Vertrag (verbindlich)
`proposal.allowed_change_intents` ist eine typisierte Whitelist.

Regeln:
- nur registrierte Intents zulässig (z. B. `add|replace|extract|remove|move|adapt_tests`)
- unbekannte Intents werden diagnostiziert und ignoriert
- leere effektive Intent-Menge bei required Proposal führt zu `proposal_limited`

#### 6. Quellenpriorität und Override-Regeln (verbindlich)
Die v1-Quellenpriorität bleibt unverändert.
Zusatz:
- sicherheitskritische Settings können als „nicht per niedriger Quelle überschreibbar“ markiert werden
- Konflikte werden diagnostiziert (`override_blocked_by_policy_tier`)

#### 7. Trace-/Output-Vertrag V2 (verbindlich)
`sections.runtime_settings` muss zusätzlich enthalten:
- `effect_status` pro Schlüssel
- `inactive_due_to_context[]`
- `policy_coupled_settings[]`
- `mutation_coupled_settings[]`

Damit ist sichtbar, welche Settings zwar gesetzt, aber absichtlich nicht wirksam sind.

#### 8. Stabilitätsregel (verbindlich)
Bei identischem Input + identischem Kontext muss identische
- Auflösung,
- Wirksamkeitsklassifikation,
- Diagnostik
entstehen.

### V2-Design (Integrationspunkte)

#### Zielstruktur (Erweiterung)
- `core/runtime_settings.py`
  - `SettingsEffectEvaluator`
  - `ContextRequirementChecker`
- `core/runtime_settings_registry.py`
  - V2-Domänengruppen und Intent-Register
- `core/runtime_settings_policies.py`
  - Quellen-/Override- und Kontext-Wirksamkeitspolicies

#### Modell-Erweiterungen
- `SettingSpec`
  - ergänzt um `required_contexts`, `safety_tier`, `allowed_override_sources`
- `ResolvedSetting`
  - ergänzt um `effect_status`, `effect_reason_code`, `required_contexts`
- `SettingDiagnostic`
  - ergänzt um `context_snapshot_id`, `policy_version` (falls relevant)

#### API-Erweiterungen
- `resolve_settings_with_effects(keys, sources, registry, context) -> dict[str, ResolvedSetting]`
- `evaluate_setting_effect(setting, context, policy_state) -> EffectEvaluation`
- `collect_runtime_setting_diagnostics(resolved_settings) -> list[SettingDiagnostic]`

#### Integrationspunkte zu anderen Foundations
- Foundation 01:
  - Stage-/Phasenkontext für Wirksamkeitsprüfung
- Foundation 02:
  - Ziel-Reifegrad beeinflusst erforderliche Setting-Wirksamkeit
- Foundation 03:
  - Budgetprofile können über effektive Settings phasenbezogen geschärft werden
- Foundation 06:
  - LLM-Taskkonfiguration konsumiert effektive Proposal-Tiefensettings
- Foundation 10:
  - standardisierte Ausgabe inkl. `effect_status`
- Foundation 11:
  - Events für `limited/blocked` Setting-Wirksamkeit
- Foundation 14/16:
  - normative Kopplung für write/mutation-nahe Settings

#### Migrationsansatz (V2)
1. Neue Felder (`effect_status`, `required_contexts`) zunächst diagnostisch ergänzen.
2. Proposal-Domänenkeys zentral registrieren und mode-lokale Varianten ablösen.
3. Mutation-nahe Settings auf Kontextprüfung umstellen.
4. Output-Section `runtime_settings` um Wirksamkeitsdetails erweitern.
5. Quality Gate: keine direkte Nutzung von mutation-nahen Settings ohne Effect-Evaluation.

#### Verbindliche V2-Regel
Write-/Mutation-Settings sind ohne gültigen Policy- und Execution-Kontext nicht wirksam; sie müssen als `limited` oder `blocked` mit stabilem Diagnosecode ausgewiesen werden.
