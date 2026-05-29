import { useEffect, useRef, useState } from 'react';
import { SitegraphFilterOptions, SitegraphSearchManifest } from '@/shared/lib/contracts';

interface UseSearchIndexWorkerResult {
    worker: Worker | null;
    manifest: SitegraphSearchManifest | null;
    filterOptions: SitegraphFilterOptions | null;
    loading: boolean;
    error: string | null;
}

export function useSearchIndexWorker(enabled = true): UseSearchIndexWorkerResult {
    const workerRef = useRef<Worker | null>(null);
    const requestIdRef = useRef(0);
    const [workerState, setWorkerState] = useState<Worker | null>(null);
    const [manifest, setManifest] = useState<SitegraphSearchManifest | null>(null);
    const [filterOptions, setFilterOptions] = useState<SitegraphFilterOptions | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!enabled) {
            return;
        }

        const worker = new Worker(new URL('../worker/collectionSearch.worker.ts', import.meta.url), { type: 'module' });
        const requestId = ++requestIdRef.current;
        workerRef.current = worker;

        worker.onmessage = (event: MessageEvent) => {
            const message = event.data as {
                type?: string;
                requestId?: number;
                manifest?: SitegraphSearchManifest;
                filterOptions?: SitegraphFilterOptions;
                message?: string;
            };
            if (message.requestId !== requestId) return;
            if (message.type === 'ready' && message.manifest) {
                setManifest(message.manifest);
                setFilterOptions(message.filterOptions || null);
                setWorkerState(worker);
                setError(null);
            } else if (message.type === 'error') {
                setManifest(null);
                setFilterOptions(null);
                setWorkerState(null);
                setError(message.message || '无法加载南邮官网信息搜索索引 Worker');
            }
        };
        worker.onerror = event => {
            setManifest(null);
            setFilterOptions(null);
            setWorkerState(null);
            setError(event.message || '南邮官网信息搜索 Worker 启动失败');
        };
        worker.postMessage({ type: 'init', requestId });

        return () => {
            worker.terminate();
            if (workerRef.current === worker) {
                workerRef.current = null;
                setWorkerState(null);
                setFilterOptions(null);
            }
        };
    }, [enabled]);

    return {
        worker: enabled ? workerState : null,
        manifest: enabled ? manifest : null,
        filterOptions: enabled ? filterOptions : null,
        loading: enabled && !workerState && !error,
        error: enabled ? error : null
    };
}
