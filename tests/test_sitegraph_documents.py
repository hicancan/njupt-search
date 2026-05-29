from njupt_search_indexer.sitegraph_documents import build_documents, infer_version_date, section_label


def test_document_date_and_section_helpers() -> None:
    assert infer_version_date("附件发布于2026年5月29日") == "2026-05-29"
    assert infer_version_date("更新 5.29", published_at="2026-05-01") == "2026-05-29"
    assert section_label({"section_id": "exam", "name": "考试安排", "nav_path": [], "business_tags": ["考试"]}) == (
        "考试安排",
        ["考试安排"],
        ["考试"],
    )


def test_build_documents_preserves_detail_attachment_external_and_utility_records() -> None:
    package = {
        "site": {
            "site_id": "jwc",
            "name": "教务处",
            "domain": "jwc.njupt.edu.cn",
            "base_url": "https://jwc.njupt.edu.cn",
        },
        "sections": [
            {
                "section_id": "exam",
                "name": "考试安排",
                "nav_path": ["首页", "考试安排"],
                "business_tags": ["考试"],
            }
        ],
        "list_pages": [{"url": "https://jwc.njupt.edu.cn/exam", "section_id": "exam"}],
        "detail_pages": [
            {
                "url": "https://jwc.njupt.edu.cn/exam/detail",
                "page_id": "d1",
                "section_id": "exam",
                "title": "2026年期末考试安排",
                "content_text": "期末考试考场安排内容",
                "published_at": "2026-05-01",
                "page_type": "detail_article_page",
                "headings": ["考试"],
            }
        ],
        "attachments": [
            {
                "attachment_id": "a1",
                "name": "附件1.xls",
                "url": "https://jwc.njupt.edu.cn/files/a1.xls",
                "extension": "xls",
                "parent_url": "https://jwc.njupt.edu.cn/exam/detail",
                "position": 1,
            }
        ],
        "external_links": [
            {
                "external_id": "e1",
                "label": "教务系统",
                "url": "https://jwxt.njupt.edu.cn",
                "category": "external_system",
                "source_url": "https://jwc.njupt.edu.cn/exam",
                "source_section_id": "exam",
                "recorded_at": "2026-05-01",
            }
        ],
        "edges": [
            {
                "edge_id": "u1",
                "anchor_text": "考试信息查询",
                "from_url": "https://jwc.njupt.edu.cn",
                "to_url": "https://jwc.njupt.edu.cn/exam",
            }
        ],
    }

    built = build_documents(package)

    assert len(built["documents"]) == 3
    assert len(built["attachment_index"]) == 1
    assert len(built["external_index"]) == 1

    detail = built["documents"][0]
    assert detail["id"] == "jwc-detail-d1"
    assert detail["facet"] == "exam"
    assert detail["task_kind"] == "exam_schedule"
    assert detail["attachment_count"] == 1
    assert detail["attachments"][0]["parent_doc_id"] == "jwc-detail-d1"

    external = built["documents"][1]
    assert external["record_type"] == "external"
    assert external["facet"] == "system"

    utility = built["documents"][2]
    assert utility["record_type"] == "utility"
    assert utility["title"] == "考试信息查询"
