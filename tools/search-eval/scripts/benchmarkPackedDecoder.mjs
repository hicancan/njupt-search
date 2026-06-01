#!/usr/bin/env node
/* global Buffer, console, process */
import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import fs from 'node:fs/promises';
import { createRequire } from 'node:module';
import path from 'node:path';
import { performance } from 'node:perf_hooks';
import { fileURLToPath } from 'node:url';

import { decodePackedLocalBodyIndex } from '../../../packages/search-core/src/sitegraphBinaryIndex.ts';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, '../../..');
const defaultCollection = path.join(repoRoot, 'apps/web/public/generated/collections/njupt-public');
const wasmCrateDir = path.join(repoRoot, 'tools/wasm/packed-impact-decoder');
const wasmModulePath = path.join(wasmCrateDir, 'pkg/packed_impact_decoder.js');

const parseArgs = () => {
    const args = {
        buildWasm: false,
        collection: defaultCollection,
        markdown: null,
        output: null,
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

const writeJson = async (filePath, payload) => {
    if (!filePath) return;
    await fs.mkdir(path.dirname(filePath), { recursive: true });
    await fs.writeFile(filePath, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
};

const renderMarkdown = report => {
    const materialized = report.wasm_decode_to_json_then_parse.mean_ms / report.typescript_decode_to_object.mean_ms;
    const statsOnly = report.wasm_stats_only_decode.mean_ms / report.typescript_decode_to_object.mean_ms;
    return [
        '# NJUPT Search Rust/WASM Decoder Decision',
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
        '',
        '## Decision',
        '',
        `- Status: \`${report.decision.status}\``,
        `- Winner for current runtime: \`${report.decision.winner}\``,
        `- WASM materialized path ratio vs TypeScript: \`${materialized.toFixed(3)}x\``,
        `- WASM stats-only lower-bound ratio vs TypeScript: \`${statsOnly.toFixed(3)}x\``,
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

    const tsResult = timed(args.runs, decodeWithTypescript);
    const wasmJsonResult = timed(args.runs, decodeWithWasmJson);
    const wasmStatsResult = timed(args.runs, decodeWithWasmStats);
    if (!sameSummary(tsResult.summary, wasmJsonResult.summary) || !sameSummary(tsResult.summary, wasmStatsResult.summary)) {
        throw new Error('Decoder benchmark summaries do not match');
    }

    const tsWinsCurrentRuntime = tsResult.mean_ms <= wasmJsonResult.mean_ms;
    const ratio = wasmJsonResult.mean_ms / tsResult.mean_ms;
    const decision = tsWinsCurrentRuntime
        ? {
            reason: `The current browser runtime consumes a JavaScript SitegraphLocalBodyIndex object. On the full packed body workload, Rust/WASM decode plus JSON bridge was ${ratio.toFixed(3)}x the TypeScript decoder, so replacing only the decoder would increase current runtime decode cost. The stats-only WASM path is recorded as a lower-bound signal for a future full WASM retrieval core that avoids JS object materialization.`,
            status: 'typescript_better_for_current_runtime',
            winner: 'typescript_runtime_decoder',
        }
        : {
            reason: `Rust/WASM decode plus JSON bridge was ${(1 / ratio).toFixed(3)}x faster than the TypeScript decoder on the full packed body workload. This is evidence to integrate the WASM materialized decoder or move retrieval into WASM before claiming the Rust/WASM DoD item complete.`,
            status: 'wasm_materialized_decoder_wins_integration_needed',
            winner: 'wasm_json_bridge_decoder',
        };

    const report = {
        artifact_count: payloads.length,
        benchmark: 'packed-impact-decoder-wasm-vs-typescript-v1',
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
        typescript_decode_to_object: tsResult,
        wasm_decode_to_json_then_parse: wasmJsonResult,
        wasm_stats_only_decode: wasmStatsResult,
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
