import { useCallback, useMemo, useState } from 'react';
import { Exam } from '@/shared/lib/contracts';

interface SelectionState {
    scope: string | null;
    selectedIds: Set<string>;
}

export const useSelectedExamIds = (className: string | null, exams: Exam[]) => {
    const [selection, setSelection] = useState<SelectionState>({
        scope: null,
        selectedIds: new Set()
    });
    const examIds = useMemo(() => exams.map(exam => exam.id), [exams]);
    const scope = className ? `${className}\u001f${examIds.join('\u001f')}` : null;
    const defaultSelectedIds = useMemo(() => new Set(examIds), [examIds]);

    const selectedIds = selection.scope === scope
        ? selection.selectedIds
        : defaultSelectedIds;

    const toggleExamSelection = useCallback((id: string) => {
        if (!scope) return;

        setSelection(prev => {
            const base = prev.scope === scope ? prev.selectedIds : defaultSelectedIds;
            const next = new Set(base);
            if (next.has(id)) {
                next.delete(id);
            } else {
                next.add(id);
            }
            return { scope, selectedIds: next };
        });
    }, [defaultSelectedIds, scope]);

    return { selectedIds, toggleExamSelection };
};
