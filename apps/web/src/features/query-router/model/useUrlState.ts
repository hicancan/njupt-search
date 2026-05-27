import { useState, useEffect, useCallback } from 'react';

interface UrlState {
    classParam: string | null;
    qParam: string | null;
}

export function useUrlState() {
    const [state, setState] = useState<UrlState>(() => {
        const params = new URLSearchParams(window.location.search);
        return {
            classParam: params.get('class')?.toUpperCase() || null,
            qParam: params.get('q') || null
        };
    });

    useEffect(() => {
        const handlePopState = () => {
            const params = new URLSearchParams(window.location.search);
            setState({
                classParam: params.get('class')?.toUpperCase() || null,
                qParam: params.get('q') || null
            });
        };
        window.addEventListener('popstate', handlePopState);
        return () => window.removeEventListener('popstate', handlePopState);
    }, []);

    const navigate = useCallback((params: Record<string, string | null>, replace = false) => {
        const newParams = new URLSearchParams();
        Object.entries(params).forEach(([key, value]) => {
            if (value) {
                newParams.set(key, value);
            }
        });
        
        const nextSearch = newParams.toString();
        const nextUrl = nextSearch ? `${window.location.pathname}?${nextSearch}` : window.location.pathname;
        
        const currentSearch = window.location.search.replace(/^\?/, '');
        
        if (currentSearch !== nextSearch) {
            if (replace) {
                window.history.replaceState(null, '', nextUrl);
            } else {
                window.history.pushState(null, '', nextUrl);
            }
            setState({
                classParam: newParams.get('class')?.toUpperCase() || null,
                qParam: newParams.get('q') || null
            });
        }
    }, []);

    return { ...state, navigate };
}
