(function () {
  // Coque commune : langue (FR/EN) et thème (sombre/clair) partagés par toutes les pages.
  // Les pages écoutent les événements "modics:lang" et "modics:theme" pour se redessiner.
  const SHELL = {
    fr: { nav_atelier: "Atelier", nav_fleet: "Parc", nav_dashboard: "Analyse", nav_live: "Live", theme_light: "Passer en thème clair", theme_dark: "Passer en thème sombre" },
    en: { nav_atelier: "Workshop", nav_fleet: "Fleet", nav_dashboard: "Analysis", nav_live: "Live", theme_light: "Switch to light theme", theme_dark: "Switch to dark theme" },
  };
  const root = document.documentElement;
  const store = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* stockage indisponible */ } };

  const M = window.MODICS = {
    get lang() { return root.lang === "en" ? "en" : "fr"; },
    get theme() { return root.dataset.theme === "light" ? "light" : "dark"; },
    setLang(l) {
      root.lang = l; store("modics_lang", l);
      M.applyI18n(SHELL[l]); sync();
      document.dispatchEvent(new CustomEvent("modics:lang", { detail: l }));
    },
    setTheme(t) {
      root.dataset.theme = t; store("modics_theme", t); sync();
      document.dispatchEvent(new CustomEvent("modics:theme", { detail: t }));
    },
    // Traduit les éléments [data-i18n] / [data-i18n-ph] (placeholder) dont la clé existe dans dict
    applyI18n(dict) {
      document.querySelectorAll("[data-i18n]").forEach((el) => { const v = dict[el.dataset.i18n]; if (typeof v === "string") el.textContent = v; });
      document.querySelectorAll("[data-i18n-ph]").forEach((el) => { const v = dict[el.dataset.i18nPh]; if (typeof v === "string") el.placeholder = v; });
    },
    css: (v) => getComputedStyle(document.body).getPropertyValue(v).trim(),
  };

  function sync() {
    document.querySelectorAll(".lang button").forEach((b) => b.classList.toggle("active", b.dataset.lang === M.lang));
    const tb = document.getElementById("theme-btn");
    if (tb) tb.title = SHELL[M.lang][M.theme === "dark" ? "theme_light" : "theme_dark"];
  }
  document.querySelectorAll(".lang button").forEach((b) => b.addEventListener("click", () => M.setLang(b.dataset.lang)));
  const tb = document.getElementById("theme-btn");
  if (tb) tb.addEventListener("click", () => M.setTheme(M.theme === "dark" ? "light" : "dark"));
  M.applyI18n(SHELL[M.lang]);
  sync();
})();
