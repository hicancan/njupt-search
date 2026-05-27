import { useState, useEffect } from 'react';
import { APP_CONFIG } from '@/app/config/constants';

interface UptimeDisplayProps {
    startTime?: string;
}

export function UptimeDisplay({
    startTime = APP_CONFIG.START_TIME_DEFAULT
}: UptimeDisplayProps) {
    const [uptime, setUptime] = useState<string>('');

    useEffect(() => {
        const start = new Date(startTime);
        const updateTimer = () => {
            const diff = new Date().getTime() - start.getTime();
            const days = Math.floor(diff / (1000 * 60 * 60 * 24));
            const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
            const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
            const seconds = Math.floor((diff % (1000 * 60)) / 1000);
            setUptime(`${days}天 ${hours}小时 ${minutes}分 ${seconds}秒`);
        };
        const timer = setInterval(updateTimer, 1000);
        updateTimer();
        return () => clearInterval(timer);
    }, [startTime]);

    return (
        <>
            <span className="whitespace-nowrap">
                已运行 <span className="font-mono text-[var(--color-google-blue)] dark:text-[var(--color-google-blue-dark)]">{uptime}</span>
            </span>
            <span className="hidden lg:inline text-[#dadce0] dark:text-[#3c4043]">|</span>
            <img
                src={APP_CONFIG.VISITOR_BADGE_URL}
                className="h-4 w-auto opacity-80 hover:opacity-100 transition-opacity grayscale hover:grayscale-0"
                alt="visitor count"
                loading="lazy"
            />
        </>
    );
}
