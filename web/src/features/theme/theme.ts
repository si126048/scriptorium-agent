export type Theme = 'light' | 'dark';
const KEY = 'scriptorium_theme';

export function getTheme(): Theme {
  try {
    return localStorage.getItem(KEY) === 'dark' ? 'dark' : 'light';
  } catch {
    return 'light';
  }
}

export function applyTheme(theme: Theme) {
  const node = document.documentElement;
  node.dataset.theme = theme;
  node.style.colorScheme = theme;
}

export function setTheme(theme: Theme) {
  try { localStorage.setItem(KEY, theme); } catch { /* storage can be unavailable */ }
  applyTheme(theme);
}

export function initTheme() {
  applyTheme(getTheme());
}
