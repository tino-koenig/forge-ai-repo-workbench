---
hide:
  - navigation
  - toc
---

<style>
  .md-header,
  .md-tabs {
    display: none;
  }

  .md-main {
    margin-top: 0;
  }

  .forge-hero__copy {
    padding: 1.05rem 1.05rem 1rem;
  }

  .forge-lang-switch {
    margin-bottom: 0.72rem;
  }

  .forge-lang-switch--global {
    max-width: 84rem;
    margin: 0.42rem auto 0.32rem;
    padding: 0 1.05rem;
    display: flex;
    justify-content: flex-end;
    align-items: center;
    gap: 0.3rem;
    font-size: 0.72rem;
    letter-spacing: 0.008em;
    line-height: 1;
  }

  .forge-lang-switch--global a {
    text-decoration: none;
    opacity: 0.56;
    font-weight: 500;
    line-height: 1;
  }

  .forge-lang-switch--global a.is-active {
    opacity: 0.94;
    font-weight: 600;
    text-decoration: none;
    border-bottom: 1px solid currentColor;
    padding-bottom: 0.08rem;
  }

  .forge-lang-switch--global span {
    opacity: 0.24;
    line-height: 1;
  }

  .forge-lang-switch--global .forge-theme-toggle {
    padding: 0.14rem 0.46rem;
    min-height: auto;
    border-radius: 999px;
    font-size: 0.69rem;
    font-weight: 550;
    letter-spacing: 0.006em;
    line-height: 1;
    border-width: 1px;
    opacity: 0.82;
  }

  .forge-lang-switch--global .forge-theme-toggle:hover {
    opacity: 0.94;
  }

  .forge-hero__copy h1 {
    margin-top: 0;
    margin-bottom: 0.95rem;
  }

  .forge-lead {
    margin-top: 0;
    margin-bottom: 0.65rem;
  }

  .forge-subline {
    margin-top: 0;
    margin-bottom: 0.9rem;
    font-size: 0.89rem;
    font-weight: 500;
    line-height: 1.45;
    letter-spacing: 0.005em;
    color: color-mix(in srgb, var(--forge-text) 58%, transparent);
    max-width: 46ch;
  }

  .forge-hero__actions {
    gap: 0.6rem;
    margin-bottom: 0.78rem;
  }

  .forge-hero__example {
    margin-top: 1.2rem;
    max-width: 54ch;
    padding: 0.45rem 0.56rem;
    border: 1px solid color-mix(in srgb, var(--forge-border) 72%, transparent);
    border-radius: 8px;
    background: color-mix(in srgb, var(--forge-copy-bg) 68%, transparent);
    color: color-mix(in srgb, var(--forge-text) 78%, transparent);
    font-size: 0.84rem;
    line-height: 1.45;
    opacity: 0.85;
  }

  .forge-hero__example strong {
    font-weight: 600;
  }

  .forge-hero__example code {
    font-size: 0.87em;
  }

  .forge-trust-card {
    padding: 1.05rem 1.15rem;
    border-radius: 10px;
    border: 1px solid color-mix(in srgb, var(--md-primary-fg-color) 35%, transparent);
    background: color-mix(in srgb, var(--md-primary-fg-color) 8%, transparent);
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  }

  .forge-start-card--trust {
    align-self: stretch;
  }

  .forge-trust-card p {
    margin-top: 0;
    margin-bottom: 0.7rem;
  }

  .forge-trust-card ul {
    margin: 0;
    padding-left: 1.1rem;
  }

  .forge-trust-card li {
    margin-bottom: 0.4rem;
  }

  .forge-start-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1rem;
  }

  .forge-start-card--quick {
    grid-column: span 2;
  }

  .forge-start-card--docs {
    grid-column: span 1;
  }

  .forge-start-card--setup {
    grid-column: span 1;
  }

  .forge-start-card--trust {
    grid-column: span 2;
  }
</style>

<div class="forge-lang-switch forge-lang-switch--global" aria-label="Sprachauswahl">
  <a href="../">EN</a>
  <span>•</span>
  <a class="is-active" href="./">DE</a>
  <span>•</span>
  <button type="button" class="forge-theme-toggle" data-forge-theme-toggle aria-label="Theme umschalten">Dark</button>
</div>
<section class="forge-hero">
  <div class="forge-hero__copy">
    <h1>Forge - Your AI Repo Workbench</h1>
    <p class="forge-lead">
      Finde die richtige Stelle im Code, verstehe Zusammenhänge und Abhängigkeiten und verbessere dein Repository nachvollziehbar und kontrolliert.
    </p>
    <p class="forge-subline">Keine Black Box. Keine unklaren Zwischenschritte. Mit query, explain, review und propose wird die Arbeit am Repository schneller, präziser und bleibt jederzeit überprüfbar.</p>
    <div class="forge-hero__actions">
      <a class="md-button md-button--primary" href="getting-started/">Direkt starten</a>
      <a class="md-button" href="core-commands/">Commands entdecken</a>
    </div>
    <div class="forge-hero__example">
      <strong>Beispiel:</strong> Du fragst <code>"Wo ist der Runtime-Settings-Resolver implementiert?"</code>. Forge findet die relevanten Dateien, zeigt dir die entscheidenden Zeilen mit den passenden Belegen und macht jeden weiteren Schritt für review und sichere Änderungen nachvollziehbar.
    </div>
  </div>
  <div class="forge-hero__visual">
    <img src="../assets/images/forge-landing-visual.svg" alt="Forge Architektur-Visualisierung" />
  </div>
</section>

## Warum Forge überzeugt

<div class="forge-card-grid">
  <article class="forge-card">
    <div class="forge-card__row">
      <div class="forge-card__icon" aria-hidden="true">
        <svg viewBox="0 0 24 24"><path d="m12 16 7.36-5.73L21 9l-9-7-9 7 1.63 1.27M12 18.54l-7.38-5.73L3 14.07l9 7 9-7-1.63-1.27z"/></svg>
      </div>
      <div class="forge-card__body">
        <h3>Klare Modes</h3>
        <p>Keine versteckten Workflows — jeder Mode hat eine klare Aufgabe, einen sichtbaren Ablauf und einen verlässlichen Scope.</p>
      </div>
    </div>
  </article>
  <article class="forge-card">
    <div class="forge-card__row">
      <div class="forge-card__icon" aria-hidden="true">
        <svg viewBox="0 0 24 24"><path d="m10 17-4-4 1.41-1.41L10 14.17l6.59-6.59L18 9m-6-8L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5z"/></svg>
      </div>
      <div class="forge-card__body">
        <h3>Nachvollziehbar statt rätselhaft</h3>
        <p>Kein Rätselraten — du siehst genau, welche Dateien, Zeilen, Belege, Diagnostics und Entscheidungen zu einem Ergebnis geführt haben.</p>
      </div>
    </div>
  </article>
  <article class="forge-card">
    <div class="forge-card__row">
      <div class="forge-card__icon" aria-hidden="true">
        <svg viewBox="0 0 24 24"><path d="M20.5 11H19V7a2 2 0 0 0-2-2h-4V3.5A2.5 2.5 0 0 0 10.5 1 2.5 2.5 0 0 0 8 3.5V5H4a2 2 0 0 0-2 2v3.8h1.5c1.5 0 2.7 1.2 2.7 2.7S5 16.2 3.5 16.2H2V20a2 2 0 0 0 2 2h3.8v-1.5c0-1.5 1.2-2.7 2.7-2.7s2.7 1.2 2.7 2.7V22H17a2 2 0 0 0 2-2v-4h1.5a2.5 2.5 0 0 0 2.5-2.5 2.5 2.5 0 0 0-2.5-2.5"/></svg>
      </div>
      <div class="forge-card__body">
        <h3>Starker Kern für eigene Lösungen</h3>
        <p>Forge bringt einen starken Kern mit, auf dem du eigene Workflows, Anwendungen und strengere Anforderungen sauber aufbauen kannst.</p>
      </div>
    </div>
  </article>
  <article class="forge-card">
    <div class="forge-card__row">
      <div class="forge-card__icon" aria-hidden="true">
        <svg viewBox="0 0 24 24"><path d="m13.13 22.19-1.63-3.83c1.57-.58 3.04-1.36 4.4-2.27zM5.64 12.5l-3.83-1.63 6.1-2.77C7 9.46 6.22 10.93 5.64 12.5M21.61 2.39S16.66.269 11 5.93c-2.19 2.19-3.5 4.6-4.35 6.71-.28.75-.09 1.57.46 2.13l2.13 2.12c.55.56 1.37.74 2.12.46A19.1 19.1 0 0 0 18.07 13c5.66-5.66 3.54-10.61 3.54-10.61m-7.07 7.07c-.78-.78-.78-2.05 0-2.83s2.05-.78 2.83 0c.77.78.78 2.05 0 2.83s-2.05.78-2.83 0m-5.66 7.07-1.41-1.41zM6.24 22l3.64-3.64c-.34-.09-.67-.24-.97-.45L4.83 22zM2 22h1.41l4.77-4.76-1.42-1.41L2 20.59zm0-2.83 4.09-4.08c-.21-.3-.36-.62-.45-.97L2 17.76z"/></svg>
      </div>
      <div class="forge-card__body">
        <h3>Schnell produktiv</h3>
        <p>Starke Defaults, Team-Templates und framework-aware Setup für gängige Stacks wie TYPO3 bringen dich schnell zu brauchbaren Ergebnissen.</p>
      </div>
    </div>
  </article>
</div>

## Ein kurzer CLI-Ablauf

```bash
# Passende Stelle im Code finden
forge query "Wo ist der Runtime-Settings-Resolver implementiert?"

# Exakte Datei und Belege prüfen
forge explain core/runtime_settings_foundation.py

# Implementierung prüfen
forge review core/runtime_settings_foundation.py --focus correctness

# Sichere Verbesserung vorbereiten
forge propose core/runtime_settings_foundation.py --goal "tighten runtime setting validation"
```

## Der passende Einstieg

Wähle den Weg, der am besten zu dir passt: direkt praktisch loslegen, Forge Schritt für Schritt einrichten oder zuerst die Dokumentation nutzen.

<div class="forge-start-grid">
  <article class="forge-start-card forge-start-card--quick">
    <h3>Schneller Einstieg</h3>
    <p>Starte in unter einer Minute und erhalte sofort erste belastbare Ergebnisse.</p>
    <pre><code>python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
forge init --non-interactive --template typo3-v14
forge query "Wo ist der Runtime-Settings-Resolver implementiert?"
forge review core/runtime_settings_foundation.py --focus correctness</code></pre>
  </article>
  <article class="forge-start-card forge-start-card--docs">
    <h3>Dokumentation</h3>
    <p>Verstehe, wie Forge aufgebaut ist und wie du es nutzt — von User-Workflows über Developer-Foundations bis zum vollständigen Open-Source-Repository.</p>
    <ul>
      <li><a href="getting-started/">User-Dokumentation</a></li>
      <li><a href="https://github.com/tino-koenig/forge/tree/main/docs/developer">Developer-Dokumentation</a></li>
      <li><a href="https://github.com/tino-koenig/forge">GitHub-Repository</a></li>
    </ul>
  </article>
  <article class="forge-start-card forge-start-card--setup">
    <h3>Installation und Einrichtung</h3>
    <p>Richte Forge Schritt für Schritt ein — von der Installation bis zur LLM-Konfiguration.</p>
    <ul>
      <li><a href="getting-started/">Guided Setup</a></li>
      <li><a href="getting-started/">Installation</a></li>
      <li><a href="llm-setup/">LLM-Setup</a></li>
    </ul>
  </article>
  <article class="forge-start-card forge-start-card--trust forge-trust-card">
    <h3>Trust, Safety und Offenheit</h3>
    <p>Forge ist dafür gebaut, in realen Umgebungen prüfbar, begrenzt und verlässlich nutzbar zu bleiben — mit expliziten Regeln, sichtbaren Limits und nachvollziehbarem Verhalten. Nichts Wichtiges bleibt verborgen, und jeder Schritt bleibt überprüfbar.</p>
    <ul>
      <li><strong>Developer-Dokumentation:</strong> Foundations, Contracts und Architekturhinweise sind in <code>docs/developer/</code> vollständig dokumentiert und eng mit der Implementierung verzahnt.</li>
      <li><strong>Trust &amp; Safety:</strong> <a href="trust-and-safety/">Regeln, Schutzmechanismen und Grenzen</a> sind explizit, versioniert und verbindlich beschrieben.</li>
      <li><strong>Logging &amp; Limits:</strong> Laufzeitgrenzen, Read/Write-Scope und Diagnostics bleiben in <a href="runtime-settings-and-sessions/">Runtime Settings &amp; Sessions</a> sichtbar, nachvollziehbar und dokumentiert.</li>
      <li><strong>LLM-Provider &amp; Local LLM:</strong> OpenAI-kompatible Endpunkte wie OpenAI, LiteLLM und vLLM sind in <a href="llm-setup/">LLM-Setup</a> mit klarem Setup und transparentem Verhalten beschrieben.</li>
      <li><strong>Open Source (MIT):</strong> Forge ist unter der MIT-Lizenz vollständig offen, prüfbar und auditierbar (<code>LICENSE</code> im Repository).</li>
    </ul>
  </article>
</div>
