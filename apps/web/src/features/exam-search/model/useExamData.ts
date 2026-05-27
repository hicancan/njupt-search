import { useState, useEffect } from 'react';
import { APP_CONFIG } from '@/app/config/constants';
import { assertManifestMatchesExams, parseExamData, parseManifest } from '@/features/exam-search/lib/examDataContract';
import { fetchJson } from '@/shared/lib/fetch';
import { Exam, Manifest } from '@/shared/lib/contracts';

interface UseExamDataResult {
    exams: Exam[];
    loading: boolean;
    error: string | null;
    sourceUrl: string | null;
    sourceTitle: string | null;
    generatedAt: string | null;
    totalRecords: number | null;
}



export function useExamData(enabled = true): UseExamDataResult {
    const [exams, setExams] = useState<Exam[]>([]);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);
    const [sourceUrl, setSourceUrl] = useState<string | null>(null);
    const [sourceTitle, setSourceTitle] = useState<string | null>(null);
    const [generatedAt, setGeneratedAt] = useState<string | null>(null);
    const [totalRecords, setTotalRecords] = useState<number | null>(null);

    useEffect(() => {
        if (!enabled) {
            return;
        }

        const controller = new AbortController();

        Promise.all([
            fetchJson(APP_CONFIG.DATA_URLS.EXAMS, controller.signal, 'exam-data'),
            fetchJson(APP_CONFIG.DATA_URLS.SUMMARY, controller.signal, 'exam-data')
        ])
            .then(([examsPayload, manifestPayload]) => {
                const examsData = parseExamData(examsPayload, APP_CONFIG.DATA_URLS.EXAMS);
                const manifestData: Manifest = parseManifest(manifestPayload, APP_CONFIG.DATA_URLS.SUMMARY);
                assertManifestMatchesExams(manifestData, examsData);

                const sortedExams = [...examsData].sort((a, b) => {
                    if (a.start_timestamp && b.start_timestamp) {
                        return a.start_timestamp.localeCompare(b.start_timestamp);
                    }
                    return a.start_timestamp ? -1 : 1;
                });

                setExams(sortedExams);
                setSourceUrl(manifestData.source_url || null);
                setSourceTitle(manifestData.source_title || null);
                setGeneratedAt(manifestData.generated_at);
                setTotalRecords(manifestData.total_records);
                setLoading(false);
            })
            .catch(err => {
                if (err instanceof DOMException && err.name === 'AbortError') {
                    return;
                }
                console.error(err);
                setError(err instanceof Error ? err.message : '无法加载数据：未知错误');
                setLoading(false);
            });

        return () => controller.abort();
    }, [enabled]);

    return {
        exams,
        loading: enabled && loading,
        error: enabled ? error : null,
        sourceUrl,
        sourceTitle,
        generatedAt,
        totalRecords
    };
}
