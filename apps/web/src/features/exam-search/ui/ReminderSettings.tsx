interface ReminderSettingsProps {
    selected: number[];
    onChange: (reminders: number[]) => void;
}

export function ReminderSettings({ selected, onChange }: ReminderSettingsProps) {
    const options = [
        { value: 15, label: '15分钟前' },
        { value: 30, label: '30分钟前' },
        { value: 60, label: '1小时前' },
        { value: 1440, label: '1天前' },
    ];

    const toggleOption = (val: number) => {
        if (selected.includes(val)) {
            onChange(selected.filter(v => v !== val));
        } else {
            onChange([...selected, val].sort((a, b) => a - b));
        }
    };

    return (
        <div className="bg-[#f8f9fa] dark:bg-[#202124] rounded-lg p-4 mb-6">
            <div className="flex items-center gap-2 mb-3">
                <svg className="w-5 h-5 text-[#fbbc05]" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
                </svg>
                <h3 className="font-medium text-[#202124] dark:text-[#e8eaed] text-[14px]">考前提醒设置</h3>
            </div>
            <div className="flex flex-wrap gap-2">
                {options.map(opt => {
                    const isActive = selected.includes(opt.value);
                    return (
                        <button
                            type="button"
                            key={opt.value}
                            onClick={() => toggleOption(opt.value)}
                            className={`px-4 py-1.5 rounded-full text-[13px] font-medium transition-all border
                                ${isActive
                                    ? 'bg-[#e8f0fe] dark:bg-[#8ab4f8]/20 text-[var(--color-google-blue)] dark:text-[#8ab4f8] border-transparent'
                                    : 'bg-white dark:bg-[#303134] text-[#5f6368] dark:text-[#bdc1c6] border-[#dadce0] dark:border-[#5f6368] hover:bg-[#f8f9fa] dark:hover:bg-[#3c4043]'
                                }`}
                        >
                            {opt.label}
                        </button>
                    );
                })}
            </div>
        </div>
    );
}

