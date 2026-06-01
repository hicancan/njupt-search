use std::collections::{HashMap, HashSet};
use std::str;
use wasm_bindgen::prelude::*;

const MAGIC_V1: &[u8] = b"SGIXB001";
const MAGIC_V2: &[u8] = b"SGIXB002";

enum PackedFormat {
    V1,
    V2,
}

struct Cursor<'a> {
    data: &'a [u8],
    offset: usize,
}

impl<'a> Cursor<'a> {
    fn new(data: &'a [u8]) -> Self {
        Self { data, offset: 0 }
    }

    fn read_byte(&mut self) -> Result<u8, JsValue> {
        let byte = self
            .data
            .get(self.offset)
            .copied()
            .ok_or_else(|| JsValue::from_str("truncated byte"))?;
        self.offset += 1;
        Ok(byte)
    }

    fn read_bytes(&mut self, length: usize) -> Result<&'a [u8], JsValue> {
        let end = self
            .offset
            .checked_add(length)
            .ok_or_else(|| JsValue::from_str("length overflow"))?;
        if end > self.data.len() {
            return Err(JsValue::from_str("truncated bytes"));
        }
        let bytes = &self.data[self.offset..end];
        self.offset = end;
        Ok(bytes)
    }

    fn read_u32_le(&mut self) -> Result<u32, JsValue> {
        let b0 = self.read_byte()? as u32;
        let b1 = self.read_byte()? as u32;
        let b2 = self.read_byte()? as u32;
        let b3 = self.read_byte()? as u32;
        Ok(b0 | (b1 << 8) | (b2 << 16) | (b3 << 24))
    }

    fn read_varint(&mut self) -> Result<u64, JsValue> {
        let mut shift = 0_u32;
        let mut value = 0_u64;
        loop {
            let byte = self.read_byte()?;
            value = value
                .checked_add(((byte & 0x7f) as u64) << shift)
                .ok_or_else(|| JsValue::from_str("varint overflow"))?;
            if byte & 0x80 == 0 {
                return Ok(value);
            }
            shift += 7;
            if shift > 63 {
                return Err(JsValue::from_str("varint exceeds u64"));
            }
        }
    }

    fn read_magic(&mut self) -> Result<PackedFormat, JsValue> {
        let magic = self.read_bytes(MAGIC_V1.len())?;
        if magic == MAGIC_V2 {
            Ok(PackedFormat::V2)
        } else if magic == MAGIC_V1 {
            Ok(PackedFormat::V1)
        } else {
            Err(JsValue::from_str("invalid packed impact index header"))
        }
    }

    fn is_done(&self) -> bool {
        self.offset == self.data.len()
    }
}

struct Stats {
    field_count: u64,
    posting_count: u64,
    max_doc_id: u64,
}

struct ImpactBlock {
    key: String,
    impact: f64,
    ids: Vec<u64>,
}

struct RetrievalResult {
    matched_term_count: u64,
    block_count: usize,
    scores: HashMap<u64, f64>,
    impact_blocks_visited: u64,
    impact_blocks_pruned: u64,
    postings_visited: u64,
    postings_pruned: u64,
    competitive_threshold: f64,
}

struct ApplyStats {
    impact_blocks_visited: u64,
    impact_blocks_pruned: u64,
    postings_visited: u64,
    postings_pruned: u64,
    competitive_threshold: f64,
}

fn json_string(value: &str) -> Result<String, JsValue> {
    serde_json::to_string(value).map_err(|error| JsValue::from_str(&error.to_string()))
}

fn metadata_prefix(metadata: &str) -> Result<String, JsValue> {
    let trimmed = metadata.trim();
    if !trimmed.starts_with('{') || !trimmed.ends_with('}') {
        return Err(JsValue::from_str("metadata is not a JSON object"));
    }
    Ok(trimmed[..trimmed.len() - 1].to_string())
}

fn append_fields_json(cursor: &mut Cursor<'_>, output: &mut String) -> Result<Stats, JsValue> {
    let field_count = cursor.read_varint()?;
    let mut stats = Stats {
        field_count,
        posting_count: 0,
        max_doc_id: 0,
    };
    for field_index in 0..field_count {
        if field_index > 0 {
            output.push(',');
        }
        let field = (cursor.read_byte()? as char).to_string();
        output.push_str(&json_string(&field)?);
        output.push_str(":[");

        let doc_count = cursor.read_varint()?;
        stats.posting_count += doc_count;
        let mut previous = 0_u64;
        for doc_offset in 0..doc_count {
            if doc_offset > 0 {
                output.push(',');
            }
            let delta = cursor.read_varint()?;
            let doc_id = if doc_offset == 0 {
                delta
            } else {
                previous
                    .checked_add(delta)
                    .ok_or_else(|| JsValue::from_str("doc id overflow"))?
            };
            output.push_str(&doc_id.to_string());
            stats.max_doc_id = stats.max_doc_id.max(doc_id);
            previous = doc_id;
        }
        output.push(']');
    }
    Ok(stats)
}

fn scan_fields(cursor: &mut Cursor<'_>) -> Result<Stats, JsValue> {
    let field_count = cursor.read_varint()?;
    let mut stats = Stats {
        field_count,
        posting_count: 0,
        max_doc_id: 0,
    };
    for _ in 0..field_count {
        cursor.read_byte()?;
        let doc_count = cursor.read_varint()?;
        stats.posting_count += doc_count;
        let mut previous = 0_u64;
        for doc_offset in 0..doc_count {
            let delta = cursor.read_varint()?;
            let doc_id = if doc_offset == 0 {
                delta
            } else {
                previous
                    .checked_add(delta)
                    .ok_or_else(|| JsValue::from_str("doc id overflow"))?
            };
            stats.max_doc_id = stats.max_doc_id.max(doc_id);
            previous = doc_id;
        }
    }
    Ok(stats)
}

fn collect_fields(cursor: &mut Cursor<'_>) -> Result<HashMap<String, Vec<u64>>, JsValue> {
    let field_count = cursor.read_varint()?;
    let mut fields = HashMap::new();
    for _ in 0..field_count {
        let field = (cursor.read_byte()? as char).to_string();
        let doc_count = cursor.read_varint()?;
        let mut doc_ids = Vec::with_capacity(doc_count as usize);
        let mut previous = 0_u64;
        for doc_offset in 0..doc_count {
            let delta = cursor.read_varint()?;
            let doc_id = if doc_offset == 0 {
                delta
            } else {
                previous
                    .checked_add(delta)
                    .ok_or_else(|| JsValue::from_str("doc id overflow"))?
            };
            doc_ids.push(doc_id);
            previous = doc_id;
        }
        fields.insert(field, doc_ids);
    }
    Ok(fields)
}

fn read_directory(cursor: &mut Cursor<'_>) -> Result<Vec<(String, usize)>, JsValue> {
    let term_count = cursor.read_varint()?;
    let mut directory = Vec::with_capacity(term_count as usize);
    let mut payload_total = 0_usize;
    for _ in 0..term_count {
        let term_length = cursor.read_varint()? as usize;
        let term = str::from_utf8(cursor.read_bytes(term_length)?)
            .map_err(|error| JsValue::from_str(&error.to_string()))?
            .to_string();
        let payload_length = cursor.read_varint()? as usize;
        payload_total = payload_total
            .checked_add(payload_length)
            .ok_or_else(|| JsValue::from_str("payload length overflow"))?;
        directory.push((term, payload_length));
    }
    if cursor.offset + payload_total != cursor.data.len() {
        return Err(JsValue::from_str(
            "packed impact payload directory length mismatch",
        ));
    }
    Ok(directory)
}

fn field_impacts_from_metadata(metadata: &str) -> Result<(HashMap<String, f64>, usize), JsValue> {
    let value: serde_json::Value =
        serde_json::from_str(metadata).map_err(|error| JsValue::from_str(&error.to_string()))?;
    let mut impacts = HashMap::new();
    if let Some(object) = value.get("field_impacts").and_then(|item| item.as_object()) {
        for (field, impact) in object {
            impacts.insert(field.to_string(), impact.as_f64().unwrap_or(8.0));
        }
    }
    let block_size = value
        .get("block_size")
        .and_then(|item| item.as_u64())
        .unwrap_or(32)
        .max(8) as usize;
    Ok((impacts, block_size))
}

fn term_impact(term: &str, field: &str, field_impacts: &HashMap<String, f64>) -> f64 {
    field_impacts.get(field).copied().unwrap_or(8.0) + (term.chars().count().min(8) as f64)
}

fn push_term_blocks(
    blocks: &mut Vec<ImpactBlock>,
    term: &str,
    fields: HashMap<String, Vec<u64>>,
    block_size: usize,
    field_impacts: &HashMap<String, f64>,
) {
    for (field, ids) in fields {
        let impact = term_impact(term, &field, field_impacts);
        for chunk in ids.chunks(block_size) {
            blocks.push(ImpactBlock {
                key: format!("{term}\0{field}"),
                impact,
                ids: chunk.to_vec(),
            });
        }
    }
}

fn competitive_threshold(scores: &HashMap<u64, f64>, target: usize) -> f64 {
    if scores.len() < target {
        return f64::NEG_INFINITY;
    }
    let mut values: Vec<f64> = scores.values().copied().collect();
    values.sort_by(|a, b| b.partial_cmp(a).unwrap_or(std::cmp::Ordering::Equal));
    values[target.saturating_sub(1)]
}

fn suffix_unique_impact(blocks: &[ImpactBlock]) -> Vec<f64> {
    let mut suffix = vec![0.0; blocks.len() + 1];
    let mut seen = HashSet::new();
    let mut total = 0.0;
    for index in (0..blocks.len()).rev() {
        if seen.insert(blocks[index].key.clone()) {
            total += blocks[index].impact;
        }
        suffix[index] = total;
    }
    suffix
}

fn top_doc_ids(scores: &HashMap<u64, f64>, limit: usize) -> Vec<u64> {
    let mut entries: Vec<(u64, f64)> = scores
        .iter()
        .map(|(doc_id, score)| (*doc_id, *score))
        .collect();
    entries.sort_by(|left, right| {
        right
            .1
            .partial_cmp(&left.1)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then_with(|| left.0.cmp(&right.0))
    });
    entries
        .into_iter()
        .take(limit)
        .map(|(doc_id, _score)| doc_id)
        .collect()
}

fn sorted_score_entries(scores: &HashMap<u64, f64>) -> Vec<(u64, f64)> {
    let mut entries: Vec<(u64, f64)> = scores
        .iter()
        .map(|(doc_id, score)| (*doc_id, *score))
        .collect();
    entries.sort_by(|left, right| {
        right
            .1
            .partial_cmp(&left.1)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then_with(|| left.0.cmp(&right.0))
    });
    entries
}

fn collect_packed_impact_blocks(
    bytes: &[u8],
    query_terms_json: &str,
) -> Result<(Vec<ImpactBlock>, u64), JsValue> {
    let query_terms: Vec<String> = serde_json::from_str(query_terms_json)
        .map_err(|error| JsValue::from_str(&error.to_string()))?;
    let selected_terms: HashSet<String> = query_terms.iter().cloned().collect();
    let mut cursor = Cursor::new(bytes);
    let format = cursor.read_magic()?;
    let metadata_length = cursor.read_u32_le()? as usize;
    let metadata_bytes = cursor.read_bytes(metadata_length)?;
    let metadata =
        str::from_utf8(metadata_bytes).map_err(|error| JsValue::from_str(&error.to_string()))?;
    let (field_impacts, block_size) = field_impacts_from_metadata(metadata)?;
    let mut blocks = Vec::new();
    let mut matched_term_count = 0_u64;

    match format {
        PackedFormat::V1 => {
            let term_count = cursor.read_varint()?;
            for _ in 0..term_count {
                let term_length = cursor.read_varint()? as usize;
                let term = str::from_utf8(cursor.read_bytes(term_length)?)
                    .map_err(|error| JsValue::from_str(&error.to_string()))?
                    .to_string();
                if selected_terms.contains(&term) {
                    matched_term_count += 1;
                    let fields = collect_fields(&mut cursor)?;
                    push_term_blocks(&mut blocks, &term, fields, block_size, &field_impacts);
                } else {
                    scan_fields(&mut cursor)?;
                }
            }
        }
        PackedFormat::V2 => {
            let directory = read_directory(&mut cursor)?;
            for (term, payload_length) in directory {
                let end = cursor.offset + payload_length;
                let mut payload_cursor = Cursor::new(&cursor.data[cursor.offset..end]);
                if selected_terms.contains(&term) {
                    matched_term_count += 1;
                    let fields = collect_fields(&mut payload_cursor)?;
                    push_term_blocks(&mut blocks, &term, fields, block_size, &field_impacts);
                }
                if !payload_cursor.is_done() {
                    scan_fields(&mut payload_cursor)?;
                }
                if !payload_cursor.is_done() {
                    return Err(JsValue::from_str(
                        "trailing bytes in packed impact term payload",
                    ));
                }
                cursor.offset = end;
            }
        }
    }

    if !cursor.is_done() {
        return Err(JsValue::from_str("trailing bytes in packed impact index"));
    }

    blocks.sort_by(|left, right| {
        right
            .impact
            .partial_cmp(&left.impact)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then_with(|| left.key.cmp(&right.key))
    });
    Ok((blocks, matched_term_count))
}

fn apply_impact_blocks_to_scores(
    blocks: &[ImpactBlock],
    target_candidates: usize,
    scores: &mut HashMap<u64, f64>,
) -> ApplyStats {
    let suffix = suffix_unique_impact(blocks);
    let mut impact_blocks_visited = 0_u64;
    let mut impact_blocks_pruned = 0_u64;
    let mut postings_visited = 0_u64;
    let mut postings_pruned = 0_u64;
    let mut competitive = 0.0_f64;
    let target = target_candidates.max(1);

    for (index, block) in blocks.iter().enumerate() {
        let threshold = competitive_threshold(&scores, target);
        if threshold.is_finite() {
            competitive = threshold;
        }
        let max_possible_for_unseen_doc =
            block.impact + suffix.get(index + 1).copied().unwrap_or(0.0);
        let has_known_candidate = block.ids.iter().any(|doc_id| scores.contains_key(doc_id));
        if !has_known_candidate
            && scores.len() >= target
            && max_possible_for_unseen_doc <= threshold
        {
            impact_blocks_pruned += 1;
            postings_pruned += block.ids.len() as u64;
            continue;
        }
        impact_blocks_visited += 1;
        for doc_id in &block.ids {
            postings_visited += 1;
            *scores.entry(*doc_id).or_insert(0.0) += block.impact;
        }
    }

    ApplyStats {
        impact_blocks_visited,
        impact_blocks_pruned,
        postings_visited,
        postings_pruned,
        competitive_threshold: competitive,
    }
}

fn retrieve_packed_impact(
    bytes: &[u8],
    query_terms_json: &str,
    target_candidates: usize,
) -> Result<RetrievalResult, JsValue> {
    let (blocks, matched_term_count) = collect_packed_impact_blocks(bytes, query_terms_json)?;
    let mut scores: HashMap<u64, f64> = HashMap::new();
    let stats = apply_impact_blocks_to_scores(&blocks, target_candidates, &mut scores);

    Ok(RetrievalResult {
        matched_term_count,
        block_count: blocks.len(),
        scores,
        impact_blocks_visited: stats.impact_blocks_visited,
        impact_blocks_pruned: stats.impact_blocks_pruned,
        postings_visited: stats.postings_visited,
        postings_pruned: stats.postings_pruned,
        competitive_threshold: stats.competitive_threshold,
    })
}

#[wasm_bindgen]
pub struct PackedImpactRetrievalSession {
    target_candidates: usize,
    scores: HashMap<u64, f64>,
    matched_term_count: u64,
    block_count: usize,
    impact_blocks_visited: u64,
    impact_blocks_pruned: u64,
    postings_visited: u64,
    postings_pruned: u64,
    competitive_threshold: f64,
}

#[wasm_bindgen]
impl PackedImpactRetrievalSession {
    #[wasm_bindgen(constructor)]
    pub fn new(target_candidates: usize) -> PackedImpactRetrievalSession {
        PackedImpactRetrievalSession {
            target_candidates: target_candidates.max(1),
            scores: HashMap::new(),
            matched_term_count: 0,
            block_count: 0,
            impact_blocks_visited: 0,
            impact_blocks_pruned: 0,
            postings_visited: 0,
            postings_pruned: 0,
            competitive_threshold: 0.0,
        }
    }

    pub fn apply(&mut self, bytes: &[u8], query_terms_json: &str) -> Result<String, JsValue> {
        let (blocks, matched_term_count) = collect_packed_impact_blocks(bytes, query_terms_json)?;
        let stats =
            apply_impact_blocks_to_scores(&blocks, self.target_candidates, &mut self.scores);
        self.matched_term_count += matched_term_count;
        self.block_count += blocks.len();
        self.impact_blocks_visited += stats.impact_blocks_visited;
        self.impact_blocks_pruned += stats.impact_blocks_pruned;
        self.postings_visited += stats.postings_visited;
        self.postings_pruned += stats.postings_pruned;
        self.competitive_threshold = stats.competitive_threshold;

        Ok(serde_json::json!({
            "matched_term_count": matched_term_count,
            "block_count": blocks.len(),
            "candidate_count": self.scores.len(),
            "impact_blocks_visited": stats.impact_blocks_visited,
            "impact_blocks_pruned": stats.impact_blocks_pruned,
            "postings_visited": stats.postings_visited,
            "postings_pruned": stats.postings_pruned,
            "competitive_threshold": stats.competitive_threshold,
        })
        .to_string())
    }

    pub fn stats_json(&self) -> String {
        serde_json::json!({
            "matched_term_count": self.matched_term_count,
            "block_count": self.block_count,
            "candidate_count": self.scores.len(),
            "impact_blocks_visited": self.impact_blocks_visited,
            "impact_blocks_pruned": self.impact_blocks_pruned,
            "postings_visited": self.postings_visited,
            "postings_pruned": self.postings_pruned,
            "competitive_threshold": self.competitive_threshold,
        })
        .to_string()
    }

    pub fn scores_json(&self) -> String {
        serde_json::json!({
            "candidate_count": self.scores.len(),
            "score_entries": sorted_score_entries(&self.scores),
        })
        .to_string()
    }
}

#[wasm_bindgen]
pub fn decode_packed_impact_to_json(bytes: &[u8]) -> Result<String, JsValue> {
    let mut cursor = Cursor::new(bytes);
    let format = cursor.read_magic()?;

    let metadata_length = cursor.read_u32_le()? as usize;
    let metadata_bytes = cursor.read_bytes(metadata_length)?;
    let metadata =
        str::from_utf8(metadata_bytes).map_err(|error| JsValue::from_str(&error.to_string()))?;
    let mut output = metadata_prefix(metadata)?;
    if output.len() > 1 {
        output.push(',');
    }
    output.push_str("\"terms\":{");

    match format {
        PackedFormat::V1 => {
            let term_count = cursor.read_varint()?;
            for term_index in 0..term_count {
                if term_index > 0 {
                    output.push(',');
                }
                let term_length = cursor.read_varint()? as usize;
                let term = str::from_utf8(cursor.read_bytes(term_length)?)
                    .map_err(|error| JsValue::from_str(&error.to_string()))?;
                output.push_str(&json_string(term)?);
                output.push_str(":{");
                append_fields_json(&mut cursor, &mut output)?;
                output.push('}');
            }
        }
        PackedFormat::V2 => {
            let directory = read_directory(&mut cursor)?;
            for (term_index, (term, payload_length)) in directory.iter().enumerate() {
                if term_index > 0 {
                    output.push(',');
                }
                output.push_str(&json_string(term)?);
                output.push_str(":{");
                let end = cursor.offset + payload_length;
                let mut payload_cursor = Cursor::new(&cursor.data[cursor.offset..end]);
                append_fields_json(&mut payload_cursor, &mut output)?;
                if !payload_cursor.is_done() {
                    return Err(JsValue::from_str(
                        "trailing bytes in packed impact term payload",
                    ));
                }
                cursor.offset = end;
                output.push('}');
            }
        }
    }
    output.push_str("}}");

    if !cursor.is_done() {
        return Err(JsValue::from_str("trailing bytes in packed impact index"));
    }
    Ok(output)
}

#[wasm_bindgen]
pub fn decode_packed_impact_stats(bytes: &[u8]) -> Result<String, JsValue> {
    let mut cursor = Cursor::new(bytes);
    let format = cursor.read_magic()?;
    let metadata_length = cursor.read_u32_le()? as usize;
    cursor.read_bytes(metadata_length)?;

    let term_count: u64;
    let mut field_count = 0_u64;
    let mut posting_count = 0_u64;
    let mut max_doc_id = 0_u64;

    match format {
        PackedFormat::V1 => {
            term_count = cursor.read_varint()?;
            for _ in 0..term_count {
                let term_length = cursor.read_varint()? as usize;
                cursor.read_bytes(term_length)?;
                let stats = scan_fields(&mut cursor)?;
                field_count += stats.field_count;
                posting_count += stats.posting_count;
                max_doc_id = max_doc_id.max(stats.max_doc_id);
            }
        }
        PackedFormat::V2 => {
            let directory = read_directory(&mut cursor)?;
            term_count = directory.len() as u64;
            for (_term, payload_length) in directory {
                let end = cursor.offset + payload_length;
                let mut payload_cursor = Cursor::new(&cursor.data[cursor.offset..end]);
                let stats = scan_fields(&mut payload_cursor)?;
                if !payload_cursor.is_done() {
                    return Err(JsValue::from_str(
                        "trailing bytes in packed impact term payload",
                    ));
                }
                cursor.offset = end;
                field_count += stats.field_count;
                posting_count += stats.posting_count;
                max_doc_id = max_doc_id.max(stats.max_doc_id);
            }
        }
    }

    if !cursor.is_done() {
        return Err(JsValue::from_str("trailing bytes in packed impact index"));
    }

    Ok(format!(
        "{{\"term_count\":{term_count},\"field_count\":{field_count},\"posting_count\":{posting_count},\"max_doc_id\":{max_doc_id}}}"
    ))
}

#[wasm_bindgen]
pub fn retrieve_packed_impact_topk_stats(
    bytes: &[u8],
    query_terms_json: &str,
    target_candidates: usize,
) -> Result<String, JsValue> {
    let result = retrieve_packed_impact(bytes, query_terms_json, target_candidates)?;

    Ok(serde_json::json!({
        "matched_term_count": result.matched_term_count,
        "block_count": result.block_count,
        "candidate_count": result.scores.len(),
        "impact_blocks_visited": result.impact_blocks_visited,
        "impact_blocks_pruned": result.impact_blocks_pruned,
        "postings_visited": result.postings_visited,
        "postings_pruned": result.postings_pruned,
        "competitive_threshold": result.competitive_threshold,
        "top_doc_ids": top_doc_ids(&result.scores, 20),
    })
    .to_string())
}

#[wasm_bindgen]
pub fn retrieve_packed_impact_topk_scores(
    bytes: &[u8],
    query_terms_json: &str,
    target_candidates: usize,
) -> Result<String, JsValue> {
    let result = retrieve_packed_impact(bytes, query_terms_json, target_candidates)?;

    Ok(serde_json::json!({
        "matched_term_count": result.matched_term_count,
        "block_count": result.block_count,
        "candidate_count": result.scores.len(),
        "impact_blocks_visited": result.impact_blocks_visited,
        "impact_blocks_pruned": result.impact_blocks_pruned,
        "postings_visited": result.postings_visited,
        "postings_pruned": result.postings_pruned,
        "competitive_threshold": result.competitive_threshold,
        "top_doc_ids": top_doc_ids(&result.scores, 20),
        "score_entries": sorted_score_entries(&result.scores),
    })
    .to_string())
}
