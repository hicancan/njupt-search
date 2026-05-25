import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
routes_file = os.path.join(BASE_DIR, 'config', 'query_routes.json')

with open(routes_file, 'r', encoding='utf-8') as f:
    routes = json.load(f)

cet_route = None
for r in routes:
    if r['id'] == 'exam_notice_search':
        # Create cet route
        cet_route = json.loads(json.dumps(r))
        cet_route['id'] = 'cet_notice_search'
        cet_route['query_type'] = 'cet_notice_search'
        cet_route['priority'] = 95
        # "CET", "四六级", "四级", "六级", "大学英语四级", "大学英语六级", "英语四级", "英语六级"
        cet_route['triggers'] = ["CET", "\u56db\u516d\u7ea7", "\u56db\u7ea7", "\u516d\u7ea7", "\u5927\u5b66\u82f1\u8bed\u56db\u7ea7", "\u5927\u5b66\u82f1\u8bed\u516d\u7ea7", "\u82f1\u8bed\u56db\u7ea7", "\u82f1\u8bed\u516d\u7ea7"]
        cet_route['soft_terms'] = []
        # "慕课", "封闭教学楼", "普通期末"
        cet_route['bad_result_terms'] = ["\u6155\u8bfe", "\u5c01\u95ed\u6559\u5b66\u697c", "\u666e\u901a\u671f\u672b"]
        # "CET", "四级", "六级", "四六级"
        cet_route['must_include_terms_for_top_results'] = ["CET", "\u56db\u7ea7", "\u516d\u7ea7", "\u56db\u516d\u7ea7"]
        
    elif r['id'] == 'degree_defense_search':
        # "申请考核制", "招生实施细则", "培养方案"
        r['bad_result_terms'] = ["\u7533\u8bf7\u8003\u6838\u5236", "\u62db\u751f\u5b9e\u65bd\u7ec6\u5219", "\u57f9\u517b\u65b9\u6848"]
        # "论文", "答辩", "学位", "毕业"
        r['must_include_terms_for_top_results'] = ["\u8bba\u6587", "\u7b54\u8fa9", "\u5b66\u4f4d", "\u6bd5\u4e1a"]
        r['blocked_sources_for_top5'] = r.get('blocked_sources_for_top5', []) + ["cxcy"]
        r['blocked_domains_for_top5'] = r.get('blocked_domains_for_top5', []) + ["innovation_project"]
        
    elif r['id'] == 'service_search':
        r['subtypes'] = ["medical_insurance_service", "campus_network_service", "repair_service"]
        # "桂花糕", "停电"
        r['bad_result_terms'] = ["\u6842\u82b1\u7cd5", "\u505c\u7535"]
        r['blocked_sources_for_top5'] = r.get('blocked_sources_for_top5', []) + ["cxcy"]
        r['blocked_domains_for_top5'] = r.get('blocked_domains_for_top5', []) + ["innovation_project"]
        
    elif r['id'] == 'resource_search':
        r['subtypes'] = ["course_resource", "exam_paper_resource", "video_resource"]
        
    elif r['id'] == 'class_exam_lookup':
        r['top1_prefer_exact_title'] = True

if cet_route:
    routes.insert(0, cet_route)

with open(routes_file, 'w', encoding='utf-8') as f:
    json.dump(routes, f, ensure_ascii=False, indent=2)

cases = [
  {
    "query": "\u56db\u516d\u7ea7", # 四六级
    "route": "cet_notice_search",
    "top5_must_include_any_terms": ["\u56db\u7ea7", "\u516d\u7ea7", "CET", "\u56db\u516d\u7ea7"],
    "top5_must_not_include_any_terms": ["\u6155\u8bfe", "\u5c01\u95ed\u6559\u5b66\u697c", "\u666e\u901a\u671f\u672b"]
  },
  {
    "query": "CET",
    "route": "cet_notice_search",
    "top5_must_include_any_terms": ["\u56db\u7ea7", "\u516d\u7ea7", "CET", "\u56db\u516d\u7ea7"]
  },
  {
    "query": "\u56db\u7ea7", # 四级
    "route": "cet_notice_search",
    "top5_must_include_any_terms": ["\u56db\u7ea7", "\u516d\u7ea7", "CET", "\u56db\u516d\u7ea7"]
  },
  {
    "query": "\u516d\u7ea7", # 六级
    "route": "cet_notice_search",
    "top5_must_include_any_terms": ["\u56db\u7ea7", "\u516d\u7ea7", "CET", "\u56db\u516d\u7ea7"]
  },
  {
    "query": "\u8bba\u6587\u7b54\u8fa9", # 论文答辩
    "route": "degree_defense_search",
    "top5_must_include_any_terms": ["\u8bba\u6587", "\u7b54\u8fa9", "\u5b66\u4f4d", "\u6bd5\u4e1a"],
    "top5_must_not_include_any_terms": ["\u7533\u8bf7\u8003\u6838\u5236", "\u62db\u751f\u5b9e\u65bd\u7ec6\u5219", "\u57f9\u517b\u65b9\u6848"],
    "top5_must_not_source_any": ["cxcy"],
    "top5_must_not_domain_any": ["innovation_project"]
  },
  {
    "query": "\u6bd5\u4e1a\u7b54\u8fa9", # 毕业答辩
    "route": "degree_defense_search",
    "top5_must_include_any_terms": ["\u8bba\u6587", "\u7b54\u8fa9", "\u5b66\u4f4d", "\u6bd5\u4e1a"]
  },
  {
    "query": "\u5927\u521b\u7b54\u8fa9", # 大创答辩
    "route": "innovation_project_search",
    "top5_must_include_source_any": ["cxcy", "project", "innovation_project"]
  },
  {
    "query": "\u533b\u4fdd", # 医保
    "route": "service_search",
    "top5_must_include_any_terms": ["\u533b\u4fdd", "\u533b\u7597", "\u53c2\u4fdd", "\u62a5\u9500"],
    "top5_must_not_include_any_terms": ["\u6842\u82b1\u7cd5", "\u505c\u7535"],
    "top5_must_not_source_any": ["cxcy"],
    "top5_must_not_domain_any": ["innovation_project"]
  },
  {
    "query": "\u53c2\u4fdd", # 参保
    "route": "service_search",
    "top5_must_include_any_terms": ["\u533b\u4fdd", "\u533b\u7597", "\u53c2\u4fdd", "\u62a5\u9500"]
  },
  {
    "query": "\u62a5\u9500", # 报销
    "route": "service_search",
    "top5_must_include_any_terms": ["\u533b\u4fdd", "\u533b\u7597", "\u53c2\u4fdd", "\u62a5\u9500"]
  },
  {
    "query": "\u8f6c\u4e13\u4e1a", # 转专业
    "route": "official_notice_search",
    "top5_must_include_any_terms": ["\u8f6c\u4e13\u4e1a"],
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
    "query": "B250403 \u9ad8\u6570",
    "route": "class_exam_lookup",
    "allow_empty": True,
    "surface": "class_exam_lookup"
  },
  {
    "query": "\u9ad8\u6570",
    "route": "resource_search"
  },
  {
    "query": "\u9ad8\u6570\u8003\u8bd5",
    "route": "exam_notice_search"
  },
  {
    "query": "\u79bb\u6563\u6570\u5b66",
    "route": "resource_search"
  },
  {
    "query": "\u5927\u521b",
    "route": "innovation_project_search"
  },
  {
    "query": "\u5956\u5b66\u91d1",
    "route": "scholarship_search"
  },
  {
    "query": "\u52a9\u5b66\u91d1",
    "route": "subsidy_search"
  },
  {
    "query": "\u56f0\u96be\u8ba4\u5b9a",
    "route": "subsidy_search"
  },
  {
    "query": "\u5ba3\u8bb2\u4f1a",
    "route": "job_search"
  },
  {
    "query": "\u5b9e\u4e60",
    "route": "job_search"
  },
  {
    "query": "\u505c\u7535",
    "route": "campus_alert_search"
  },
  {
    "query": "\u6821\u56ed\u7f51",
    "route": "service_search"
  },
  {
    "query": "\u56fe\u4e66\u9986\u5f00\u653e",
    "route": "library_search"
  },
  {
    "query": "\u6863\u6848",
    "route": "graduation_search"
  },
  {
    "query": "\u6bd5\u4e1a\u8bbe\u8ba1",
    "route": "degree_defense_search"
  },
  {
    "query": "\u84dd\u6865\u676f",
    "route": "competition_search"
  },
  {
    "query": "\u6311\u6218\u676f",
    "route": "competition_search"
  }
]

fixtures = [
  {"query": c["query"], "expected_route": c["route"]} for c in cases
]

with open(os.path.join(BASE_DIR, 'eval', 'search_cases.json'), 'w', encoding='utf-8') as f:
    json.dump(cases, f, ensure_ascii=False, indent=2)

with open(os.path.join(BASE_DIR, 'tests', 'search_router_fixtures.json'), 'w', encoding='utf-8') as f:
    json.dump(fixtures, f, ensure_ascii=False, indent=2)
