import { Code, Download } from 'lucide-react';
import { APP_CONFIG } from '@/app/config/constants';
import { UptimeDisplay } from '@/widgets/app-shell/UptimeDisplay';

export function AppFooter() {
    return (
        <footer className="mt-auto border-t border-[#dadce0] dark:border-[#3c4043] bg-white dark:bg-[#202124] text-sm text-[#70757a] dark:text-[#9aa0a6]">
            <div className="max-w-6xl mx-auto px-4 py-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <div className="flex flex-wrap items-center gap-6">
                    <a href={APP_CONFIG.GITHUB_REPO} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 hover:underline text-[#5f6368] dark:text-[#9aa0a6] hover:text-[#202124] dark:hover:text-[#e8eaed] transition-colors">
                        <Code className="w-4 h-4" aria-hidden="true" />
                        GitHub
                    </a>
                    <a href={APP_CONFIG.BILIBILI_PAGE} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 hover:underline text-[#5f6368] dark:text-[#9aa0a6] hover:text-[#202124] dark:hover:text-[#e8eaed] transition-colors">
                        <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                            <path d="M17.813 4.653h.854c1.51.054 2.769.657 3.773 1.811 1.004 1.154 1.515 2.649 1.536 4.485v5.23c-.021 1.84-.533 3.337-1.536 4.492-1.004 1.154-2.263 1.758-3.773 1.811H5.333c-1.51-.053-2.769-.657-3.773-1.811C.557 19.518.046 18.021.025 16.18V10.95c.021-1.836.532-3.331 1.535-4.485 1.004-1.154 2.263-1.757 3.773-1.81h.854l-1.84-2.002a.81.81 0 01-.137-.735c.05-.24.238-.41.498-.445.195-.027.391.047.525.2l2.361 2.583c.125.136.216.31.263.504h8.286c.046-.194.137-.368.262-.504l2.361-2.583c.134-.153.33-.227.525-.2.26-.035.448.135.498.376.028.14-.012.285-.107.395l-1.871 2.002zm-12.48 2.083c-1.082.02-1.954.4-2.617 1.14-.662.74-1 1.706-1.013 2.898v5.229c.013 1.192.35 2.158 1.013 2.898.663.74 1.535 1.12 2.617 1.14h13.334c1.082-.02 1.954-.4 2.617-1.14.662-.74 1-1.706 1.013-2.898V10.774c-.013-1.192-.35-2.158-1.013-2.898-.663-.74-1.535-1.12-2.617-1.14H5.333zm2.593 3.65c0-.629.566-1.139 1.263-1.139.697 0 1.263.51 1.263 1.139v1.94c0 .63-.566 1.14-1.263 1.14-.697 0-1.263-.51-1.263-1.14v-1.94zm8.258 0c0-.629.566-1.139 1.263-1.139.697 0 1.263.51 1.263 1.139v1.94c0 .63-.566 1.14-1.263 1.14-.697 0-1.263-.51-1.263-1.14v-1.94z"/>
                        </svg>
                        Bilibili
                    </a>
                    <a href="https://github.com/hicancan/njupt-search/releases/latest/download/njupt-search-latest.apk" className="inline-flex items-center gap-1.5 hover:underline text-[#5f6368] dark:text-[#9aa0a6] hover:text-[#202124] dark:hover:text-[#e8eaed] transition-colors">
                        <Download className="w-4 h-4" aria-hidden="true" />
                        Android APK
                    </a>
                </div>
                <div className="flex flex-wrap items-center gap-3 text-xs sm:text-sm">
                    <UptimeDisplay />
                </div>
            </div>
        </footer>
    );
}
