import { APP_CONFIG } from '@/app/config/constants';
import {
    SitegraphIndexBundle,
    SitegraphSearchFilters,
    SitegraphSearchCoverage,
    SitegraphSearchManifest,
    SitegraphSortMode,
} from '@/shared/lib/contracts';
import { fetchJson } from '@/shared/lib/fetch';
import {
    parseSitegraphDocMeta,
    parseSitegraphInvertedIndex,
    parseSitegraphManifest,
    searchSitegraphProgressively,
    buildSitegraphFilterOptions,
} from '@njupt-search/search-core';

type InitMessage = { type: 'init'; requestId: number };
type QueryMessage = {
    type: 'query';
    requestId: number;
    query: string;
    limit?: number;
    sortMode?: SitegraphSortMode;
    filters?: SitegraphSearchFilters;
};
type CancelMessage = { type: 'cancel'; requestId: number };
type IncomingMessage = InitMessage | QueryMessage | CancelMessage;

let manifest: SitegraphSearchManifest | null = null;
let bundle: SitegraphIndexBundle | null = null;
let activeController: AbortController | null = null;
let activeRequestId: number | null = null;
let lastCoverage: SitegraphSearchCoverage | null = null;

const post = (payload: Record<string, unknown>) => {
    self.postMessage(payload);
};

const publicPath = (path: string): string => {
    if (/^https?:\/\//.test(path) || path.startsWith('/')) return path;
    return `/${path}`;
};

const init = async (requestId: number) => {
    activeController?.abort();
    const controller = new AbortController();
    activeController = controller;
    activeRequestId = requestId;
    const manifestPath = publicPath(APP_CONFIG.DATA_URLS.SEARCH_MANIFEST);
    const manifestPayload = await fetchJson(manifestPath, controller.signal, 'manifest');
    manifest = parseSitegraphManifest(manifestPayload, manifestPath);
    const artifacts = manifest.artifacts;
    const [docMetaPayload, lightIndexPayload, aliasesPayload] = await Promise.all([
        fetchJson(publicPath(artifacts.doc_meta_light.path), controller.signal, 'index'),
        fetchJson(publicPath(artifacts.light_inverted_index.path), controller.signal, 'index'),
        fetchJson(publicPath(artifacts.query_aliases.path), controller.signal, 'index'),
    ]);
    bundle = {
        manifest,
        docMeta: parseSitegraphDocMeta(docMetaPayload, artifacts.doc_meta_light.path),
        lightInvertedIndex: parseSitegraphInvertedIndex(lightIndexPayload, artifacts.light_inverted_index.path),
        queryAliases: aliasesPayload as Record<string, unknown>,
    };
    post({
        type: 'ready',
        requestId,
        manifest,
        filterOptions: buildSitegraphFilterOptions(
            bundle.docMeta,
            Object.fromEntries(manifest.sources.map(source => [source.source_id, source.display_name || source.source_id]))
        ),
        firstScreenBytes: artifacts.doc_meta_light.bytes + artifacts.light_inverted_index.bytes + artifacts.query_aliases.bytes,
    });
};

const query = async (
    requestId: number,
    queryText: string,
    limit = 30,
    sortMode: SitegraphSortMode = 'relevance',
    filters: SitegraphSearchFilters = {}
) => {
    if (!bundle) {
        throw new Error('Search worker is not initialized');
    }
    activeController?.abort();
    const controller = new AbortController();
    activeController = controller;
    activeRequestId = requestId;
    await searchSitegraphProgressively(bundle, queryText, controller.signal, event => {
        lastCoverage = event.coverage;
        post({ ...event, requestId });
    }, { limit, sortMode, filters });
};

self.onmessage = (event: MessageEvent<IncomingMessage>) => {
    const message = event.data;
    if (message.type === 'cancel') {
        if (message.requestId === activeRequestId) {
            activeController?.abort();
            activeController = null;
            activeRequestId = null;
        }
        post({
            type: 'cancelled',
            requestId: message.requestId,
            coverage: lastCoverage ? { ...lastCoverage, phase: 'cancelled', exhaustive_complete: false } : null,
        });
        return;
    }

    const run = message.type === 'init'
        ? init(message.requestId)
        : query(message.requestId, message.query, message.limit, message.sortMode, message.filters);

    run.catch(error => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        post({
            type: 'error',
            requestId: message.requestId,
            message: error instanceof Error ? error.message : String(error),
            coverage: lastCoverage ? { ...lastCoverage, phase: 'error' } : null,
        });
    });
};
