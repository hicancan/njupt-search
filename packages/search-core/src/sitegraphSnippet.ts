import type { SitegraphFullDocument, SitegraphMatchSnippet } from '@njupt-search/contracts';
import { normalizeSearchText as normalize } from './tokenizer';

const SNIPPET_PREFIX_LENGTH = 64;
const SNIPPET_SUFFIX_LENGTH = 96;
const FALLBACK_SNIPPET_LENGTH = 180;

type SnippetField = SitegraphMatchSnippet['field'];

interface SnippetCandidate {
    field: SnippetField;
    text: string;
}

const compactText = (value: string): string => value.replace(/\s+/g, ' ').trim();

const normalizedTerms = (query: string, terms: string[]): string[] => {
    return Array.from(new Set([query, ...terms].map(normalize).filter(term => term.length >= 2)))
        .sort((a, b) => b.length - a.length);
};

const findFirstMatch = (text: string, terms: string[]): { index: number; term: string } | null => {
    const lowerText = text.toLocaleLowerCase('zh-CN');
    let best: { index: number; term: string } | null = null;
    for (const term of terms) {
        const index = lowerText.indexOf(term.toLocaleLowerCase('zh-CN'));
        if (index < 0) continue;
        if (!best || index < best.index || (index === best.index && term.length > best.term.length)) {
            best = { index, term };
        }
    }
    return best;
};

const sliceAroundMatch = (text: string, index: number, termLength: number): string => {
    const start = Math.max(0, index - SNIPPET_PREFIX_LENGTH);
    const end = Math.min(text.length, index + termLength + SNIPPET_SUFFIX_LENGTH);
    const prefix = start > 0 ? '...' : '';
    const suffix = end < text.length ? '...' : '';
    return `${prefix}${text.slice(start, end).trim()}${suffix}`;
};

const fallbackSnippet = (candidate: SnippetCandidate): SitegraphMatchSnippet | null => {
    const text = compactText(candidate.text);
    if (!text) return null;
    return {
        field: candidate.field,
        text: text.length > FALLBACK_SNIPPET_LENGTH ? `${text.slice(0, FALLBACK_SNIPPET_LENGTH).trim()}...` : text,
        matched_terms: [],
    };
};

export const buildSitegraphMatchSnippet = (
    document: SitegraphFullDocument,
    query: string,
    terms: string[]
): SitegraphMatchSnippet | undefined => {
    const candidates: SnippetCandidate[] = [
        { field: 'content', text: document.content },
        { field: 'summary', text: document.summary },
        { field: 'title', text: document.title },
        { field: 'attachments', text: document.attachments.map(attachment => attachment.name).join(' ') },
        { field: 'nav_path', text: document.nav_path_text || document.section },
        { field: 'url', text: document.url },
    ];
    const matchTerms = normalizedTerms(query, terms);

    for (const candidate of candidates) {
        const text = compactText(candidate.text);
        if (!text) continue;
        const match = findFirstMatch(text, matchTerms);
        if (!match) continue;
        const snippet = sliceAroundMatch(text, match.index, match.term.length);
        return {
            field: candidate.field,
            text: snippet,
            matched_terms: matchTerms.filter(term => snippet.toLocaleLowerCase('zh-CN').includes(term.toLocaleLowerCase('zh-CN'))),
        };
    }

    return candidates
        .map(fallbackSnippet)
        .find((snippet): snippet is SitegraphMatchSnippet => Boolean(snippet));
};
