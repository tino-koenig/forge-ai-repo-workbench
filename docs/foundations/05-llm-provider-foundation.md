# Foundation 05: LLM Provider Foundation

## Zweck
Stabile Provider-Schicht für Completion, Usage und Kosten.

## Kernidee
- capability-unabhängige LLM-Basis
- klare Provider-Fehlerbilder und Timeouts
- einheitliches Usage-/Cost-Objekt

## Was sie umfasst
- Provider-Adapter (`openai_compatible`, `mock`, später weitere)
- Token- und Kosten-Ermittlung
- Retries/Timeouts

## Beispiel
Ein LLM-Task ruft `provider_complete(...)` auf und erhält `text + usage + cost`.

## Erwarteter Umfang
Klein bis mittel (vieles bereits vorhanden)

## Aufwand für Realisierung
Klein bis mittel

## Priorität
P2

## Risiken
- Vermischung mit task-spezifischer Logik
- fehlende Testbarkeit bei Providerfehlern

## Erfolgskriterium
Keine capability-spezifische Prompt-/Parse-Logik in der Provider-Schicht.

## Konzept

### Problem
Provider-nahe Aufgaben (HTTP, Auth, Timeout, Usage/Cost) und task-spezifische Aufgaben (Planner/Refinement/Decision) können leicht vermischt werden. Das macht Wechsel von Modellen/Providern riskant und erschwert Tests.

### Ziel
- Stabile, austauschbare Provider-Schicht als technischer Unterbau.
- Einheitliches Completion- und Usage-Verhalten über alle Provider.
- Saubere Trennung zu Foundation 06 (LLM Tasks).

### Nicht-Ziele
- Keine task-spezifische Prompt-/Parser-Logik.
- Keine Mode-spezifische Entscheidungspolitik.
- Kein direktes Scheduling/Orchestration.

### Leitprinzipien
- Provider-agnostische Kern-API.
- Klare Fehlerklassen statt Freitext-Ausnahmen.
- Reproduzierbare Usage-/Cost-Metrik.

## Spezifikation

### 1. Provider-Scope
Muss mindestens unterstützen:
- `mock`
- `openai_compatible`

Erweiterbar:
- weitere Provider über Adapter-Interface

### 2. Einheitliches Completion-Result
Jeder Provider liefert:
- `provider_contract_version`
- `text` (normalisierter Primärausgang)
- `usage` (`prompt_tokens`, `completion_tokens`, `total_tokens`, `source`)
- `cost` (wenn konfigurierbar, inkl. Herkunft)
- `provider_meta` (modell, endpoint, latency)
- `error` (strukturierter Providerfehler oder `None`)

### 3. Fehlerklassen (verbindlich)
Mindestens:
- `provider_config_error`
- `provider_auth_error`
- `provider_network_error`
- `provider_timeout_error`
- `provider_response_error`

Fehler müssen strukturiert zurückgegeben werden und dürfen nicht unklassifiziert bleiben.

### 4. Timeout/Retry-Regeln
- Timeout ist verpflichtend konfigurierbar.
- Retry nur bei transienten Fehlern.
- Retry-Policy ist zentral parametrisierbar (Anzahl, Delay-Profil).

### 5. Usage-/Cost-Vertrag
- Wenn Provider Token liefert, werden sie unverändert übernommen.
- Wenn `total_tokens` fehlt, darf es nur aus verlässlich vorliegenden `prompt_tokens` + `completion_tokens` deterministisch berechnet werden.
- Cost nur berechnen, wenn Pricing vollständig konfiguriert ist; die Herkunft des Kostenwerts muss sichtbar bleiben (`provider_reported|configured_estimate|unknown`).
- Unbekannte Werte werden als `unknown` gekennzeichnet, nicht erfunden.

### 6. Prompt-Handling-Grenze
- Provider-Layer lädt/rendered keine Task-Templates.
- Provider-Layer akzeptiert fertig vorbereitete Prompt-/Message-Payloads.
- Task-Validierung/Guardrails bleiben in Foundation 06.

### 7. Beobachtbarkeit
- Jeder Call liefert korrelierbare Metadaten (`latency_ms`, provider, model, endpoint hint).
- Events müssen in Foundation 11 integrierbar sein.

## Design

### Zielstruktur (Vorschlag)
- `core/llm_provider_foundation.py`
  - providerunabhängige API
  - Retry/Timeout-Orchestrierung
- `core/llm_provider_adapters.py`
  - konkrete Adapter (`mock`, `openai_compatible`)
- `core/llm_usage_cost.py`
  - Normalisierung von Usage/Cost

### Datenmodelle (konzeptionell)
- `ProviderRequest`
  - provider, messages_or_prompt_payload, model, temperature, max_tokens, timeout, trace_context
- `ProviderResult`
  - text, usage, cost, provider_meta, error, diagnostics
- `ProviderError`
  - code, message, class, retryable

### API-Skizze
- `provider_complete(request, settings) -> ProviderResult`
- `normalize_usage(raw_usage) -> UsagePayload`
- `estimate_cost(usage, pricing) -> CostPayload`
- `should_retry(error, policy) -> bool`

Retry-Entscheidungen erfolgen ausschließlich zentral auf Basis klassifizierter technischer Fehler. Task-spezifische Semantik darf im Provider-Layer keine Retry-Logik auslösen.

Hinweis:
- Providerfehler werden als strukturierte Felder im `ProviderResult` zurückgegeben (`error` + diagnostics), nicht als untypisierter Ausnahmefluss.

### Abgrenzung zu Foundation 06 (verbindlich)
- Foundation 05: technisch, providernah, task-neutral
- Foundation 06: taskspezifisch, schema-/guardrail-orientiert
- Keine Task-Namen oder Action-Semantik in Foundation 05
- Provider-spezifische Rohdaten dürfen intern genutzt werden, aber nicht unkontrolliert in den Kernvertrag auslaufen.

### Integrationsplan
1. Bestehende Provideraufrufe unter einheitliche ProviderResult-Struktur ziehen.
2. Usage/Cost-Normalisierung zentralisieren.
3. Foundation 06 auf neue Provider-API umstellen.
4. Alte providernahe Hilfslogik in Integrationslayern entfernen.

### Migrationsstrategie
- Phase 1: Adapter um vorhandene Implementierungen.
- Phase 2: strukturierte Fehlerklassen verpflichtend.
- Phase 3: alle LLM-Calls nur noch über Foundation 05.

### Risiken im Design
- Adapter-Leaks (provider-spezifische Felder dringen in Kern-API)
- inkonsistente Kostenlogik je Provider
- unklare Retry-Semantik

### Gegenmaßnahmen
- harte ProviderResult-Schnittstelle
- zentrale Usage/Cost-Normalisierung
- Retry-Regeln als getestete Policy-Komponente

## Verbindlicher Vertragskern (jetzt)

Diese Punkte sind in Foundation 05 verpflichtend:
- einheitliche Completion-API und Resultstruktur inklusive strukturiertem Fehlerfeld
- strukturierte Fehlerklassen
- standardisierte Usage/Cost-Normalisierung mit sichtbarer Herkunft der Werte
- klare Schichtgrenze zu Foundation 06
- korrelierbare Metadaten für Foundation 11

## Bewusst verschoben (spätere Detailphasen)

Diese Punkte werden nachgelagert konkretisiert:
- providerübergreifendes Modell-Routing
- adaptive Retry-Profile je Providerstatus
- aktive Kostenoptimierung durch Modell-/Parameterwahl

## Detaillierungsregel

Foundation 05 definiert den stabilen technischen Providervertrag.  
Task-spezifische Semantik und Guardrails liegen ausschließlich in Foundation 06.

## V2-Erweiterungen (Modellprofile pro Einsatz, optional)

### V2-Konzept

#### Problem
Ein einzelnes globales Modellsetting ist für v2 unzureichend, weil unterschiedliche Einsatzarten unterschiedliche Provider-Profile brauchen (z. B. Analyse vs. Planentwurf vs. Codeentwurf). Ohne klaren Vertrag droht:
- implizites Modell-Routing im Mode-Code
- intransparente Kosten-/Latenzschwankungen
- schwierige Reproduzierbarkeit bei Qualitätsabweichungen

#### Zielbild
Foundation 05 bleibt task-neutral, unterstützt aber deklarative Modellprofile:
- `analysis_profile`
- `planning_profile`
- `codegen_profile` (optional)
- `fallback_profile`

Zusätzlich werden Provider-Rohantworten kontrolliert referenzierbar (nicht roh ausgeschüttet) für Audit und Diagnose.

#### Leitprinzipien (V2)
- Profile steuern technische Providerwahl, nicht Task-Semantik
- Auswahl ist deklarativ, tracebar und reproduzierbar
- Rohantwortzugriff nur kontrolliert über Referenzen und Retention-Regeln
- Fallbacks bleiben explizit und diagnostiziert

### V2-Spezifikation (Vertragskern)

#### 1. Modellprofil-Vertrag (verbindlich)
`ProviderRequest` darf statt direktem Modell optional enthalten:
- `model_profile` (`analysis|planning|codegen|fallback|custom`)

Auflösung:
- `model_profile` -> konkretes `provider/model/params` Mapping aus Runtime Settings (Foundation 04)
- fehlendes Profil führt zu deterministischem Fallback oder strukturiertem Fehler (`provider_profile_missing`)

#### 2. Profilinhalte (verbindlich)
Ein Profil muss mindestens definieren:
- `provider`
- `model`
- `timeout_ms`
- `retry_policy_ref`
- optionale Parameter (`temperature`, `max_tokens`, `top_p`)

Optional:
- `cost_class` (z. B. `low|standard|high`)
- `latency_class`

#### 3. Profile-Auswahl und Überschreibung (verbindlich)
Regeln:
- task-/mode-seitig wird nur das gewünschte Profil signalisiert, nicht das konkrete Modell hartkodiert
- direkte Modellüberschreibung ist nur erlaubt, wenn die Runtime-Policy es zulässt
- jede Überschreibung wird im Result als `profile_override=true` mit Grund ausgewiesen

#### 4. Fallback-Kette (verbindlich)
V2 führt eine explizite technische Fallback-Kette:
1. primäres Profil
2. optional profildefinierte Fallback-Profile
3. globales `fallback_profile`

Jeder Fallback-Schritt muss diagnostiziert werden:
- `fallback_from_profile`
- `fallback_to_profile`
- `fallback_reason_code`

#### 5. Rohantwort-Referenzvertrag (verbindlich)
Statt unkontrollierter Rohausgabe:
- `raw_response_ref` (opaque reference)
- `raw_response_policy` (`none|redacted|full_internal`)
- `retention_class`

Regeln:
- `raw_response_ref` nur, wenn Observability/Retention aktiv konfiguriert
- redaktionspflichtige Felder dürfen nicht im Klartext in Standardausgaben landen
- direkte Rohpayload-Ausgabe in Capability-Sections ist unzulässig

#### 6. Usage-/Cost-Konsistenz über Profile (verbindlich)
Usage/Cost bleibt profilunabhängig im gleichen Kernschema.
Zusätzlich:
- `profile_id`
- `pricing_profile_id` (falls Cost geschätzt)
- `cost_confidence` (`reported|estimated|unknown`)

#### 7. Error- und Retry-Vertrag V2 (verbindlich)
Retry-Policy kann profilgebunden sein, bleibt aber technisch:
- keine task-semantischen Retry-Entscheidungen
- gleiche Fehlerklasse -> gleiche Retry-Entscheidung innerhalb desselben Profils

Wenn Profil-Policy fehlt oder inkonsistent ist:
- `provider_profile_invalid`
- kein stilles Defaulting auf unpassende Retry-Parameter

#### 8. Trace-Kern V2 (verbindlich)
Pro Call zusätzlich:
- `profile_id`
- `resolved_provider_model`
- `fallback_chain[]`
- `raw_response_ref` (optional)
- `profile_override`

### V2-Design (Integrationspunkte)

#### Zielstruktur (Erweiterung)
- `core/llm_provider_foundation.py`
  - `ProviderProfileResolver`
  - `ProviderFallbackEngine`
  - `ProviderCallExecutor`
- `core/llm_provider_profiles.py`
  - Profilmodelle und Validierung
- `core/llm_raw_response_store.py` (optional)
  - verwaltete Referenzen, Redaction, Retention

#### Modell-Erweiterungen
- `ProviderRequest`
  - ergänzt um `model_profile`, `allow_model_override`, `raw_capture_mode`
- `ProviderResult`
  - ergänzt um `profile_id`, `fallback_chain`, `raw_response_ref`, `profile_override`
- `ProviderDiagnostic`
  - ergänzt um `profile_reason_code`, `fallback_reason_code`

#### API-Erweiterungen
- `resolve_provider_profile(request, settings) -> ResolvedProviderProfile`
- `provider_complete_with_profile(request, resolved_profile) -> ProviderResult`
- `capture_raw_response_ref(raw_payload, policy) -> RawResponseRef | None`
- `build_provider_profile_diagnostics(result) -> list[ProviderDiagnostic]`

#### Integrationspunkte zu anderen Foundations
- Foundation 04:
  - liefert Profilkonfiguration und Override-Policies
- Foundation 06:
  - liefert nur gewünschten Einsatzzweck/Profiltyp, keine Providerdetails
- Foundation 10:
  - Output zeigt `profile_id`, Fallback-Hinweise und Usage/Cost-Herkunft
- Foundation 11:
  - Eventing für Profilauflösung, Fallback, Rohantwort-Referenzierung
- Foundation 14/17:
  - Regeln für Speicherung/Retention/Audit von Rohantwortreferenzen

#### Migrationsansatz (V2)
1. Profilresolver zunächst rein diagnostisch einführen.
2. Bestehende direkte Modellsettings auf Profile mappen.
3. Fallback-Kette aktivieren und im Trace erzwingen.
4. Optionalen Rohantwort-Ref-Speicher für Diagnoseläufe ergänzen.
5. Harte Regel aktivieren: keine hardcodierten Model-Switches im Mode-Code.

#### Verbindliche V2-Regel
Modellprofil-Auswahl ist deklarativ und zentral; Modes/Tasks dürfen keine direkten Provider-/Model-Switches hardcodieren.
