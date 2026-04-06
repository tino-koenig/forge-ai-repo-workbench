(function () {
  "use strict";

  const STORAGE_KEY = "__palette";
  const DARK_SCHEME = "slate";
  const LIGHT_SCHEME = "default";

  function readPalette() {
    try {
      if (typeof window.__md_get === "function") {
        return window.__md_get(STORAGE_KEY);
      }
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (_) {
      return null;
    }
  }

  function writePalette(scheme) {
    const palette = readPalette() || {};
    const color = palette.color || {};
    const merged = {
      ...palette,
      color: {
        ...color,
        scheme,
      },
    };

    try {
      if (typeof window.__md_set === "function") {
        window.__md_set(STORAGE_KEY, merged);
      } else {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(merged));
      }
    } catch (_) {
      return;
    }
  }

  function getCurrentScheme() {
    return document.body.getAttribute("data-md-color-scheme") || LIGHT_SCHEME;
  }

  function setCurrentScheme(scheme) {
    document.body.setAttribute("data-md-color-scheme", scheme);
    writePalette(scheme);
  }

  function updateToggleLabel(button, scheme) {
    if (!button) {
      return;
    }
    const isGerman = document.documentElement.lang === "de";
    if (scheme === DARK_SCHEME) {
      button.textContent = isGerman ? "Hell" : "Light";
      button.setAttribute("aria-label", isGerman ? "Zu hellem Theme wechseln" : "Switch to light theme");
      return;
    }
    button.textContent = isGerman ? "Dunkel" : "Dark";
    button.setAttribute("aria-label", isGerman ? "Zu dunklem Theme wechseln" : "Switch to dark theme");
  }

  function initToggle(button) {
    const persistedScheme = readPalette()?.color?.scheme;
    if (persistedScheme) {
      setCurrentScheme(persistedScheme);
      updateToggleLabel(button, persistedScheme);
    } else {
      updateToggleLabel(button, getCurrentScheme());
    }

    button.addEventListener("click", function () {
      const nextScheme = getCurrentScheme() === DARK_SCHEME ? LIGHT_SCHEME : DARK_SCHEME;
      setCurrentScheme(nextScheme);
      updateToggleLabel(button, nextScheme);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    const button = document.querySelector("[data-forge-theme-toggle]");
    if (!button) {
      return;
    }
    initToggle(button);
  });
})();
