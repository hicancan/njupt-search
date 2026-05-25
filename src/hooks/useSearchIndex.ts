import { useEffect, useState } from 'react';
import { APP_CONFIG } from '@/constants';
import { SearchDocument, SearchManifest } from '@/types';
import { parseSearchDocuments, parseSearchManifest } from '@/utils/searchIndex';
import { fetchJson } from '@/utils/fetch';

interface UseSearchIndexResult {
    documents: SearchDocument[];
    manifest: SearchManifest | null;
    queryAliases: Record<string, unknown>;
    ontology: Record<string, unknown> | null;
    optionalUnavailable: string[];
    loading: boolean;
    error: string | null;
}



export function useSearchIndex(): UseSearchIndexResult {
    const [documents, setDocuments] = useState<SearchDocument[]>([]);
    const [manifest, setManifest] = useState<SearchManifest | null>(null);
    const [queryAliases, setQueryAliases] = useState<Record<string, unknown>>({});
    const [ontology, setOntology] = useState<Record<string, unknown> | null>(null);
    const [optionalUnavailable, setOptionalUnavailable] = useState<string[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const controller = new AbortController();

        const load = async () => {
            const [documentPayload, manifestPayload] = await Promise.all([
                fetchJson(APP_CONFIG.DATA_URLS.SEARCH_INDEX, controller.signal),
                fetchJson(APP_CONFIG.DATA_URLS.SEARCH_MANIFEST, controller.signal)
            ]);

            const parsedDocuments = parseSearchDocuments(documentPayload, APP_CONFIG.DATA_URLS.SEARCH_INDEX);
            const parsedManifest = parseSearchManifest(manifestPayload, APP_CONFIG.DATA_URLS.SEARCH_MANIFEST);

            const optionalResults = await Promise.allSettled([
                fetchJson(APP_CONFIG.DATA_URLS.QUERY_ALIASES, controller.signal),
                fetchJson(APP_CONFIG.DATA_URLS.ONTOLOGY, controller.signal)
            ]);
            const unavailable: string[] = [];
            const [aliasesResult, ontologyResult] = optionalResults;

            if (aliasesResult?.status === 'fulfilled') {
                setQueryAliases(aliasesResult.value as Record<string, unknown>);
            } else {
                setQueryAliases({});
                unavailable.push('query_aliases');
            }

            if (ontologyResult?.status === 'fulfilled') {
                setOntology(ontologyResult.value as Record<string, unknown>);
            } else {
                setOntology(null);
                unavailable.push('ontology');
            }

            setOptionalUnavailable(unavailable);
            if (unavailable.length > 0) {
                console.warn(`Optional search features unavailable: ${unavailable.join(', ')}`);
            }

            setDocuments(parsedDocuments);
            setManifest(parsedManifest);
            setError(null);
        };

        load()
            .catch(err => {
                if (err instanceof DOMException && err.name === 'AbortError') {
                    return;
                }
                console.error(err);
                setDocuments([]);
                setManifest(null);
                setQueryAliases({});
                setOntology(null);
                setOptionalUnavailable([]);
                setError(err instanceof Error ? err.message : '无法加载校园搜索索引');
            })
            .finally(() => {
                if (!controller.signal.aborted) {
                    setLoading(false);
                }
            });

        return () => controller.abort();
    }, []);

    return { documents, manifest, queryAliases, ontology, optionalUnavailable, loading, error };
}
