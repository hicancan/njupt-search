import { AlertCircle } from 'lucide-react';

interface InlineErrorBannerProps {
    message: string | null;
}

export function InlineErrorBanner({ message }: InlineErrorBannerProps) {
    if (!message) return null;

    return (
        <div className="max-w-6xl mx-auto w-full px-4 pt-4">
            <div className="border border-[#f4c7c3] dark:border-[#5f2b26] bg-[#fce8e6] dark:bg-[#2b1715] text-[#b3261e] dark:text-[#f28b82] rounded-md p-3 text-sm flex gap-2">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
                <span>{message}</span>
            </div>
        </div>
    );
}
