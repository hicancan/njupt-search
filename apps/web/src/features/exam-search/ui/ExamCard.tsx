import { Exam } from '@/shared/lib/contracts';

interface ExamCardProps {
    exam: Exam;
    isSelected: boolean;
    onToggle: () => void;
}

const formatDisplayDate = (isoString?: string | null): string => {
    if (!isoString) return '';
    const date = new Date(isoString);
    return date.toLocaleString('zh-CN', {
        month: 'short', day: 'numeric', weekday: 'short', hour: '2-digit', minute: '2-digit'
    });
};

export function ExamCard({ exam, isSelected, onToggle }: ExamCardProps) {
    const isValidTime = !!exam.start_timestamp;

    return (
        <label
            className={`
                block p-5 pl-4 transition-all duration-300 cursor-pointer group border-l-4
                hover:-translate-y-0.5 hover:shadow-[0_4px_12px_rgba(0,0,0,0.05)] dark:hover:shadow-none
                ${isSelected 
                    ? 'border-[#1a73e8] bg-[#f8fafd] dark:bg-[#1a73e8]/10 shadow-[0_1px_3px_rgba(0,0,0,0.02)]' 
                    : 'border-transparent opacity-70 grayscale-[0.5] hover:bg-[#f8f9fa] dark:hover:bg-[#303134]'
                }
            `}
        >
            <div className="flex items-start gap-4">
                <div className="pt-1 relative">
                    <input 
                        type="checkbox" 
                        checked={isSelected}
                        onChange={onToggle}
                        className="sr-only peer"
                    />
                    <div className={`
                        w-5 h-5 rounded border flex items-center justify-center transition-colors duration-200
                        peer-focus-visible:ring-2 peer-focus-visible:ring-offset-2 peer-focus-visible:ring-[var(--color-google-blue)]
                        ${isSelected 
                            ? 'bg-[var(--color-google-blue)] border-[var(--color-google-blue)] dark:bg-[var(--color-google-blue-dark)] dark:border-[var(--color-google-blue-dark)]' 
                            : 'border-[#dadce0] dark:border-[#5f6368] bg-white dark:bg-[#202124] group-hover:border-[#9aa0a6] dark:group-hover:border-[#9aa0a6]'
                        }
                    `}>
                        {isSelected && (
                            <svg className="w-3.5 h-3.5 text-white dark:text-[#202124] draw-check" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                                <polyline points="20 6 9 17 4 12"></polyline>
                            </svg>
                        )}
                    </div>
                </div>
                
                <div className="flex-1">
                    <div className="flex justify-between items-start mb-2 gap-3">
                        <h3 className={`text-[18px] font-normal leading-snug ${isSelected ? 'text-[var(--color-google-blue)] dark:text-[var(--color-google-blue-dark)] group-hover:underline' : 'text-[#202124] dark:text-[#e8eaed]'}`}>
                            {exam.course_name}
                        </h3>
                        {exam.campus && (
                            <span className="shrink-0 text-[12px] text-[#006621] dark:text-[#81c995] bg-[#e6f4ea] dark:bg-[#1e8e3e]/20 px-2.5 py-0.5 rounded">
                                {exam.campus}
                            </span>
                        )}
                    </div>
                    
                    <div className="text-[14px] text-[#4d5156] dark:text-[#bdc1c6] space-y-2.5 mt-1">
                        {isValidTime ? (
                            <div className="flex items-start gap-2">
                                <svg className="w-4 h-4 mt-0.5 shrink-0 text-[#4285f4] dark:text-[#8ab4f8]" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                                <div>
                                    <span className="font-medium text-[#202124] dark:text-[#e8eaed]">{formatDisplayDate(exam.start_timestamp)}</span> 
                                    <span className="mx-1 text-[#70757a]">至</span> 
                                    <span>{formatDisplayDate(exam.end_timestamp)}</span>
                                    <span className="ml-2 text-[12px] px-1.5 py-0.5 bg-[#f1f3f4] dark:bg-[#3c4043] rounded text-[#5f6368] dark:text-[#9aa0a6]">
                                        {exam.duration_minutes} min
                                    </span>
                                </div>
                            </div>
                        ) : (
                            <div className="flex items-center gap-2 text-[#d93025] dark:text-[#f28b82]">
                                <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                                <span><span className="font-medium">时间待定:</span> {exam.raw_time || '未发布'}</span>
                            </div>
                        )}
                        
                        <div className="flex items-start gap-2">
                            <svg className="w-4 h-4 mt-0.5 shrink-0 text-[#ea4335] dark:text-[#f28b82]" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                            <span className="font-medium text-[#202124] dark:text-[#e8eaed]">{exam.location || '待定'}</span>
                        </div>
                        
                        <div className="flex flex-wrap gap-x-5 gap-y-2 pt-1 text-[13px] text-[#70757a] dark:text-[#9aa0a6]">
                            {exam.course_code && (
                                <span className="flex items-center gap-1.5 bg-[#f8f9fa] dark:bg-[#303134] px-2 py-0.5 rounded border border-[#dadce0] dark:border-[#5f6368]">
                                    <span className="text-[#3c4043] dark:text-[#e8eaed]">{exam.course_code}</span>
                                </span>
                            )}
                            <span className="flex items-center gap-1.5">
                                <svg className="w-4 h-4 text-[#34a853] dark:text-[#81c995]" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>
                                {exam.teacher || '未知'}
                            </span>
                            <span className="flex items-center gap-1.5">
                                <svg className="w-4 h-4 text-[#fbbc04] dark:text-[#fdd663]" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" /></svg>
                                {exam.count ?? '-'} 人
                            </span>
                            {exam.notes && <span className="italic">注: {exam.notes}</span>}
                        </div>
                    </div>
                </div>
            </div>
        </label>
    );
}

