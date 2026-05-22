import { useEffect, useState } from 'react';
import { APP_CONFIG } from '@/constants';
import { SearchDocument, SearchManifest } from '@/types';
import { parseSearchDocuments, parseSearchManifest } from '@/utils/searchIndex';
import { fetchJson } from '@/utils/fetch';

interface UseSearchIndexResult {
    documents: SearchDocument[];
    manifest: SearchManifest | null;
    loading: boolean;
    error: string | null;
}



export function useSearchIndex(): UseSearchIndexResult {
    const [documents, setDocuments] = useState<SearchDocument[]>([]);
    const [manifest, setManifest] = useState<SearchManifest | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const controller = new AbortController();

        Promise.all([
            fetchJson(APP_CONFIG.DATA_URLS.SEARCH_INDEX, controller.signal),
            fetchJson(APP_CONFIG.DATA_URLS.SEARCH_MANIFEST, controller.signal)
        ])
            .then(([documentPayload, manifestPayload]) => {
                setDocuments(parseSearchDocuments(documentPayload, APP_CONFIG.DATA_URLS.SEARCH_INDEX));
                setManifest(parseSearchManifest(manifestPayload, APP_CONFIG.DATA_URLS.SEARCH_MANIFEST));
                setError(null);
            })
            .catch(err => {
                if (err instanceof DOMException && err.name === 'AbortError') {
                    return;
                }
                console.error(err);
                setDocuments([]);
                setManifest(null);
                setError(err instanceof Error ? err.message : '无法加载校园搜索索引');
            })
            .finally(() => {
                if (!controller.signal.aborted) {
                    setLoading(false);
                }
            });

        return () => controller.abort();
    }, []);

    return { documents, manifest, loading, error };
}
