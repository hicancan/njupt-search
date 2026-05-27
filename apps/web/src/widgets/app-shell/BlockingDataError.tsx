import { AlertCircle } from 'lucide-react';

interface BlockingDataErrorProps {
    examError: string;
    searchError: string;
}

export function BlockingDataError({ examError, searchError }: BlockingDataErrorProps) {
    return (
        <div className="min-h-screen flex items-center justify-center bg-[#f8fafc] dark:bg-[#171717] text-[#202124] dark:text-[#e8eaed] px-4">
            <div className="max-w-md border border-[#dadce0] dark:border-[#3c4043] rounded-md bg-white dark:bg-[#202124] p-6">
                <AlertCircle className="w-8 h-8 text-[#d93025]" aria-hidden="true" />
                <h1 className="mt-3 text-xl font-semibold">数据加载失败</h1>
                <p className="mt-2 text-sm text-[#4d5156] dark:text-[#bdc1c6]">{examError}</p>
                <p className="mt-1 text-sm text-[#4d5156] dark:text-[#bdc1c6]">{searchError}</p>
            </div>
        </div>
    );
}
