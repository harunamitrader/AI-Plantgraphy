(function () {
  const DB_NAME = 'ai-plantgraphy-drafts';
  const STORE_NAME = 'drafts';
  const DB_VERSION = 1;

  function openDb() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          const store = db.createObjectStore(STORE_NAME, { keyPath: 'id' });
          store.createIndex('createdAt', 'createdAt', { unique: false });
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error || new Error('IndexedDBを開けません。'));
    });
  }

  async function withStore(mode, callback) {
    const db = await openDb();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, mode);
      const store = tx.objectStore(STORE_NAME);
      const result = callback(store);
      tx.oncomplete = () => resolve(result);
      tx.onerror = () => reject(tx.error || new Error('IndexedDB操作に失敗しました。'));
      tx.onabort = () => reject(tx.error || new Error('IndexedDB操作が中断されました。'));
    }).finally(() => db.close());
  }

  function requestToPromise(request) {
    return new Promise((resolve, reject) => {
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error || new Error('IndexedDB読み取りに失敗しました。'));
    });
  }

  function generateId() {
    const random = Math.random().toString(36).slice(2, 8);
    return `draft-${Date.now()}-${random}`;
  }

  function normalizeImages(images) {
    return (images || []).map((image, index) => ({
      id: image.id || `image-${index + 1}`,
      name: image.name || `image-${index + 1}.jpg`,
      type: image.type || 'image/jpeg',
      blob: image.blob
    }));
  }

  async function saveDraft(draft) {
    const payload = {
      id: draft.id || generateId(),
      createdAt: draft.createdAt || new Date().toISOString(),
      note: draft.note || '',
      locationLabel: draft.locationLabel || '',
      geminiModel: draft.geminiModel || '',
      selectedImageIds: Array.isArray(draft.selectedImageIds) ? draft.selectedImageIds : [],
      images: normalizeImages(draft.images)
    };
    await withStore('readwrite', (store) => {
      store.put(payload);
    });
    return payload;
  }

  async function listDrafts() {
    const records = await withStore('readonly', (store) => requestToPromise(store.getAll()));
    return (records || []).sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt)));
  }

  async function getDraft(id) {
    return withStore('readonly', (store) => requestToPromise(store.get(id)));
  }

  async function deleteDraft(id) {
    await withStore('readwrite', (store) => {
      store.delete(id);
    });
  }

  async function countDrafts() {
    return withStore('readonly', (store) => requestToPromise(store.count()));
  }

  async function checkHealth() {
    const response = await fetch('/api/health', { cache: 'no-store' });
    if (!response.ok) {
      throw new Error('サーバーが応答しません。');
    }
    return response.json();
  }

  async function sendDraft(id, apiKey) {
    const draft = await getDraft(id);
    if (!draft) {
      throw new Error('未送信データが見つかりません。');
    }
    const selectedIds = Array.isArray(draft.selectedImageIds) && draft.selectedImageIds.length
      ? new Set(draft.selectedImageIds)
      : new Set((draft.images || []).slice(-3).map((image) => image.id));
    const images = (draft.images || []).filter((image) => selectedIds.has(image.id)).slice(0, 3);
    if (!images.length) {
      throw new Error('送信する写真がありません。');
    }

    const formData = new FormData();
    images.forEach((image) => {
      formData.append('images', new File([image.blob], image.name, { type: image.type || 'image/jpeg' }));
    });
    formData.append('note', draft.note || '');
    formData.append('location_label', draft.locationLabel || '');
    formData.append('gemini_model', draft.geminiModel || '');

    const response = await fetch('/api/observations', {
      method: 'POST',
      headers: {
        'X-Plant-Dex-Api-Key': apiKey
      },
      body: formData
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || '送信に失敗しました。');
    }
    await deleteDraft(id);
    return data;
  }

  function escapeHtml(value) {
    return String(value || '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#39;');
  }

  function formatDraftDate(value) {
    if (!value) {
      return '日時不明';
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return String(value);
    }
    return date.toLocaleString('ja-JP', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    });
  }

  window.AIPlantgraphyDrafts = {
    saveDraft,
    listDrafts,
    getDraft,
    deleteDraft,
    countDrafts,
    checkHealth,
    sendDraft,
    formatDraftDate,
    escapeHtml
  };
})();
