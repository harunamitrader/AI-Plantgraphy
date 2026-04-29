(function () {
  const DB_NAME = 'ai-plantgraphy-view-cache';
  const STORE_NAME = 'entries';
  const DB_VERSION = 1;

  function openDb() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          db.createObjectStore(STORE_NAME, { keyPath: 'key' });
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error || new Error('IndexedDB を開けません。'));
    });
  }

  async function withStore(mode, callback) {
    const db = await openDb();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(STORE_NAME, mode);
      const store = transaction.objectStore(STORE_NAME);
      let finished = false;

      transaction.oncomplete = () => {
        db.close();
        if (!finished) {
          resolve(undefined);
        }
      };
      transaction.onerror = () => {
        db.close();
        reject(transaction.error || new Error('IndexedDB の処理に失敗しました。'));
      };

      Promise.resolve(callback(store))
        .then((value) => {
          finished = true;
          resolve(value);
        })
        .catch((error) => {
          finished = true;
          reject(error);
        });
    });
  }

  function indexKey(name) {
    return `${name}_index`;
  }

  function detailKey(kind, id) {
    return `${kind}_detail::${id}`;
  }

  async function saveEntry(key, payload) {
    return withStore('readwrite', (store) => {
      store.put({
        key,
        savedAt: new Date().toISOString(),
        payload,
      });
    });
  }

  async function loadEntry(key) {
    return withStore('readonly', (store) => new Promise((resolve, reject) => {
      const request = store.get(key);
      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () => reject(request.error || new Error('キャッシュを読めません。'));
    }));
  }

  async function saveIndex(name, payload) {
    return saveEntry(indexKey(name), payload);
  }

  async function loadIndex(name) {
    return loadEntry(indexKey(name));
  }

  async function saveDetail(kind, id, payload) {
    return saveEntry(detailKey(kind, id), payload);
  }

  async function loadDetail(kind, id) {
    return loadEntry(detailKey(kind, id));
  }

  function formatSavedAt(savedAt) {
    if (!savedAt) {
      return '';
    }
    const date = new Date(savedAt);
    if (Number.isNaN(date.getTime())) {
      return '';
    }
    return date.toLocaleString('ja-JP', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  function offlineMessage(baseMessage, savedAt) {
    const formatted = formatSavedAt(savedAt);
    if (!formatted) {
      return `${baseMessage} オフライン表示中 / 最新ではありません。`;
    }
    return `${baseMessage} オフライン表示中 / 最新ではありません。最終更新 ${formatted}`;
  }

  window.AIPlantgraphyViewCache = {
    saveEntry,
    loadEntry,
    saveIndex,
    loadIndex,
    saveDetail,
    loadDetail,
    formatSavedAt,
    offlineMessage,
  };
})();
