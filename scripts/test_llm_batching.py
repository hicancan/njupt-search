import json
import unittest

from core.llm_scorer import BatchLLMResult, redact_for_log, split_llm_batches


class LLMBatchingTests(unittest.TestCase):
    def test_splitter_respects_doc_limit(self) -> None:
        documents = [{"id": str(index), "content": "x" * 10} for index in range(5)]
        batches = split_llm_batches(documents, max_docs=2, max_chars=10_000)
        self.assertEqual([len(batch) for batch in batches], [2, 2, 1])

    def test_splitter_respects_char_limit(self) -> None:
        documents = [{"id": str(index), "content": "x" * 2100} for index in range(3)]
        batches = split_llm_batches(documents, max_docs=10, max_chars=2200)
        self.assertEqual(len(batches), 3)

    def test_batch_result_schema_accepts_fixture(self) -> None:
        payload = {
            "results": [
                {
                    "id": "doc-1",
                    "audience": ["本科生"],
                    "category": "项目",
                    "domain": "international",
                    "intent": "apply",
                    "sub_category": "海外交流",
                    "tags": ["海外交流", "报名"],
                    "deadline": None,
                    "action_required": True,
                    "action_type": "报名",
                    "action_summary": "学生需按通知报名。",
                    "required_materials": [],
                    "student_summary": "本科生可关注海外交流报名。",
                    "sensitive": False,
                    "sensitive_types": [],
                    "attachment_roles": [],
                    "risk_flags": [],
                    "evidence": ["报名"],
                    "confidence": 0.82,
                    "review_required": False,
                }
            ]
        }
        validated = BatchLLMResult.model_validate(payload)
        self.assertEqual(validated.results[0].id, "doc-1")

    def test_redaction_removes_keys_and_urls(self) -> None:
        message = "POST https://api.example.test/path?key=SECRET Bearer sk-sample-key failed"
        redacted = redact_for_log(message)
        self.assertNotIn("SECRET", redacted)
        self.assertNotIn("sk-sample-key", redacted)
        self.assertNotIn("https://api.example.test", redacted)
        self.assertIn("<redacted-key>", redacted)

    def test_fixture_is_json_serializable(self) -> None:
        payload = BatchLLMResult(results=[])
        self.assertEqual(json.loads(payload.model_dump_json()), {"results": []})


if __name__ == "__main__":
    unittest.main()
