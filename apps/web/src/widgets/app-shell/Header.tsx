import { SearchInput } from '@/widgets/search-box/SearchInput';
import { ThemeToggle } from '@/widgets/app-shell/ThemeToggle';

interface HeaderProps {
    inputValue: string;
    onInputChange: (value: string) => void;
    onSubmit: (value: string) => void;
    onGoHome: () => void;
}

export function Header({ inputValue, onInputChange, onSubmit, onGoHome }: HeaderProps) {
    return (
        <header className="sticky top-0 z-40 border-b border-[#dadce0] dark:border-[#3c4043] bg-white/95 dark:bg-[#202124]/95 backdrop-blur">
            <div className="max-w-6xl mx-auto px-4 py-3 flex items-center gap-4">
                <button
                    type="button"
                    onClick={onGoHome}
                    className="flex items-center gap-2 shrink-0 text-left sm:w-[140px]"
                    aria-label="回到 njupt-search 首页"
                >
                    <img src="/assets/logo.png" alt="" className="w-8 h-8 rounded-md" />
                    <div className="hidden sm:block font-semibold leading-tight text-[#202124] dark:text-[#e8eaed]">
                        njupt-search
                    </div>
                </button>
                <div className="flex-1 min-w-0 max-w-[692px]">
                    <SearchInput value={inputValue} onChange={onInputChange} onSubmit={onSubmit} autoFocus={false} />
                </div>
                <ThemeToggle />
            </div>
        </header>
    );
}
