import { useRef, useEffect } from 'react';

interface SearchInputProps {
    value: string;
    onChange: (value: string) => void;
}

export function SearchInput({ value, onChange }: SearchInputProps) {
    const inputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        // Auto focus on mount
        inputRef.current?.focus();
    }, []);

    const clearInput = () => {
        onChange('');
        inputRef.current?.focus();
    };

    return (
        <div className="relative w-full z-20 group">
            <label htmlFor="class-search" className="sr-only">输入班级号进行搜索</label>
            <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-[#9aa0a6] transition-all duration-300 group-focus-within:text-[var(--color-google-blue)] dark:group-focus-within:text-[var(--color-google-blue-dark)] group-focus-within:scale-110">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
                </svg>
            </div>
            <input
                id="class-search"
                ref={inputRef}
                type="text"
                autoComplete="off"
                aria-label="输入班级号进行搜索"
                className="w-full h-[46px] pl-12 pr-12 bg-white dark:bg-[#202124] border border-[#dfe1e5] dark:border-[#5f6368] rounded-full text-[16px] leading-normal outline-none hover:shadow-[0_1px_6px_rgba(32,33,36,0.28)] dark:hover:shadow-[0_1px_6px_rgba(23,23,23,0.8)] focus:shadow-[0_1px_6px_rgba(32,33,36,0.28)] dark:focus:shadow-[0_1px_6px_rgba(23,23,23,0.8)] hover:border-transparent focus:border-transparent transition-all text-[#202124] dark:text-[#bdc1c6]"
                placeholder="输入班级号 (如 B250403)"
                value={value}
                onChange={(e) => onChange(e.target.value)}
            />
            {value && (
                <button 
                    type="button" 
                    onClick={clearInput}
                    className="absolute inset-y-0 right-0 pr-4 flex items-center text-[#70757a] hover:text-[#202124] dark:text-[#9aa0a6] dark:hover:text-white"
                >
                    <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                    </svg>
                </button>
            )}
        </div>
    );
}
