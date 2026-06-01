export type FetchResourceType = 'manifest' | 'index' | 'shard' | 'exam-data' | 'default';

export type ArtifactCacheScope = 'memory_content_hash' | 'browser_persistent_content_hash';

export interface ArtifactContentCache {
    scope: ArtifactCacheScope;
    has: (url: string) => Promise<boolean>;
    read: (url: string) => Promise<ArrayBuffer | null>;
    write: (url: string, payload: ArrayBuffer) => Promise<void>;
}

export interface ArtifactFetchResult<T> {
    value: T;
    cacheHit: boolean;
    cacheLayer: 'persistent' | 'network' | 'none';
    byteLength: number;
}

const textDecoder = new TextDecoder();

const cloneArrayBuffer = (buffer: ArrayBuffer): ArrayBuffer => buffer.slice(0);

const cacheModeFor = (resourceType: FetchResourceType): RequestCache => {
    switch (resourceType) {
        case 'manifest':
            return 'reload';
        case 'index':
        case 'shard':
            return 'force-cache';
        case 'exam-data':
            return 'default';
        default:
            return 'default';
    }
};

export const fetchJson = async <T = unknown>(
    url: string,
    signal?: AbortSignal,
    resourceType: FetchResourceType = 'default'
): Promise<T> => {
    const response = await fetch(url, { cache: cacheModeFor(resourceType), signal });

    if (!response.ok) {
        throw new Error(`数据请求失败: ${url} HTTP ${response.status}`);
    }

    try {
        return await response.json() as T;
    } catch {
        throw new Error(`数据文件不是有效 JSON: ${url}`);
    }
};

export const fetchArrayBuffer = async (
    url: string,
    signal?: AbortSignal,
    resourceType: FetchResourceType = 'default'
): Promise<ArrayBuffer> => {
    const response = await fetch(url, { cache: cacheModeFor(resourceType), signal });

    if (!response.ok) {
        throw new Error(`数据请求失败: ${url} HTTP ${response.status}`);
    }

    return response.arrayBuffer();
};

const fetchArrayBufferArtifactResult = async (
    url: string,
    signal: AbortSignal | undefined,
    resourceType: FetchResourceType,
    cache?: ArtifactContentCache
): Promise<ArtifactFetchResult<ArrayBuffer>> => {
    if (signal?.aborted) {
        throw new DOMException('Search cancelled', 'AbortError');
    }
    if (cache && resourceType !== 'manifest') {
        const cached = await cache.read(url).catch(() => null);
        if (cached) {
            return {
                value: cached,
                cacheHit: true,
                cacheLayer: 'persistent',
                byteLength: cached.byteLength,
            };
        }
    }

    const response = await fetch(url, { cache: cacheModeFor(resourceType), signal });
    if (!response.ok) {
        throw new Error(`数据请求失败: ${url} HTTP ${response.status}`);
    }
    const payload = await response.arrayBuffer();
    if (cache && resourceType !== 'manifest') {
        await cache.write(url, cloneArrayBuffer(payload)).catch(() => undefined);
    }
    return {
        value: payload,
        cacheHit: false,
        cacheLayer: cache ? 'network' : 'none',
        byteLength: payload.byteLength,
    };
};

export const fetchJsonArtifact = async <T = unknown>(
    url: string,
    signal?: AbortSignal,
    resourceType: FetchResourceType = 'default',
    cache?: ArtifactContentCache
): Promise<ArtifactFetchResult<T>> => {
    const result = await fetchArrayBufferArtifactResult(url, signal, resourceType, cache);
    try {
        return {
            ...result,
            value: JSON.parse(textDecoder.decode(result.value)) as T,
        };
    } catch {
        throw new Error(`数据文件不是有效 JSON: ${url}`);
    }
};

export const fetchArrayBufferArtifact = (
    url: string,
    signal?: AbortSignal,
    resourceType: FetchResourceType = 'default',
    cache?: ArtifactContentCache
): Promise<ArtifactFetchResult<ArrayBuffer>> => {
    return fetchArrayBufferArtifactResult(url, signal, resourceType, cache);
};

type ArtifactCacheRecord = {
    url: string;
    storedAt: number;
    byteLength: number;
    payload: ArrayBuffer;
};

const openArtifactDb = (dbName: string, storeName: string): Promise<IDBDatabase | null> => {
    if (!('indexedDB' in globalThis)) return Promise.resolve(null);
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(dbName, 1);
        request.onupgradeneeded = () => {
            const db = request.result;
            if (!db.objectStoreNames.contains(storeName)) {
                db.createObjectStore(storeName, { keyPath: 'url' });
            }
        };
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error ?? new Error('IndexedDB open failed'));
    });
};

const transactArtifactStore = async <T>(
    dbName: string,
    storeName: string,
    mode: IDBTransactionMode,
    run: (store: IDBObjectStore) => IDBRequest<T>
): Promise<T | null> => {
    const db = await openArtifactDb(dbName, storeName);
    if (!db) return null;
    return new Promise((resolve, reject) => {
        const transaction = db.transaction(storeName, mode);
        const request = run(transaction.objectStore(storeName));
        request.onsuccess = () => resolve(request.result ?? null);
        request.onerror = () => reject(request.error ?? new Error('IndexedDB artifact transaction failed'));
        transaction.oncomplete = () => db.close();
        transaction.onabort = () => {
            db.close();
            reject(transaction.error ?? new Error('IndexedDB artifact transaction aborted'));
        };
    });
};

export const createBrowserContentHashArtifactCache = (
    namespace = 'njupt-public'
): ArtifactContentCache => {
    const safeNamespace = namespace.replace(/[^a-z0-9._-]+/gi, '-');
    const dbName = `njupt-search-artifact-cache-${safeNamespace}-v1`;
    const storeName = 'artifacts';
    const memoryMirror = new Map<string, ArrayBuffer>();

    return {
        scope: 'browser_persistent_content_hash',
        async has(url: string): Promise<boolean> {
            if (memoryMirror.has(url)) return true;
            const record = await transactArtifactStore<ArtifactCacheRecord>(
                dbName,
                storeName,
                'readonly',
                store => store.get(url)
            );
            if (!record?.payload) return false;
            memoryMirror.set(url, record.payload);
            return true;
        },
        async read(url: string): Promise<ArrayBuffer | null> {
            const mirrored = memoryMirror.get(url);
            if (mirrored) return cloneArrayBuffer(mirrored);
            const record = await transactArtifactStore<ArtifactCacheRecord>(
                dbName,
                storeName,
                'readonly',
                store => store.get(url)
            );
            if (!record?.payload) return null;
            memoryMirror.set(url, record.payload);
            return cloneArrayBuffer(record.payload);
        },
        async write(url: string, payload: ArrayBuffer): Promise<void> {
            const stored = cloneArrayBuffer(payload);
            memoryMirror.set(url, stored);
            await transactArtifactStore<IDBValidKey>(
                dbName,
                storeName,
                'readwrite',
                store => store.put({
                    url,
                    storedAt: Date.now(),
                    byteLength: stored.byteLength,
                    payload: stored,
                } satisfies ArtifactCacheRecord)
            );
        },
    };
};
