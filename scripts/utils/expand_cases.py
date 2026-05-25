import json
import os

cases = [
    {
        "query": "四六级",
        "route": "cet_notice_search",
        "top5_must_include_any_terms": ["四级", "六级", "CET", "四六级"],
        "top5_must_not_include_any_terms": ["慕课", "封闭教学楼", "普通期末"]
    },
    {
        "query": "CET",
        "route": "cet_notice_search",
        "top5_must_include_any_terms": ["四级", "六级", "CET", "四六级"]
    },
    {
        "query": "四级",
        "route": "cet_notice_search",
        "top5_must_include_any_terms": ["四级", "六级", "CET", "四六级"]
    },
    {
        "query": "六级",
        "route": "cet_notice_search",
        "top5_must_include_any_terms": ["四级", "六级", "CET", "四六级"]
    },
    {
        "query": "论文答辩",
        "route": "degree_defense_search",
        "top5_must_include_any_terms": ["论文", "答辩", "学位", "毕业"],
        "top5_must_not_include_any_terms": ["申请考核制", "招生实施细则", "培养方案"],
        "top5_must_not_source_any": ["cxcy"],
        "top5_must_not_domain_any": ["innovation_project"]
    },
    {
        "query": "毕业答辩",
        "route": "degree_defense_search",
        "top5_must_include_any_terms": ["论文", "答辩", "学位", "毕业"]
    },
    {
        "query": "大创答辩",
        "route": "innovation_project_search",
        "top5_must_include_source_any": ["cxcy", "project", "innovation_project"]
    },
    {
        "query": "医保",
        "route": "service_search",
        "top5_must_include_any_terms": ["医保", "医疗", "参保", "报销"],
        "top5_must_not_include_any_terms": ["桂花糕", "停电"],
        "top5_must_not_source_any": ["cxcy"],
        "top5_must_not_domain_any": ["innovation_project"]
    },
    {
        "query": "参保",
        "route": "service_search",
        "top5_must_include_any_terms": ["医保", "医疗", "参保", "报销"]
    },
    {
        "query": "报销",
        "route": "service_search",
        "top5_must_include_any_terms": ["医保", "医疗", "参保", "报销"]
    },
    {
        "query": "转专业",
        "route": "official_notice_search",
        "top5_must_include_any_terms": ["转专业"],
        "top5_must_not_source_any": ["cxcy"],
        "top5_must_not_domain_any": ["innovation_project"]
    },
    {
        "query": "B250403",
        "route": "class_exam_lookup",
        "allow_empty": True,
        "surface": "class_exam_lookup"
    },
    {
        "query": "B250403 高数",
        "route": "class_exam_lookup",
        "allow_empty": True,
        "surface": "class_exam_lookup"
    },
    {
        "query": "高数",
        "route": "resource_search"
    },
    {
        "query": "高数考试",
        "route": "exam_notice_search"
    },
    {
        "query": "离散数学",
        "route": "resource_search"
    },
    {
        "query": "大创",
        "route": "innovation_project_search"
    },
    {
        "query": "奖学金",
        "route": "scholarship_search"
    },
    {
        "query": "助学金",
        "route": "subsidy_search"
    },
    {
        "query": "困难认定",
        "route": "subsidy_search"
    },
    {
        "query": "宣讲会",
        "route": "job_search"
    },
    {
        "query": "实习",
        "route": "job_search"
    },
    {
        "query": "停电",
        "route": "campus_alert_search"
    },
    {
        "query": "校园网",
        "route": "service_search"
    },
    {
        "query": "图书馆开放",
        "route": "library_search"
    },
    {
        "query": "档案",
        "route": "graduation_search"
    },
    {
        "query": "毕业设计",
        "route": "degree_defense_search"
    },
    {
        "query": "蓝桥杯",
        "route": "competition_search"
    },
    {
        "query": "挑战杯",
        "route": "competition_search"
    }
]

fixtures = [
  {
    "query": "四六级",
    "expected_route": "cet_notice_search"
  },
  {
    "query": "CET",
    "expected_route": "cet_notice_search"
  },
  {
    "query": "四级",
    "expected_route": "cet_notice_search"
  },
  {
    "query": "六级",
    "expected_route": "cet_notice_search"
  },
  {
    "query": "论文答辩",
    "expected_route": "degree_defense_search"
  },
  {
    "query": "大创答辩",
    "expected_route": "innovation_project_search"
  },
  {
    "query": "医保",
    "expected_route": "service_search"
  },
  {
    "query": "转专业",
    "expected_route": "official_notice_search"
  },
  {
    "query": "B250403",
    "expected_route": "class_exam_lookup"
  },
  {
    "query": "B250403 高数",
    "expected_route": "class_exam_lookup"
  },
  {
    "query": "高数",
    "expected_route": "resource_search"
  },
  {
    "query": "高数考试",
    "expected_route": "exam_notice_search"
  },
  {
    "query": "离散数学",
    "expected_route": "resource_search"
  },
  {
    "query": "停电",
    "expected_route": "campus_alert_search"
  },
  {
    "query": "校园网",
    "expected_route": "service_search"
  },
  {
    "query": "奖学金",
    "expected_route": "scholarship_search"
  },
  {
    "query": "助学金",
    "expected_route": "subsidy_search"
  },
  {
    "query": "宣讲会",
    "expected_route": "job_search"
  },
  {
    "query": "图书馆开放",
    "expected_route": "library_search"
  },
  {
    "query": "档案",
    "expected_route": "graduation_search"
  }
]

with open(os.path.join(os.path.dirname(__file__), '..', 'eval', 'search_cases.json'), 'wb') as f:
    f.write(json.dumps(cases, ensure_ascii=False, indent=2).encode('utf-8'))

with open(os.path.join(os.path.dirname(__file__), '..', 'tests', 'search_router_fixtures.json'), 'wb') as f:
    f.write(json.dumps(fixtures, ensure_ascii=False, indent=2).encode('utf-8'))
