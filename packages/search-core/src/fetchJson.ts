export type FetchResourceType = 'manifest' | 'index' | 'shard' | 'exam-data' | 'default';

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

