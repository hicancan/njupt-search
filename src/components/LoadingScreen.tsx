export function LoadingScreen() {
    return (
        <div className="min-h-screen bg-white dark:bg-[#202124] text-[#202124] dark:text-[#e8eaed]">
            <div className="max-w-6xl mx-auto px-4 py-10">
                <div className="h-10 w-52 rounded bg-white dark:bg-[#202124] border border-[#dadce0] dark:border-[#3c4043] relative overflow-hidden">
                    <div className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-[#edf2f7] dark:via-white/10 to-transparent animate-shimmer" />
                </div>
                <div className="mt-8 h-[52px] max-w-3xl rounded-full bg-white dark:bg-[#202124] border border-[#dadce0] dark:border-[#3c4043] relative overflow-hidden">
                    <div className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-[#edf2f7] dark:via-white/10 to-transparent animate-shimmer" />
                </div>
                <div className="mt-8 grid grid-cols-1 sm:grid-cols-4 gap-3">
                    {[0, 1, 2, 3].map(item => (
                        <div key={item} className="h-28 rounded-md bg-white dark:bg-[#202124] border border-[#dadce0] dark:border-[#3c4043] relative overflow-hidden">
                            <div className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-[#edf2f7] dark:via-white/10 to-transparent animate-shimmer" />
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}
