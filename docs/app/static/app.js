(function () {
  const API_BASE_KEY = 'ai_plantgraphy_api_base_url';
  const PASSWORD_KEY = 'ai_plantgraphy_password';
  const LEGACY_PASSWORD_KEY = 'plant_dex_api_key';
  const MODEL_KEY = 'plant_dex_gemini_model';

  function isPagesHost() {
    return window.location.hostname.endsWith('github.io');
  }

  function getAppRootPath() {
    const override = document.querySelector('meta[name="ai-plantgraphy-app-root"]');
    if (override && override.content) {
      return normalizeRootPath(override.content);
    }
    const path = window.location.pathname || '/';
    if (path.endsWith('.html')) {
      return normalizeRootPath(path.slice(0, path.lastIndexOf('/') + 1));
    }
    return '/';
  }

  function normalizeRootPath(value) {
    const text = String(value || '').trim();
    if (!text) {
      return '/';
    }
    const withLeadingSlash = text.startsWith('/') ? text : `/${text}`;
    return withLeadingSlash.endsWith('/') ? withLeadingSlash : `${withLeadingSlash}/`;
  }

  function normalizeApiBaseUrl(value) {
    const text = String(value || '').trim();
    if (!text) {
      return '';
    }
    return text.replace(/\/+$/, '');
  }

  function getStoredApiBaseUrl() {
    return normalizeApiBaseUrl(localStorage.getItem(API_BASE_KEY) || '');
  }

  function getDefaultApiBaseUrl() {
    if (isPagesHost()) {
      return '';
    }
    return normalizeApiBaseUrl(window.location.origin);
  }

  function getApiBaseUrl() {
    return getStoredApiBaseUrl() || getDefaultApiBaseUrl();
  }

  function requiresExplicitApiBaseUrl() {
    return isPagesHost();
  }

  function hasConfiguredApiBaseUrl() {
    return Boolean(getApiBaseUrl());
  }

  function setApiBaseUrl(value) {
    const normalized = normalizeApiBaseUrl(value);
    if (!normalized) {
      localStorage.removeItem(API_BASE_KEY);
      return '';
    }
    localStorage.setItem(API_BASE_KEY, normalized);
    return normalized;
  }

  function apiUrl(path) {
    const normalizedPath = String(path || '').startsWith('/') ? path : `/${path}`;
    const baseUrl = getApiBaseUrl();
    if (!baseUrl) {
      throw new Error('接続先URLが未設定です。設定ページで自分のPCのURLを保存してください。');
    }
    return `${baseUrl}${normalizedPath}`;
  }

  function pageUrl(slug) {
    const normalized = String(slug || '').replace(/^\/+/, '').replace(/\.html$/, '');
    if (isPagesHost()) {
      const root = getAppRootPath();
      if (!normalized || normalized === 'home' || normalized === 'index') {
        return `${root}index.html`;
      }
      return `${root}${normalized}.html`;
    }
    if (!normalized || normalized === 'home' || normalized === 'index') {
      return '/';
    }
    return `/${normalized}`;
  }

  function observationUrl(observationId) {
    if (!observationId) {
      return pageUrl('observations');
    }
    if (isPagesHost()) {
      return `${apiUrl(`/observations/${observationId}`)}`;
    }
    return `/observations/${observationId}`;
  }

  function plantUrl(plantId) {
    if (!plantId) {
      return pageUrl('plants');
    }
    if (isPagesHost()) {
      return `${apiUrl(`/plants/${plantId}`)}`;
    }
    return `/plants/${plantId}`;
  }

  function resolveServerUrl(pathOrUrl) {
    const text = String(pathOrUrl || '').trim();
    if (!text) {
      return '';
    }
    if (/^https?:\/\//i.test(text)) {
      return text;
    }
    return `${apiUrl(text.startsWith('/') ? text : `/${text}`)}`;
  }

  function serverPageUrl(slug) {
    const normalized = String(slug || '').replace(/^\/+/, '').replace(/\.html$/, '');
    if (!normalized || normalized === 'home' || normalized === 'index') {
      return apiUrl('/');
    }
    return apiUrl(`/${normalized}`);
  }

  function bindOnlineLinks(root = document) {
    const links = root.querySelectorAll('[data-online-link]');
    if (!links.length) {
      return;
    }
    const hasApiBase = hasConfiguredApiBaseUrl();
    links.forEach((link) => {
      const slug = link.getAttribute('data-online-link') || '';
      if (!hasApiBase) {
        link.setAttribute('href', pageUrl('settings'));
        link.classList.add('is-disabled');
        link.setAttribute('title', '先に設定ページで自分のPCの接続先URLを保存してください。');
        return;
      }
      link.setAttribute('href', serverPageUrl(slug));
      link.classList.remove('is-disabled');
      link.removeAttribute('title');
    });
  }

  function getStoredPassword() {
    return (localStorage.getItem(PASSWORD_KEY) || localStorage.getItem(LEGACY_PASSWORD_KEY) || '').trim();
  }

  function setStoredPassword(value) {
    const trimmed = String(value || '').trim();
    localStorage.setItem(PASSWORD_KEY, trimmed);
    localStorage.removeItem(LEGACY_PASSWORD_KEY);
    return trimmed;
  }

  function getStoredGeminiModel() {
    return localStorage.getItem(MODEL_KEY) || '';
  }

  function setStoredGeminiModel(value) {
    localStorage.setItem(MODEL_KEY, value || '');
    return value || '';
  }

  async function fetchJson(path, options = {}) {
    const response = await fetch(apiUrl(path), options);
    const contentType = response.headers.get('content-type') || '';
    const data = contentType.includes('application/json') ? await response.json() : null;
    if (!response.ok) {
      throw new Error((data && data.detail) || 'API呼び出しに失敗しました。');
    }
    return data;
  }

  async function fetchBootstrap() {
    return fetchJson('/api/bootstrap', { cache: 'no-store' });
  }

  function defaultOfflineMessage() {
    return '接続先PCに接続できません。PC起動後に再試行してください。';
  }

  function showOfflineBanner(target, message) {
    if (!target) {
      return;
    }
    target.hidden = false;
    target.innerHTML = `
      <div class="offline-banner-body">
        <strong>サーバー未接続</strong>
        <p>${message || defaultOfflineMessage()}</p>
      </div>
    `;
  }

  function hideOfflineBanner(target) {
    if (!target) {
      return;
    }
    target.hidden = true;
    target.innerHTML = '';
  }

  if ('serviceWorker' in navigator && window.isSecureContext) {
    window.addEventListener('load', () => {
      const scopePath = getAppRootPath();
      const serviceWorkerUrl = new URL(`${scopePath.replace(/^\//, '')}static/service-worker.js`, window.location.origin + '/');
      navigator.serviceWorker.register(serviceWorkerUrl.pathname, { scope: scopePath }).catch(() => {});
    });
  }

  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => bindOnlineLinks());
    } else {
      bindOnlineLinks();
    }
  }

  window.AIPlantgraphyApp = {
    apiBaseKey: API_BASE_KEY,
    passwordKey: PASSWORD_KEY,
    modelKey: MODEL_KEY,
    getAppRootPath,
    normalizeApiBaseUrl,
    getStoredApiBaseUrl,
    getDefaultApiBaseUrl,
    getApiBaseUrl,
    requiresExplicitApiBaseUrl,
    hasConfiguredApiBaseUrl,
    setApiBaseUrl,
    apiUrl,
    pageUrl,
    observationUrl,
    plantUrl,
    serverPageUrl,
    resolveServerUrl,
    bindOnlineLinks,
    getStoredPassword,
    setStoredPassword,
    getStoredGeminiModel,
    setStoredGeminiModel,
    fetchJson,
    fetchBootstrap,
    defaultOfflineMessage,
    showOfflineBanner,
    hideOfflineBanner,
  };
})();
