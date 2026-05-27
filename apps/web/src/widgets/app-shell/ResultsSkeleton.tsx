export function ResultsSkeleton() {
    return (
        <div className="w-full">
            <div className="flex gap-6 border-b border-[#dadce0] dark:border-[#3c4043] pb-0 mb-4 overflow-hidden">
                {[0, 1, 2, 3, 4].map(item => (
                    <div key={item} className="h-4 w-12 mb-3 bg-[#f1f3f4] dark:bg-[#303134] rounded relative overflow-hidden shrink-0">
                        <div className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/40 dark:via-white/10 to-transparent animate-shimmer" />
                    </div>
                ))}
            </div>
            
            <div className="mt-8 space-y-8">
                {[0, 1, 2, 3].map(item => (
                    <div key={item} className="max-w-[692px]">
                        <div className="flex items-center gap-2 mb-2">
                            <div className="h-3 w-32 bg-[#f1f3f4] dark:bg-[#303134] rounded relative overflow-hidden">
                                <div className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/40 dark:via-white/10 to-transparent animate-shimmer" />
                            </div>
                        </div>
                        <div className="h-6 w-3/4 bg-[#f1f3f4] dark:bg-[#303134] rounded relative overflow-hidden mb-3">
                            <div className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/40 dark:via-white/10 to-transparent animate-shimmer" />
                        </div>
                        <div className="flex gap-2 mb-3">
                            <div className="h-5 w-12 bg-[#f1f3f4] dark:bg-[#303134] rounded relative overflow-hidden"></div>
                            <div className="h-5 w-16 bg-[#f1f3f4] dark:bg-[#303134] rounded relative overflow-hidden"></div>
                        </div>
                        <div className="space-y-2">
                            <div className="h-3.5 w-full bg-[#f1f3f4] dark:bg-[#303134] rounded relative overflow-hidden">
                                <div className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/40 dark:via-white/10 to-transparent animate-shimmer" />
                            </div>
                            <div className="h-3.5 w-5/6 bg-[#f1f3f4] dark:bg-[#303134] rounded relative overflow-hidden">
                                <div className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/40 dark:via-white/10 to-transparent animate-shimmer" />
                            </div>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
