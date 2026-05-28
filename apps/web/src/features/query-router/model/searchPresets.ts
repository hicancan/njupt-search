export type QuickSearchIcon =
    | 'calendar'
    | 'shuffle'
    | 'download'
    | 'waypoints'
    | 'trophy'
    | 'file-text';

export interface QuickSearchPreset {
    label: string;
    query: string;
    icon: QuickSearchIcon;
}

export const QUICK_SEARCHES: QuickSearchPreset[] = [
    { label: '考试安排', query: '考试安排', icon: 'calendar' },
    { label: '校历', query: '校历', icon: 'calendar' },
    { label: '教务系统', query: '教务管理系统', icon: 'waypoints' },
    { label: '缓考申请', query: '缓考申请表', icon: 'download' },
    { label: '成绩复核', query: '成绩复核申请表', icon: 'download' },
    { label: '转专业', query: '转专业', icon: 'shuffle' },
    { label: '奖学金', query: '奖学金', icon: 'trophy' },
    { label: '大创', query: '大创', icon: 'trophy' },
];
