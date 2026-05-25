import json
import re
import os
from typing import Any, Dict, List

def load_query_routes(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)

def route_query(raw_query: str, routes: List[Dict[str, Any]]) -> Dict[str, Any]:
    normalized_query = re.sub(r"\s+", " ", str(raw_query or "")).strip()
    query_lower = normalized_query.lower()
    
    scored_routes = []
    
    for route in routes:
        evidence_score = 0
        must_have = route.get("must_have_any", [])
        if must_have:
            if not any(term.lower() in query_lower for term in must_have):
                if route.get("id") == "class_exam_lookup" and re.search(r"^[a-z]\d{6,8}", query_lower):
                    pass
                else:
                    evidence_score -= 1000

        if route.get("id") == "class_exam_lookup" and re.search(r"^[a-z]\d{6,8}", query_lower):
            evidence_score += 100
            
        triggers = route.get("triggers", [])
        for trigger in triggers:
            if trigger.lower() in query_lower:
                evidence_score += 50

        soft_terms = route.get("soft_terms", [])
        for term in soft_terms:
            if term.lower() in query_lower:
                evidence_score += 15

        negative_terms = route.get("negative_terms", [])
        for term in negative_terms:
            if term.lower() in query_lower:
                evidence_score -= 50
                
        if evidence_score > 0:
            score = evidence_score + (route.get("priority", 50) / 100.0)
            scored_routes.append({"route": route, "score": score})

    scored_routes.sort(key=lambda x: x["score"], reverse=True)
    if scored_routes:
        best = scored_routes[0]
        best_route = best["route"]
        best_score = best["score"]
    else:
        best_route = {"id": "general_search", "query_type": "general_search"}
        best_score = 0
    
    confidence = 0.5
    if best_score >= 80:
        confidence = 0.95
    elif best_score >= 60:
        confidence = 0.8
        
    alt_routes = [
        {"query_type": r["route"]["query_type"], "score": r["score"]}
        for r in scored_routes[1:4] if r["score"] > 0
    ]

    return {
        "raw_query": raw_query,
        "normalized_query": normalized_query,
        "query_type": best_route.get("query_type", "general_search"),
        "route_score": best_score,
        "route_confidence": confidence,
        "route_source": "query_routes_v2",
        "target_domains": best_route.get("must_domains", []) + best_route.get("preferred_domains", []),
        "target_intents": best_route.get("preferred_intents", []),
        "preferred_sources": best_route.get("preferred_sources", []),
        "preferred_channels": best_route.get("preferred_channels", []),
        "blocked_domains_for_top5": best_route.get("blocked_domains_for_top5", []),
        "blocked_sources_for_top5": best_route.get("blocked_sources_for_top5", []),
        "bad_result_terms": best_route.get("bad_result_terms", []),
        "must_include_terms_for_top_results": best_route.get("must_include_terms_for_top_results", []),
        "allow_resource_top5": best_route.get("allow_resource_top5", True),
        "freshness_preference": best_route.get("freshness_preference", "none"),
        "top1_prefer_exact_title": best_route.get("top1_prefer_exact_title", False),
        "alternative_routes": alt_routes,
        "explanation": best_route.get("explanation", "")
    }
