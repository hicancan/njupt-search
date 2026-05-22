import { useEffect, useRef, useState } from 'react';
import { Search, X } from 'lucide-react';

const SEARCH_SUGGESTIONS = [
    '搜考试安排',
    '搜奖学金公示',
    '搜竞赛报名',
    '搜讲座活动',
    '搜招聘宣讲',
    '搜图书馆开放',
    '搜停水停电',
    '搜 B250403'
];

interface SearchInputProps {
    value: string;
    onChange: (value: string) => void;
    placeholder?: string;
    autoFocus?: boolean;
    onSubmit?: (value: string) => void;
}

export function SearchInput({
    value,
    onChange,
    placeholder,
    autoFocus = true,
    onSubmit
}: SearchInputProps) {
    const inputRef = useRef<HTMLInputElement>(null);
    const suggestionIndexRef = useRef(0);
    const charIndexRef = useRef(0);
    const directionRef = useRef<1 | -1>(1);
    const [dynamicPlaceholder, setDynamicPlaceholder] = useState(SEARCH_SUGGESTIONS[0]);

    useEffect(() => {
        if (autoFocus) {
            inputRef.current?.focus();
        }
    }, [autoFocus]);

    useEffect(() => {
        if (placeholder) return;

        let timeoutId = 0;
        const tick = () => {
            const suggestion = SEARCH_SUGGESTIONS[suggestionIndexRef.current] ?? '搜考试安排';
            const nextLength = charIndexRef.current + directionRef.current;
            charIndexRef.current = nextLength;
            setDynamicPlaceholder(suggestion.slice(0, Math.max(1, nextLength)));

            let delay = directionRef.current === 1 ? 82 : 46;
            if (nextLength >= suggestion.length) {
                directionRef.current = -1;
                delay = 1050;
            } else if (nextLength <= 1) {
                directionRef.current = 1;
                suggestionIndexRef.current = (suggestionIndexRef.current + 1) % SEARCH_SUGGESTIONS.length;
                delay = 260;
            }

            timeoutId = window.setTimeout(tick, delay);
        };

        timeoutId = window.setTimeout(tick, 520);
        return () => window.clearTimeout(timeoutId);
    }, [placeholder]);

    const clearInput = () => {
        onChange('');
        inputRef.current?.focus();
    };

    return (
        <form 
            className="relative w-full z-20 group"
            onSubmit={(e) => {
                e.preventDefault();
                onSubmit?.(value);
            }}
        >
            <label htmlFor="njupt-search" className="sr-only">搜索南邮信息</label>
            <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-[#9aa0a6] transition-all duration-300 group-focus-within:text-[var(--color-google-blue)] dark:group-focus-within:text-[var(--color-google-blue-dark)] group-focus-within:scale-110">
                <Search className="w-5 h-5" aria-hidden="true" />
            </div>
            <input
                id="njupt-search"
                ref={inputRef}
                type="text"
                autoComplete="off"
                aria-label="搜索南邮信息"
                className="w-full h-[52px] pl-12 pr-12 bg-white dark:bg-[#202124] border border-[#dfe1e5] dark:border-[#5f6368] rounded-full text-[16px] leading-normal outline-none hover:shadow-[0_1px_6px_rgba(32,33,36,0.18)] dark:hover:shadow-[0_1px_6px_rgba(23,23,23,0.8)] focus:shadow-[0_1px_6px_rgba(32,33,36,0.22)] dark:focus:shadow-[0_1px_6px_rgba(23,23,23,0.8)] hover:border-[#cfd4dc] focus:border-[#8ab4f8] transition-all text-[#202124] dark:text-[#e8eaed] placeholder:text-[#70757a] dark:placeholder:text-[#9aa0a6]"
                placeholder={placeholder || dynamicPlaceholder}
                value={value}
                onChange={(e) => onChange(e.target.value)}
            />
            {value && (
                <button 
                    type="button" 
                    onClick={clearInput}
                    aria-label="清空搜索"
                    className="absolute inset-y-0 right-0 pr-4 flex items-center text-[#70757a] hover:text-[#202124] dark:text-[#9aa0a6] dark:hover:text-white"
                >
                    <X className="w-5 h-5" aria-hidden="true" />
                </button>
            )}
        </form>
    );
}
