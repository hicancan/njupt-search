from __future__ import annotations

from njupt_search_indexer.sitegraph_binary_index import PACKED_IMPACT_MAGIC_V2, pack_impact_index, unpack_impact_index, unpack_impact_terms


def test_packed_impact_index_roundtrips_delta_encoded_terms() -> None:
    payload = {
        "version": "sitegraph-local-body-impact-v2",
        "tokenizer": "nfkc-lower-cjk-ngram-code",
        "field_codes": {"summary": "m", "content": "c"},
        "field_impacts": {"m": 16, "c": 10},
        "block_size": 32,
        "scoring_model": "impact-ordered-block-max-bm25f-lite-v2",
        "scope": {
            "index_id": "jwc__exam__2026",
            "source_id": "jwc",
            "facet": "exam",
            "year": "2026",
            "shard_ids": ["s1", "s2"],
        },
        "terms": {
            "校历": {"m": [3, 9, 14], "c": [4]},
            "考试": {"c": [1, 2, 99]},
        },
    }

    packed = pack_impact_index(payload)

    assert packed.startswith(PACKED_IMPACT_MAGIC_V2)
    assert len(packed) < len(str(payload).encode("utf-8"))
    assert unpack_impact_index(packed) == payload
    assert unpack_impact_terms(packed, ["考试"]) == {
        **payload,
        "terms": {
            "考试": {"c": [1, 2, 99]},
        },
    }
