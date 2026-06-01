import type { SitegraphFullDocument, SitegraphMatchHighlight, SitegraphMatchSnippet } from '@njupt-search/contracts';
import { normalizeSearchText as normalize } from './tokenizer';

const VISIBLE_MATCH_PREFIX_LENGTH = 24;
const SNIPPET_SUFFIX_LENGTH = 112;
const FALLBACK_SNIPPET_LENGTH = 180;

type SnippetField = SitegraphMatchSnippet['field'];

interface SnippetCandidate {
    field: SnippetField;
    text: string;
    evidenceLevel: SitegraphMatchSnippet['evidence_level'];
}

interface SearchableText {
    normalized: string;
    sourceStartByNormalizedIndex: number[];
    sourceEndByNormalizedIndex: number[];
}

interface TextMatch {
    start: number;
    end: number;
    term: string;
}

interface ScoredMatch {
    candidate: SnippetCandidate;
    text: string;
    match: TextMatch;
    score: number;
}

const FIELD_WEIGHTS: Record<SnippetField, number> = {
    content: 90,
    summary: 82,
    attachments: 76,
    title: 70,
    nav_path: 58,
    url: 30,
};

const compactText = (value: string): string => value.replace(/\s+/g, ' ').trim();

const normalizedTerms = (query: string, terms: string[]): string[] => {
    return Array.from(new Set([query, ...terms]
        .map(normalize)
        .filter(term => term.length >= 2)))
        .sort((a, b) => b.length - a.length);
};

const buildSearchableText = (text: string): SearchableText => {
    let normalized = '';
    const sourceStartByNormalizedIndex: number[] = [];
    const sourceEndByNormalizedIndex: number[] = [];

    for (let sourceIndex = 0; sourceIndex < text.length;) {
        const codePoint = text.codePointAt(sourceIndex);
        const char = String.fromCodePoint(codePoint || 0);
        const sourceEnd = sourceIndex + char.length;
        const normalizedChar = char.normalize('NFKC').toLocaleLowerCase('zh-CN');
        if (!/\s/.test(normalizedChar)) {
            for (let index = 0; index < normalizedChar.length; index += 1) {
                sourceStartByNormalizedIndex.push(sourceIndex);
                sourceEndByNormalizedIndex.push(sourceEnd);
            }
            normalized += normalizedChar;
        }
        sourceIndex = sourceEnd;
    }

    return { normalized, sourceStartByNormalizedIndex, sourceEndByNormalizedIndex };
};

const collectMatches = (text: string, terms: string[]): TextMatch[] => {
    const searchable = buildSearchableText(text);
    const matches: TextMatch[] = [];
    for (const term of terms) {
        let normalizedIndex = searchable.normalized.indexOf(term);
        while (normalizedIndex >= 0) {
            const normalizedEnd = normalizedIndex + term.length - 1;
            const start = searchable.sourceStartByNormalizedIndex[normalizedIndex];
            const end = searchable.sourceEndByNormalizedIndex[normalizedEnd];
            if (start !== undefined && end !== undefined) {
                matches.push({ start, end, term });
            }
            normalizedIndex = searchable.normalized.indexOf(term, normalizedIndex + 1);
        }
    }
    return matches;
};

const chooseNonOverlappingHighlights = (matches: TextMatch[]): SitegraphMatchHighlight[] => {
    const selected: SitegraphMatchHighlight[] = [];
    const sorted = [...matches].sort((a, b) => {
        if (a.start !== b.start) return a.start - b.start;
        return (b.end - b.start) - (a.end - a.start);
    });

    for (const match of sorted) {
        const overlaps = selected.some(item => match.start < item.end && match.end > item.start);
        if (overlaps) continue;
        selected.push({ start: match.start, end: match.end, term: match.term });
    }
    return selected.sort((a, b) => a.start - b.start);
};

const buildHighlights = (text: string, terms: string[]): SitegraphMatchHighlight[] => {
    return chooseNonOverlappingHighlights(collectMatches(text, terms));
};

const scoreMatch = (field: SnippetField, match: TextMatch, normalizedQuery: string): number => {
    const queryBoost = match.term === normalizedQuery ? 1000 : 0;
    const termLengthBoost = match.term.length * 12;
    const earlyMatchBoost = Math.max(0, 40 - Math.floor(match.start / 8));
    return FIELD_WEIGHTS[field] + queryBoost + termLengthBoost + earlyMatchBoost;
};

const bestCandidateMatch = (candidates: SnippetCandidate[], terms: string[], normalizedQuery: string): ScoredMatch | null => {
    let best: ScoredMatch | null = null;
    for (const candidate of candidates) {
        const text = compactText(candidate.text);
        if (!text) continue;
        const matches = collectMatches(text, terms);
        for (const match of matches) {
            const scored: ScoredMatch = {
                candidate,
                text,
                match,
                score: scoreMatch(candidate.field, match, normalizedQuery),
            };
            if (!best
                || scored.score > best.score
                || (scored.score === best.score && scored.match.start < best.match.start)) {
                best = scored;
            }
        }
    }
    return best;
};

const sliceAroundMatch = (text: string, match: TextMatch): string => {
    const start = Math.max(0, match.start - VISIBLE_MATCH_PREFIX_LENGTH);
    const end = Math.min(text.length, match.end + SNIPPET_SUFFIX_LENGTH);
    const prefix = start > 0 ? '...' : '';
    const suffix = end < text.length ? '...' : '';
    return `${prefix}${text.slice(start, end).trim()}${suffix}`;
};

const fallbackSnippet = (candidate: SnippetCandidate): SitegraphMatchSnippet | null => {
    const text = compactText(candidate.text);
    if (!text) return null;
        return {
            field: candidate.field,
            evidence_level: candidate.evidenceLevel,
            text: text.length > FALLBACK_SNIPPET_LENGTH ? `${text.slice(0, FALLBACK_SNIPPET_LENGTH).trim()}...` : text,
            matched_terms: [],
        highlights: [],
        fallback: true,
    };
};

export const buildSitegraphMatchSnippet = (
    document: SitegraphFullDocument,
    query: string,
    terms: string[]
): SitegraphMatchSnippet | undefined => {
    const candidates: SnippetCandidate[] = [
        { field: 'content', text: document.content, evidenceLevel: 'full_content' },
        { field: 'summary', text: document.summary, evidenceLevel: 'snippet' },
        {
            field: 'attachments',
            text: document.attachments.map(attachment => attachment.name).join(' '),
            evidenceLevel: 'filename_only'
        },
        { field: 'title', text: document.title, evidenceLevel: 'source_metadata' },
        { field: 'nav_path', text: document.nav_path_text || document.section, evidenceLevel: 'source_metadata' },
        { field: 'url', text: document.url, evidenceLevel: 'source_metadata' },
    ];
    const matchTerms = normalizedTerms(query, terms);
    const normalizedQuery = normalize(query);
    const best = bestCandidateMatch(candidates, matchTerms, normalizedQuery);

    if (best) {
        const snippet = sliceAroundMatch(best.text, best.match);
        const highlights = buildHighlights(snippet, matchTerms);
        const matchedTerms = Array.from(new Set(highlights.map(highlight => highlight.term)))
            .sort((a, b) => b.length - a.length);
        return {
            field: best.candidate.field,
            evidence_level: best.candidate.evidenceLevel,
            text: snippet,
            matched_terms: matchedTerms,
            highlights,
            primary_term: best.match.term,
        };
    }

    return candidates
        .map(fallbackSnippet)
        .find((snippet): snippet is SitegraphMatchSnippet => Boolean(snippet));
};
