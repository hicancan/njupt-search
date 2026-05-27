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
    { label: '转专业', query: '转专业', icon: 'shuffle' },
    { label: '学生表格', query: '学生相关文件及表格', icon: 'download' },
    { label: '教务系统', query: '教务管理系统', icon: 'waypoints' },
    { label: '大创', query: '大创', icon: 'trophy' },
    { label: '规章制度', query: '规章制度', icon: 'file-text' },
];
