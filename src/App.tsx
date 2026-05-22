import { useState, useEffect } from 'react';
import { UptimeDisplay } from './components/UptimeDisplay';
import { ThemeToggle } from './components/ThemeToggle';
import { SearchInput } from './components/SearchInput';
import { ExamList } from './components/ExamList';
import { ExamDetail } from './components/ExamDetail';
import { Logo } from './components/Logo';
import { APP_CONFIG } from '@/constants';
import { useExamData } from '@/hooks/useExamData';
import { useClassSearch } from '@/hooks/useClassSearch';
import { useSelectedExamIds } from '@/hooks/useSelectedExamIds';
import { usePwaInstall } from '@/hooks/usePwaInstall';

function App() {
    const { exams: allExams, loading, error, sourceUrl, sourceTitle, generatedAt, totalRecords } = useExamData();
    const { canInstall, install } = usePwaInstall();

    // UI State
    const [inputValue, setInputValue] = useState<string>(() => {
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get('class')?.toUpperCase() || '';
    });
    const [manualSelection, setManualSelection] = useState<string | null>(() => {
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get('class')?.toUpperCase() || null;
    });
    const [reminders, setReminders] = useState<number[]>([30, 60]);

    const searchResult = useClassSearch(allExams, inputValue, manualSelection);
    const currentClass = searchResult.mode === 'DETAIL' ? searchResult.classes[0] || null : null;
    const { selectedIds, toggleExamSelection } = useSelectedExamIds(currentClass, searchResult.exams);

    useEffect(() => {
        if (searchResult.mode === 'DETAIL' && currentClass && searchResult.exams.length > 0) {
            const query = new URLSearchParams({ class: currentClass }).toString();
            const newUrl = `${window.location.pathname}?${query}`;
            window.history.replaceState(null, '', newUrl);
        } else if (searchResult.mode === 'EMPTY') {
            window.history.replaceState(null, '', window.location.pathname);
        }
    }, [currentClass, searchResult.exams.length, searchResult.mode]);

    const handleInput = (val: string) => {
        setInputValue(val);
        if (manualSelection && val !== manualSelection) {
            setManualSelection(null);
        }
    };

    const handleClassClick = (cls: string) => {
        setInputValue(cls);
        setManualSelection(cls);
    };

    if (loading) return (
        <div className="min-h-screen flex items-center justify-center bg-white dark:bg-[var(--color-google-bg-dark)] text-[#70757a] dark:text-[#9aa0a6]">
            <div className="flex flex-col items-center gap-4">
                <div className="w-8 h-8 border-4 border-[var(--color-google-blue)] dark:border-[var(--color-google-blue-dark)] border-t-transparent rounded-full animate-spin"></div>
                <span className="text-[14px]">数据同步中...</span>
            </div>
        </div>
    );

    if (error) return (
        <div className="min-h-screen flex items-center justify-center bg-white dark:bg-[var(--color-google-bg-dark)]">
            <div className="p-6 text-center text-[#d93025] dark:text-[#f28b82]">
                <div className="text-3xl mb-3">⚠️</div>
                <p className="text-[14px]">{error}</p>
            </div>
        </div>
    );

    const isHomePage = searchResult.mode === 'EMPTY';

    return (
        <div className="min-h-screen flex flex-col bg-white dark:bg-[var(--color-google-bg-dark)] text-[#202124] dark:text-[#bdc1c6] transition-colors duration-200 font-sans">
            {!isHomePage && (
                <header className="border-b border-[#ebebeb] dark:border-[#3c4043] pb-4 pt-4 sm:pt-6 relative sticky top-0 bg-white dark:bg-[var(--color-google-bg-dark)] z-30">
                    {/* Mobile Top Row */}
                    <div className="w-full flex justify-between items-center mb-4 sm:hidden px-4">
                        <div className="flex-shrink-0 flex items-center cursor-pointer" onClick={() => handleInput('')}>
                            <Logo size="small" />
                        </div>
                        <div>
                            <ThemeToggle />
                        </div>
                    </div>

                    {/* Desktop Absolute Logo */}
                    <div className="hidden sm:flex sm:absolute sm:left-8 sm:top-1/2 sm:-translate-y-1/2 flex-shrink-0 items-center cursor-pointer" onClick={() => handleInput('')}>
                        <Logo size="small" />
                    </div>
                    
                    <div className="w-full max-w-[730px] mx-auto flex justify-center px-4 relative z-10">
                        <SearchInput value={inputValue} onChange={handleInput} />
                    </div>
                    
                    {/* Desktop Absolute Theme Toggle */}
                    <div className="hidden sm:flex sm:absolute sm:right-8 sm:top-1/2 sm:-translate-y-1/2 items-center gap-4">
                        <ThemeToggle />
                    </div>
                </header>
            )}

            {isHomePage && (
                <header className="absolute top-0 left-0 right-0 p-4 sm:px-6 flex justify-between items-center z-50">
                    <div className="text-[14px] text-[#4d5156] dark:text-[#bdc1c6] pt-1">
                        <a href={`https://${APP_CONFIG.DOMAIN}`} className="hover:underline">{APP_CONFIG.DOMAIN}</a>
                    </div>
                    <div>
                        <ThemeToggle />
                    </div>
                </header>
            )}

            <main className={`flex-1 w-full flex flex-col ${isHomePage ? 'items-center justify-center px-4 pb-32' : 'max-w-[730px] mx-auto px-4 py-4'}`}>
                {isHomePage && (
                    <div className="w-full max-w-[584px] flex flex-col items-center">
                        <Logo size="large" />
                        <div className="w-full">
                            <SearchInput value={inputValue} onChange={handleInput} />
                        </div>
                        <div className="mt-8 flex flex-row justify-center gap-3 w-full">
                            {canInstall ? (
                                <button 
                                    onClick={install}
                                    className="bg-[#f8f9fa] dark:bg-[#303134] text-[#3c4043] dark:text-[#e8eaed] border border-[#f8f9fa] dark:border-[#303134] hover:border-[#dadce0] dark:hover:border-[#5f6368] hover:shadow-sm px-4 py-2 rounded text-sm transition-all focus:outline-none focus:ring-2 focus:ring-[var(--color-google-blue)] whitespace-nowrap"
                                >
                                    添加到主屏幕 (PWA)
                                </button>
                            ) : (
                                <button 
                                    disabled
                                    className="bg-[#f8f9fa] dark:bg-[#303134] text-[#3c4043] dark:text-[#e8eaed] border border-[#f8f9fa] dark:border-[#303134] opacity-50 cursor-not-allowed px-4 py-2 rounded text-sm whitespace-nowrap"
                                    title="当前环境不支持或已安装"
                                >
                                    添加到主屏幕 (PWA)
                                </button>
                            )}
                            <a 
                                href="https://github.com/hicancan/njupt-exam/releases/latest/download/app-release.apk"
                                className="bg-[#f8f9fa] dark:bg-[#303134] text-[#3c4043] dark:text-[#e8eaed] border border-[#f8f9fa] dark:border-[#303134] hover:border-[#dadce0] dark:hover:border-[#5f6368] hover:shadow-sm px-4 py-2 rounded text-sm transition-all focus:outline-none focus:ring-2 focus:ring-[var(--color-google-blue)] whitespace-nowrap"
                            >
                                下载 Android APK
                            </a>
                        </div>
                    </div>
                )}

                <div className="w-full">
                    {!isHomePage && searchResult.mode === 'NOT_FOUND' && (
                        <div className="py-4 text-[#4d5156] dark:text-[#bdc1c6]">
                            <p>找不到和您查询的 <span className="font-bold text-red-500">"{inputValue}"</span> 相符的班级。</p>
                            <p className="mt-4">建议：</p>
                            <ul className="list-disc pl-8 mt-2 space-y-1">
                                <li>请检查输入是否正确。</li>
                                <li>目前仅支持按班级号搜索（如 B250403）。</li>
                            </ul>
                        </div>
                    )}

                    {!isHomePage && searchResult.mode === 'LIST' && (
                        <ExamList
                            classes={searchResult.classes}
                            onClassClick={handleClassClick}
                        />
                    )}

                    {!isHomePage && searchResult.mode === 'DETAIL' && (
                        <ExamDetail
                            className={searchResult.classes[0] || ''}
                            exams={searchResult.exams}
                            selectedIds={selectedIds}
                            onToggleSelection={toggleExamSelection}
                            reminders={reminders}
                            onRemindersChange={setReminders}
                            sourceUrl={sourceUrl}
                            sourceTitle={sourceTitle}
                            generatedAt={generatedAt}
                            totalRecords={totalRecords}
                        />
                    )}
                </div>
            </main>

            <footer className="bg-[#f2f2f2] dark:bg-[#171717] text-[#70757a] dark:text-[#9aa0a6] text-sm border-t border-[#dadce0] dark:border-[#3c4043]">
                <div className="px-8 py-3 flex flex-col lg:flex-row justify-between lg:items-center gap-4">
                    <div className="flex w-full lg:w-auto justify-between lg:justify-start items-center gap-6">
                        <a href={APP_CONFIG.GITHUB_REPO} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1.5 hover:underline group">
                            <svg className="w-4 h-4 fill-current opacity-70 group-hover:opacity-100 transition-opacity" viewBox="0 0 24 24"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" /></svg>
                            <span>GitHub</span>
                        </a>
                        <a href={APP_CONFIG.BILIBILI_PAGE} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1.5 hover:underline group">
                            <svg className="w-4 h-4 fill-current opacity-70 group-hover:opacity-100 hover:text-[#FB7299] transition-all" viewBox="0 0 24 24"><path d="M17.813 4.653h.854c1.51.054 2.769.578 3.773 1.574 1.004.995 1.524 2.249 1.56 3.76v7.36c-.036 1.51-.556 2.769-1.56 3.773-1.004.996-2.264 1.52-3.773 1.574H5.333c-1.51-.054-2.77-.578-3.773-1.574-1.005-.995-1.525-2.249-1.561-3.76v-7.36c.036-1.511.556-2.765 1.561-3.76 1.003-.996 2.264-1.52 3.773-1.574h.854l-1.99-1.99a.633.633 0 0 1-.186-.464.633.633 0 0 1 .186-.465c.123-.124.278-.186.464-.186.186 0 .341.062.465.186l2.36 2.36h2.827l2.365-2.36a.633.633 0 0 1 .465-.186.633.633 0 0 1 .186.465.633.633 0 0 1-.186.464l-1.995 1.99zM6.933 9.453c-.63 0-1.14.51-1.14 1.14 0 .63.51 1.14 1.14 1.14.63 0 1.14-.51 1.14-1.14 0-.63-.51-1.14-1.14-1.14zm9.334 0c-.63 0-1.14.51-1.14 1.14 0 .63.51 1.14 1.14 1.14.63 0 1.14-.51 1.14-1.14 0-.63-.51-1.14-1.14-1.14z" /></svg>
                            <span>Bilibili</span>
                        </a>
                    </div>
                    <div className="flex w-full lg:w-auto justify-between lg:justify-end items-center gap-6">
                        <UptimeDisplay />
                    </div>
                </div>
            </footer>
        </div>
    );
}

export default App;
