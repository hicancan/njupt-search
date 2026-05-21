
import { APP_CONFIG } from '@/constants';

interface ExamListProps {
    classes: string[];
    onClassClick: (className: string) => void;
}

export function ExamList({ classes, onClassClick }: ExamListProps) {
    const displayClasses = classes.slice(0, APP_CONFIG.MAX_CLASS_DISPLAY_COUNT);
    const hasMore = classes.length > APP_CONFIG.MAX_CLASS_DISPLAY_COUNT;

    return (
        <div className="w-full mt-2">
            <div className="text-[14px] text-[#70757a] dark:text-[#9aa0a6] mb-6">
                请选择具体的班级，共找到 {classes.length} 个匹配项：
            </div>
            
            <div className="flex flex-wrap gap-3">
                {displayClasses.map((cls, index) => (
                    <button 
                        key={index} 
                        onClick={() => onClassClick(cls)}
                        className="px-5 py-2.5 bg-white dark:bg-[#202124] border border-[#dadce0] dark:border-[#5f6368] rounded-full text-[15px] text-[#1a0dab] dark:text-[#8ab4f8] hover:bg-[#f8f9fa] dark:hover:bg-[#303134] hover:border-[#d2e3fc] dark:hover:border-[#8ab4f8]/30 transition-all shadow-sm hover:shadow active:scale-95 flex items-center gap-2"
                    >
                        <span>{cls}</span>
                        <svg className="w-3.5 h-3.5 opacity-60" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" />
                        </svg>
                    </button>
                ))}
            </div>

            {hasMore && (
                <p className="text-center text-sm text-[var(--color-google-grey)] dark:text-[var(--color-google-grey-dark)] mt-10 pb-10">
                    为提供最相关的结果，我们省略了部分相似的条目，请继续输入以精确查找。
                </p>
            )}
        </div>
    );
}
