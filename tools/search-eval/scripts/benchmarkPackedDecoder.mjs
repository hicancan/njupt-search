#!/usr/bin/env node
/* global Buffer, console, process */
import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import fs from 'node:fs/promises';
import { createRequire } from 'node:module';
import path from 'node:path';
import { performance } from 'node:perf_hooks';
import { fileURLToPath } from 'node:url';

import {
    decodePackedLocalBodyIndex,
    decodePackedLocalBodyIndexTerms,
} from '../../../packages/search-core/src/sitegraphBinaryIndex.ts';
import { tokenizeSitegraphQuery } from '../../../packages/search-core/src/tokenizer.ts';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, '../../..');
const defaultCollection = path.join(repoRoot, 'apps/web/public/generated/collections/njupt-public');
const wasmCrateDir = path.join(repoRoot, 'tools/wasm/packed-impact-decoder');
const wasmModulePath = path.join(wasmCrateDir, 'pkg/packed_impact_decoder.js');
const defaultRetrievalQueries = ['校历', '慕课考试', '转专业', '学生相关文件及表格', '教务管理系统', '奖学金', '大创', '不存在的查询词'];

const parseArgs = () => {
    const args = {
        buildWasm: false,
        collection: defaultCollection,
        markdown: null,
        output: null,
        queries: [],
        runs: 5,
    };
    for (let index = 2; index < process.argv.length; index += 1) {
        const arg = process.argv[index];
        if (arg === '--build-wasm') {
            args.buildWasm = true;
        } else if (arg === '--collection') {
            args.collection = path.resolve(process.argv[++index]);
        } else if (arg === '--output') {
            args.output = path.resolve(process.argv[++index]);
        } else if (arg === '--markdown') {
            args.markdown = path.resolve(process.argv[++index]);
        } else if (arg === '--runs') {
            args.runs = Math.max(1, Number.parseInt(process.argv[++index], 10));
        } else if (arg === '--query') {
            args.queries.push(process.argv[++index]);
        } else {
            throw new Error(`Unknown argument: ${arg}`);
        }
    }
    return args;
};

const commandVersion = (command, args = ['--version']) => {
    try {
        return execFileSync(command, args, { cwd: repoRoot, encoding: 'utf8' }).trim();
    } catch (error) {
        return `unavailable: ${error instanceof Error ? error.message : String(error)}`;
    }
};

const listPackedArtifacts = async collection => {
    const directory = path.join(collection, 'sitegraph/local_impact_body_packed_indexes');
    const entries = await fs.readdir(directory);
    return entries
        .filter(entry => entry.endsWith('.bin'))
        .sort()
        .map(entry => path.join(directory, entry));
};

const toArrayBuffer = bytes => {
    const copy = new Uint8Array(bytes.byteLength);
    copy.set(bytes);
    return copy.buffer;
};

const summarizeDecodedIndex = decoded => {
    const summary = {
        field_count: 0,
        max_doc_id: 0,
        posting_count: 0,
        term_count: 0,
    };
    for (const fields of Object.values(decoded.terms)) {
        summary.term_count += 1;
        for (const docIds of Object.values(fields)) {
            summary.field_count += 1;
            summary.posting_count += docIds.length;
            for (const docId of docIds) {
                if (docId > summary.max_doc_id) summary.max_doc_id = docId;
            }
        }
    }
    return summary;
};

const addSummary = (left, right) => ({
    field_count: left.field_count + right.field_count,
    max_doc_id: Math.max(left.max_doc_id, right.max_doc_id),
    posting_count: left.posting_count + right.posting_count,
    term_count: left.term_count + right.term_count,
});

const emptySummary = () => ({
    field_count: 0,
    max_doc_id: 0,
    posting_count: 0,
    term_count: 0,
});

const emptyRetrievalSummary = () => ({
    block_count: 0,
    candidate_count: 0,
    impact_blocks_pruned: 0,
    impact_blocks_visited: 0,
    matched_term_count: 0,
    postings_pruned: 0,
    postings_visited: 0,
});

const addRetrievalSummary = (left, right) => ({
    block_count: left.block_count + Number(right.block_count || 0),
    candidate_count: left.candidate_count + Number(right.candidate_count || 0),
    impact_blocks_pruned: left.impact_blocks_pruned + Number(right.impact_blocks_pruned || 0),
    impact_blocks_visited: left.impact_blocks_visited + Number(right.impact_blocks_visited || 0),
    matched_term_count: left.matched_term_count + Number(right.matched_term_count || 0),
    postings_pruned: left.postings_pruned + Number(right.postings_pruned || 0),
    postings_visited: left.postings_visited + Number(right.postings_visited || 0),
});

const sameRetrievalSummary = (left, right) =>
    left.block_count === right.block_count
    && left.candidate_count === right.candidate_count
    && left.impact_blocks_pruned === right.impact_blocks_pruned
    && left.impact_blocks_visited === right.impact_blocks_visited
    && left.matched_term_count === right.matched_term_count
    && left.postings_pruned === right.postings_pruned
    && left.postings_visited === right.postings_visited;

const sameSummary = (left, right) =>
    left.term_count === right.term_count
    && left.field_count === right.field_count
    && left.posting_count === right.posting_count
    && left.max_doc_id === right.max_doc_id;

const summarizeDurations = durations => ({
    max_ms: Number(Math.max(...durations).toFixed(3)),
    mean_ms: Number((durations.reduce((total, value) => total + value, 0) / durations.length).toFixed(3)),
    min_ms: Number(Math.min(...durations).toFixed(3)),
});

const timed = (runs, fn) => {
    const durations = [];
    let summary = emptySummary();
    for (let run = 0; run < runs; run += 1) {
        const started = performance.now();
        summary = fn();
        durations.push(performance.now() - started);
    }
    return {
        ...summarizeDurations(durations),
        runs,
        summary,
    };
};

const timedRetrieval = (runs, fn) => {
    const durations = [];
    let summary = emptyRetrievalSummary();
    for (let run = 0; run < runs; run += 1) {
        const started = performance.now();
        summary = fn();
        durations.push(performance.now() - started);
    }
    return {
        ...summarizeDurations(durations),
        runs,
        summary,
    };
};

const sortedScoreEntries = scores => Array.from(scores.entries()).sort((left, right) => {
    const scoreDelta = right[1] - left[1];
    if (scoreDelta !== 0) return scoreDelta;
    return left[0] - right[0];
});

const competitiveThreshold = (scores, target) => {
    if (scores.size < target) return Number.NEGATIVE_INFINITY;
    return sortedScoreEntries(scores)[Math.max(0, target - 1)]?.[1] ?? Number.NEGATIVE_INFINITY;
};

const scoreImpactIndexInto = (scores, index, terms, targetCandidates = 160) => {
    const blocks = [];
    const blockSize = Math.max(8, index.block_size || 32);
    for (const term of terms) {
        const termPayload = index.terms[term];
        if (!termPayload) continue;
        for (const [field, ids] of Object.entries(termPayload)) {
            const impact = (index.field_impacts[field] || 8) + Math.min(term.length, 8);
            for (let offset = 0; offset < ids.length; offset += blockSize) {
                blocks.push({
                    key: `${term}\0${field}`,
                    impact,
                    ids: ids.slice(offset, offset + blockSize),
                });
            }
        }
    }
    blocks.sort((left, right) => right.impact - left.impact || left.key.localeCompare(right.key));
    const suffix = new Array(blocks.length + 1).fill(0);
    const seen = new Set();
    let total = 0;
    for (let index = blocks.length - 1; index >= 0; index -= 1) {
        if (!seen.has(blocks[index].key)) {
            seen.add(blocks[index].key);
            total += blocks[index].impact;
        }
        suffix[index] = total;
    }
    const summary = {
        ...emptyRetrievalSummary(),
        block_count: blocks.length,
        matched_term_count: Object.keys(index.terms).length,
    };
    for (let index = 0; index < blocks.length; index += 1) {
        const block = blocks[index];
        const threshold = competitiveThreshold(scores, targetCandidates);
        const maxPossibleForUnseenDoc = block.impact + (suffix[index + 1] ?? 0);
        const hasKnownCandidate = block.ids.some(docIndex => scores.has(docIndex));
        if (!hasKnownCandidate && scores.size >= targetCandidates && maxPossibleForUnseenDoc <= threshold) {
            summary.impact_blocks_pruned += 1;
            summary.postings_pruned += block.ids.length;
            continue;
        }
        summary.impact_blocks_visited += 1;
        for (const docIndex of block.ids) {
            summary.postings_visited += 1;
            scores.set(docIndex, (scores.get(docIndex) || 0) + block.impact);
        }
    }
    return summary;
};

const loadAliases = async collection => {
    const manifest = JSON.parse(await fs.readFile(path.join(collection, 'manifest.json'), 'utf8'));
    const aliasesPath = path.join(repoRoot, 'apps/web/public', manifest.artifacts.query_aliases.path);
    return JSON.parse(await fs.readFile(aliasesPath, 'utf8'));
};

const writeJson = async (filePath, payload) => {
    if (!filePath) return;
    await fs.mkdir(path.dirname(filePath), { recursive: true });
    await fs.writeFile(filePath, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
};

const renderMarkdown = report => {
    const materialized = report.wasm_decode_to_json_then_parse.mean_ms / report.typescript_decode_to_object.mean_ms;
    const statsOnly = report.wasm_stats_only_decode.mean_ms / report.typescript_decode_to_object.mean_ms;
    const retrievalRatio = report.wasm_retrieval_session.mean_ms / report.typescript_retrieval_kernel.mean_ms;
    return [
        '# NJUPT Search Rust/WASM Retrieval Decision',
        '',
        `- Generated at: \`${report.generated_at}\``,
        `- Artifact count: \`${report.artifact_count}\``,
        `- Packed body bytes: \`${report.total_bytes.toLocaleString('en-US')}\``,
        `- Runs: \`${report.runs}\``,
        '',
        '## Results',
        '',
        '| Path | Mean ms | Min ms | Max ms |',
        '| --- | ---: | ---: | ---: |',
        `| TypeScript runtime decoder to JS object | ${report.typescript_decode_to_object.mean_ms.toFixed(3)} | ${report.typescript_decode_to_object.min_ms.toFixed(3)} | ${report.typescript_decode_to_object.max_ms.toFixed(3)} |`,
        `| Rust/WASM decode to JSON string, then JS parse | ${report.wasm_decode_to_json_then_parse.mean_ms.toFixed(3)} | ${report.wasm_decode_to_json_then_parse.min_ms.toFixed(3)} | ${report.wasm_decode_to_json_then_parse.max_ms.toFixed(3)} |`,
        `| Rust/WASM stats-only decode lower bound | ${report.wasm_stats_only_decode.mean_ms.toFixed(3)} | ${report.wasm_stats_only_decode.min_ms.toFixed(3)} | ${report.wasm_stats_only_decode.max_ms.toFixed(3)} |`,
        `| TypeScript selective retrieval kernel | ${report.typescript_retrieval_kernel.mean_ms.toFixed(3)} | ${report.typescript_retrieval_kernel.min_ms.toFixed(3)} | ${report.typescript_retrieval_kernel.max_ms.toFixed(3)} |`,
        `| Rust/WASM stateless retrieval kernel | ${report.wasm_retrieval_kernel.mean_ms.toFixed(3)} | ${report.wasm_retrieval_kernel.min_ms.toFixed(3)} | ${report.wasm_retrieval_kernel.max_ms.toFixed(3)} |`,
        `| Rust/WASM stateful retrieval session | ${report.wasm_retrieval_session.mean_ms.toFixed(3)} | ${report.wasm_retrieval_session.min_ms.toFixed(3)} | ${report.wasm_retrieval_session.max_ms.toFixed(3)} |`,
        `| Rust/WASM stateful retrieval with score bridge | ${report.wasm_retrieval_session_scores_bridge.mean_ms.toFixed(3)} | ${report.wasm_retrieval_session_scores_bridge.min_ms.toFixed(3)} | ${report.wasm_retrieval_session_scores_bridge.max_ms.toFixed(3)} |`,
        '',
        '## Decision',
        '',
        `- Status: \`${report.decision.status}\``,
        `- Winner for current runtime: \`${report.decision.winner}\``,
        `- WASM materialized path ratio vs TypeScript: \`${materialized.toFixed(3)}x\``,
        `- WASM stats-only lower-bound ratio vs TypeScript: \`${statsOnly.toFixed(3)}x\``,
        `- WASM stateful retrieval ratio vs TypeScript retrieval kernel: \`${retrievalRatio.toFixed(3)}x\``,
        `- WASM stateful score bridge ratio vs TypeScript retrieval kernel: \`${(report.wasm_retrieval_session_scores_bridge.mean_ms / report.typescript_retrieval_kernel.mean_ms).toFixed(3)}x\``,
        `- Reason: ${report.decision.reason}`,
        '',
        '## Reproduction',
        '',
        '```powershell',
        'node --import tsx tools\\search-eval\\scripts\\benchmarkPackedDecoder.mjs --build-wasm --collection apps\\web\\public\\generated\\collections\\njupt-public --runs 5 --output docs\\reports\\njupt-search-wasm-decision.json --markdown docs\\reports\\njupt-search-wasm-decision.md',
        '```',
        '',
    ].join('\n');
};

const main = async () => {
    const args = parseArgs();
    if (args.buildWasm) {
        execFileSync('wasm-pack', ['build', '--target', 'nodejs', '--release', '--out-dir', 'pkg'], {
            cwd: wasmCrateDir,
            stdio: 'inherit',
        });
    }
    if (!existsSync(wasmModulePath)) {
        throw new Error(`Missing WASM package. Run: wasm-pack build --target nodejs --release --out-dir pkg in ${wasmCrateDir}`);
    }

    const require = createRequire(import.meta.url);
    const wasm = require(wasmModulePath);
    const artifactPaths = await listPackedArtifacts(args.collection);
    const aliases = await loadAliases(args.collection);
    const retrievalQueries = args.queries.length > 0 ? args.queries : defaultRetrievalQueries;
    const retrievalTermsByQuery = retrievalQueries.map(query => ({
        query,
        terms: tokenizeSitegraphQuery(query, aliases),
    }));
    const payloads = await Promise.all(
        artifactPaths.map(async artifactPath => {
            const bytes = await fs.readFile(artifactPath);
            return {
                arrayBuffer: toArrayBuffer(bytes),
                bytes,
                path: artifactPath,
                uint8: new Uint8Array(bytes.buffer, bytes.byteOffset, bytes.byteLength),
            };
        }),
    );

    if (payloads.length === 0) {
        throw new Error(`No packed body index artifacts found under ${args.collection}`);
    }

    const firstTs = decodePackedLocalBodyIndex(payloads[0].arrayBuffer, payloads[0].path);
    const firstWasm = JSON.parse(wasm.decode_packed_impact_to_json(payloads[0].uint8));
    if (JSON.stringify(firstTs) !== JSON.stringify(firstWasm)) {
        throw new Error('WASM materialized decoder does not match TypeScript decoder on the first packed artifact');
    }

    const decodeWithTypescript = () => {
        let aggregate = emptySummary();
        for (const payload of payloads) {
            aggregate = addSummary(aggregate, summarizeDecodedIndex(decodePackedLocalBodyIndex(payload.arrayBuffer, payload.path)));
        }
        return aggregate;
    };
    const decodeWithWasmJson = () => {
        let aggregate = emptySummary();
        for (const payload of payloads) {
            aggregate = addSummary(aggregate, summarizeDecodedIndex(JSON.parse(wasm.decode_packed_impact_to_json(payload.uint8))));
        }
        return aggregate;
    };
    const decodeWithWasmStats = () => {
        let aggregate = emptySummary();
        for (const payload of payloads) {
            aggregate = addSummary(aggregate, JSON.parse(wasm.decode_packed_impact_stats(payload.uint8)));
        }
        return aggregate;
    };
    const retrieveWithTypescript = () => {
        let aggregate = emptyRetrievalSummary();
        for (const { terms } of retrievalTermsByQuery) {
            const scores = new Map();
            let querySummary = emptyRetrievalSummary();
            for (const payload of payloads) {
                const decoded = decodePackedLocalBodyIndexTerms(payload.arrayBuffer, terms, payload.path);
                querySummary = addRetrievalSummary(querySummary, scoreImpactIndexInto(scores, decoded, terms));
            }
            querySummary.candidate_count = scores.size;
            aggregate = addRetrievalSummary(aggregate, querySummary);
        }
        return aggregate;
    };
    const retrieveWithWasm = () => {
        let aggregate = emptyRetrievalSummary();
        for (const { terms } of retrievalTermsByQuery) {
            const serializedTerms = JSON.stringify(terms);
            for (const payload of payloads) {
                aggregate = addRetrievalSummary(
                    aggregate,
                    JSON.parse(wasm.retrieve_packed_impact_topk_stats(payload.uint8, serializedTerms, 160)),
                );
            }
        }
        return aggregate;
    };
    const retrieveWithWasmSession = () => {
        let aggregate = emptyRetrievalSummary();
        for (const { terms } of retrievalTermsByQuery) {
            const session = new wasm.PackedImpactRetrievalSession(160);
            const serializedTerms = JSON.stringify(terms);
            let querySummary = emptyRetrievalSummary();
            for (const payload of payloads) {
                const result = JSON.parse(session.apply(payload.uint8, serializedTerms));
                querySummary = addRetrievalSummary(querySummary, { ...result, candidate_count: 0 });
            }
            const finalStats = JSON.parse(session.stats_json());
            querySummary.candidate_count = Number(finalStats.candidate_count || 0);
            aggregate = addRetrievalSummary(aggregate, querySummary);
            session.free();
        }
        return aggregate;
    };
    const retrieveWithWasmSessionScoresBridge = () => {
        let aggregate = emptyRetrievalSummary();
        for (const { terms } of retrievalTermsByQuery) {
            const session = new wasm.PackedImpactRetrievalSession(160);
            const serializedTerms = JSON.stringify(terms);
            let querySummary = emptyRetrievalSummary();
            for (const payload of payloads) {
                const result = JSON.parse(session.apply(payload.uint8, serializedTerms));
                querySummary = addRetrievalSummary(querySummary, { ...result, candidate_count: 0 });
            }
            const scoresPayload = JSON.parse(session.scores_json());
            if (!Array.isArray(scoresPayload.score_entries)) {
                throw new Error('WASM score bridge result is missing score_entries');
            }
            if (scoresPayload.score_entries.length !== Number(scoresPayload.candidate_count || 0)) {
                throw new Error('WASM score bridge candidate_count does not match score_entries length');
            }
            querySummary.candidate_count = Number(scoresPayload.candidate_count || 0);
            aggregate = addRetrievalSummary(aggregate, querySummary);
            session.free();
        }
        return aggregate;
    };

    const tsResult = timed(args.runs, decodeWithTypescript);
    const wasmJsonResult = timed(args.runs, decodeWithWasmJson);
    const wasmStatsResult = timed(args.runs, decodeWithWasmStats);
    const tsRetrievalResult = timedRetrieval(args.runs, retrieveWithTypescript);
    const wasmRetrievalResult = timedRetrieval(args.runs, retrieveWithWasm);
    const wasmRetrievalSessionResult = timedRetrieval(args.runs, retrieveWithWasmSession);
    const wasmRetrievalSessionScoresBridgeResult = timedRetrieval(args.runs, retrieveWithWasmSessionScoresBridge);
    if (!sameSummary(tsResult.summary, wasmJsonResult.summary) || !sameSummary(tsResult.summary, wasmStatsResult.summary)) {
        throw new Error('Decoder benchmark summaries do not match');
    }
    if (!sameRetrievalSummary(tsRetrievalResult.summary, wasmRetrievalSessionResult.summary)) {
        throw new Error(`Stateful retrieval benchmark summaries do not match: ${JSON.stringify({ ts: tsRetrievalResult.summary, wasm: wasmRetrievalSessionResult.summary })}`);
    }
    if (!sameRetrievalSummary(wasmRetrievalSessionResult.summary, wasmRetrievalSessionScoresBridgeResult.summary)) {
        throw new Error(`WASM session score bridge retrieval summaries do not match: ${JSON.stringify({ stats: wasmRetrievalSessionResult.summary, scores: wasmRetrievalSessionScoresBridgeResult.summary })}`);
    }

    const tsWinsCurrentRuntime = tsResult.mean_ms <= wasmJsonResult.mean_ms;
    const retrievalRatio = wasmRetrievalSessionResult.mean_ms / tsRetrievalResult.mean_ms;
    const scoreBridgeRatio = wasmRetrievalSessionScoresBridgeResult.mean_ms / tsRetrievalResult.mean_ms;
    const ratio = wasmJsonResult.mean_ms / tsResult.mean_ms;
    const tsRetrievalWins = tsRetrievalResult.mean_ms <= wasmRetrievalSessionScoresBridgeResult.mean_ms;
    const wasmScoreBridgeWins = wasmRetrievalSessionScoresBridgeResult.mean_ms < tsRetrievalResult.mean_ms;
    const decision = wasmScoreBridgeWins
        ? {
            reason: `The browser runtime can consume Rust/WASM stateful score entries directly. On the full packed body workload, the Rust/WASM session score bridge was ${scoreBridgeRatio.toFixed(3)}x the TypeScript selective retrieval kernel for the same artifact format, query set, and global top-k pruning state.`,
            status: 'rust_wasm_retrieval_runtime_selected',
            winner: 'wasm_retrieval_session_scores_bridge',
        }
        : tsWinsCurrentRuntime && tsRetrievalWins
        ? {
            reason: `The current browser runtime consumes JavaScript search objects. On the full packed body workload, Rust/WASM decode plus JSON bridge was ${ratio.toFixed(3)}x the TypeScript decoder, and the Rust/WASM selective retrieval kernel was ${retrievalRatio.toFixed(3)}x the TypeScript selective retrieval kernel for the same query set. TypeScript remains the selected runtime until a full browser WASM integration beats it end to end.`,
            status: 'typescript_runtime_selected_after_wasm_retrieval_kernel',
            winner: 'typescript_runtime_decoder',
        }
        : {
            reason: `Rust/WASM produced a faster path in at least one measured mode: materialized decode ratio ${ratio.toFixed(3)}x, retrieval kernel ratio ${retrievalRatio.toFixed(3)}x. Integrate the winning WASM retrieval path in the browser before treating the TypeScript runtime as final.`,
            status: 'wasm_retrieval_integration_needed',
            winner: tsRetrievalWins ? 'wasm_json_bridge_decoder' : 'wasm_retrieval_kernel',
        };

    const report = {
        artifact_count: payloads.length,
        benchmark: 'packed-impact-retrieval-wasm-vs-typescript-v2',
        collection: path.relative(repoRoot, args.collection).replaceAll(path.sep, '/'),
        decision,
        generated_at: new Date().toISOString(),
        runs: args.runs,
        toolchain: {
            node: commandVersion('node'),
            rustc: commandVersion('rustc'),
            wasm_opt: commandVersion('wasm-opt', ['--version']),
            wasm_pack: commandVersion('wasm-pack'),
            wasm_tools: commandVersion('wasm-tools', ['--version']),
        },
        total_bytes: payloads.reduce((total, payload) => total + payload.bytes.byteLength, 0),
        retrieval_queries: retrievalTermsByQuery.map(item => ({ query: item.query, term_count: item.terms.length })),
        typescript_decode_to_object: tsResult,
        wasm_decode_to_json_then_parse: wasmJsonResult,
        wasm_stats_only_decode: wasmStatsResult,
        typescript_retrieval_kernel: tsRetrievalResult,
        wasm_retrieval_kernel: wasmRetrievalResult,
        wasm_retrieval_session: wasmRetrievalSessionResult,
        wasm_retrieval_session_scores_bridge: wasmRetrievalSessionScoresBridgeResult,
    };

    await writeJson(args.output, report);
    if (args.markdown) {
        await fs.mkdir(path.dirname(args.markdown), { recursive: true });
        await fs.writeFile(args.markdown, renderMarkdown(report), 'utf8');
    }
    console.log(JSON.stringify(report, null, 2));
};

main().catch(error => {
    console.error(error instanceof Error ? error.stack || error.message : error);
    process.exitCode = 1;
});
