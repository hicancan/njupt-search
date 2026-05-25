/**
 * eval_frontend_search.ts
 *
 * Runs the REAL TypeScript recallSearchDocuments / routeQuery
 * against eval/search_cases.json and outputs JSON for Python eval_search_parity.py.
 *
 * Usage:
 *   npx tsx --tsconfig tsconfig.app.json scripts/eval/eval_frontend_search.ts
 *   npx tsx --tsconfig tsconfig.app.json scripts/eval/eval_frontend_search.ts --out eval/reports/ts_search_results.json
 */

import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

// Use real TS source via @/ aliases (resolved by tsx + tsconfig)
import { recallSearchDocuments, parseSearchDocuments } from '../../src/utils/searchIndex.js';
import { routeQuery } from '../../src/utils/queryRouter.js';
import type { SearchDocument } from '../../src/types/index.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const BASE_DIR = join(__dirname, '..', '..');

function loadJson(path: string): unknown {
    const raw = readFileSync(path, 'utf-8');
    return JSON.parse(raw);
}

async function main() {
    // Parse CLI args
    const args = process.argv.slice(2);
    let outPath = join(BASE_DIR, 'eval', 'reports', 'ts_search_results.json');
    for (let i = 0; i < args.length; i++) {
        if (args[i] === '--out') {
            const next = args[i + 1];
            if (next) {
                outPath = next;
                break;
            }
        }
    }

    // Load index data
    const indexDir = join(BASE_DIR, 'public', 'index');
    const noticeDocs = parseSearchDocuments(
        loadJson(join(indexDir, 'documents.json')),
        'documents.json'
    );
    const queryAliases = loadJson(join(BASE_DIR, 'config', 'query_aliases.json')) as Record<string, unknown>;
    const allDocuments: SearchDocument[] = noticeDocs;
    console.log(`[eval_frontend_search] Loaded ${noticeDocs.length} notice docs`);

    // Load search cases
    const casesPath = join(BASE_DIR, 'eval', 'search_cases.json');
    const cases = loadJson(casesPath) as Array<{ query: string; route?: string }>;

    const results: Array<{
        query: string;
        route_type: string;
        top1_prefer_exact_title: boolean;
        top5_ids: string[];
        top5_titles: string[];
        top5_sources: string[];
        top5_domains: string[];
        top5_channel_ids: string[];
        expected_route: string;
        route_match: boolean;
    }> = [];

    for (const tc of cases) {
        const query = tc.query;
        const expectedRoute = tc.route || 'general_search';

        // Route
        const routeObj = routeQuery(query);
        const routeMatch = routeObj.query_type === expectedRoute;

        // Recall candidates; display order is strictly newest published_at first.
        const recalled = recallSearchDocuments(allDocuments, query, queryAliases);
        const top5 = recalled.slice(0, 5);

        results.push({
            query,
            route_type: routeObj.query_type,
            top1_prefer_exact_title: routeObj.top1_prefer_exact_title,
            top5_ids: top5.map(d => d.id),
            top5_titles: top5.map(d => d.title),
            top5_sources: top5.map(d => d.source_id || d.source),
            top5_domains: top5.map(d => d.domain),
            top5_channel_ids: top5.map(d => d.channel_id),
            expected_route: expectedRoute,
            route_match: routeMatch,
        });
    }

    // Write output
    const outDir = dirname(outPath);
    mkdirSync(outDir, { recursive: true });
    writeFileSync(outPath, JSON.stringify(results, null, 2), 'utf-8');

    // Summary
    const routeMatches = results.filter(r => r.route_match).length;
    console.log(`\n[eval_frontend_search] Done. ${results.length} queries processed.`);
    console.log(`  Route matches: ${routeMatches}/${results.length}`);
    console.log(`  Output: ${outPath}`);
}

main().catch(err => {
    console.error('[eval_frontend_search] ERROR:', err);
    process.exit(1);
});
