export const fetchJson = async <T = unknown>(url: string, signal?: AbortSignal): Promise<T> => {
    const response = await fetch(url, { cache: 'no-cache', signal });

    if (!response.ok) {
        throw new Error(`数据请求失败: ${url} HTTP ${response.status}`);
    }

    try {
        return await response.json() as T;
    } catch {
        throw new Error(`数据文件不是有效 JSON: ${url}`);
    }
};
