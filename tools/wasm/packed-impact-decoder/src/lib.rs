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
        return Err(JsValue::from_str("packed impact payload directory length mismatch"));
    }
    Ok(directory)
}

#[wasm_bindgen]
pub fn decode_packed_impact_to_json(bytes: &[u8]) -> Result<String, JsValue> {
    let mut cursor = Cursor::new(bytes);
    let format = cursor.read_magic()?;

    let metadata_length = cursor.read_u32_le()? as usize;
    let metadata_bytes = cursor.read_bytes(metadata_length)?;
    let metadata = str::from_utf8(metadata_bytes).map_err(|error| JsValue::from_str(&error.to_string()))?;
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
                    return Err(JsValue::from_str("trailing bytes in packed impact term payload"));
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
                    return Err(JsValue::from_str("trailing bytes in packed impact term payload"));
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
