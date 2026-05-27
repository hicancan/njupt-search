interface DataUpdateToastProps {
    visible: boolean;
    onRefresh: () => void;
}

export function DataUpdateToast({ visible, onRefresh }: DataUpdateToastProps) {
    if (!visible) return null;

    return (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[100] fade-in">
            <div className="bg-[#1a73e8] text-white px-5 py-3 rounded-full shadow-lg flex items-center gap-3 text-sm font-medium whitespace-nowrap border border-transparent dark:border-[#3c4043]">
                <span>发现最新校园索引数据</span>
                <button
                    type="button"
                    onClick={onRefresh}
                    className="bg-white text-[#1a73e8] px-4 py-1.5 rounded-full hover:bg-gray-100 transition-colors cursor-pointer"
                >
                    立刻刷新
                </button>
            </div>
        </div>
    );
}
