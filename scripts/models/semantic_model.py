import re
from datetime import datetime
from typing import Any

from models.search_contract import (
    SEARCH_CATEGORIES,
    SEARCH_DOMAINS,
    SEARCH_INTENTS,
    SEARCH_LIFECYCLES,
    SEARCH_SOURCE_TYPES,
    normalize_contract_value,
)

DOMAIN_KEYWORDS = {
    "exam": ("考试", "期末", "补考", "重修", "四六级", "准考证", "考场"),
    "course": ("选课", "课程", "慕课", "学分", "成绩", "学籍", "校历", "转专业", "推免"),
    "degree": ("学位", "论文", "答辩", "开题", "盲审", "硕博连读", "毕业设计"),
    "scholarship": ("奖学金", "助学金", "资助", "困难认定", "评优", "励志", "助研", "助管", "助教"),
    "employment": ("就业", "招聘", "宣讲", "岗位", "实习", "双选会", "用人单位", "生源信息"),
    "competition": ("竞赛", "挑战杯", "互联网+", "校赛", "获奖", "创新大赛", "数学建模"),
    "international": ("海外", "境外", "国际", "交换", "访学", "留学", "港澳台", "外方"),
    "project": ("项目", "大创", "创业基金", "科创", "申报", "训练计划", "实验室招新"),
    "innovation_project": ("大创", "大学生创新创业训练计划", "创新创业项目", "创新训练"),
    "library": ("图书馆", "数据库", "研读室", "馆藏", "借阅", "开放时间"),
    "security": ("保卫", "交通管制", "消防", "安全", "户籍", "车贴", "通行"),
    "logistics": ("后勤", "停水", "停电", "维修", "洗浴", "医保", "班车", "体检"),
    "campus_network": ("校园网", "VPN", "统一身份认证", "邮箱", "信息化"),
    "subsidy": ("助学金", "困难认定", "资助", "贫困补助"),
    "medical_insurance": ("医保", "医疗保险", "体检"),
    "archive": ("档案", "证明", "成绩单", "归档"),
    "lecture": ("讲座", "报告", "论坛", "沙龙", "学术活动", "培训"),
    "research": ("科研", "课题", "基金", "专利", "成果转化", "论文", "自然科学"),
    "resource": ("资料", "下载", "手册", "指南", "流程", "表格", "模板"),
    "policy": ("规章", "制度", "办法", "章程", "信息公开", "政策"),
    "life": ("宿舍", "返校", "离校", "社团", "志愿服务", "文体", "心理", "活动"),
    "news": ("新闻", "大会", "调研", "召开", "活动回顾", "报道"),
    "academic": ("培养", "教学", "学院", "导师", "班级事务", "实验安排"),
}

INTENT_KEYWORDS = {
    "apply": ("申请", "申报", "遴选", "选拔", "推荐", "报名", "招募"),
    "register": ("报名", "登记", "预约", "注册", "确认"),
    "submit": ("提交", "报送", "填写", "上传", "递交", "交至", "缴费"),
    "attend": ("参加", "参会", "出席", "讲座", "报告", "培训", "活动"),
    "check_result": ("查询", "查看", "成绩", "结果", "名单", "入选", "获奖"),
    "publicity": ("公示", "名单", "拟推荐", "拟获奖", "拟录取", "结果公布"),
    "download": ("下载", "附件", "表格", "模板", "手册", "指南"),
    "schedule": ("安排", "时间", "开放", "校历", "日程", "考试安排", "班车"),
    "alert": ("停水", "停电", "管制", "封闭", "提醒", "预警", "安全"),
    "pay": ("缴费", "支付", "学费", "收费"),
    "contact": ("联系", "咨询", "联系人", "电话", "邮箱"),
    "export": ("导出", "日历", "ics", "下载日程"),
    "read": ("通知", "公告", "新闻", "报道", "说明"),
}

DISPLAY_CATEGORY_BY_DOMAIN = {
    "exam": "考试",
    "course": "选课",
    "degree": "研究生",
    "scholarship": "奖助",
    "employment": "就业",
    "competition": "竞赛",
    "international": "项目",
    "project": "项目",
    "innovation_project": "项目",
    "library": "生活",
    "security": "生活",
    "logistics": "生活",
    "campus_network": "生活",
    "subsidy": "奖助",
    "medical_insurance": "生活",
    "archive": "资料",
    "lecture": "讲座",
    "research": "项目",
    "resource": "资料",
    "policy": "公告",
    "life": "生活",
    "news": "公告",
    "academic": "学院",
}

DOMAIN_LABELS = {
    "academic": "学业事务",
    "exam": "考试",
    "course": "课程选课",
    "degree": "学位培养",
    "scholarship": "奖助评优",
    "employment": "就业实习",
    "competition": "竞赛",
    "project": "项目机会",
    "international": "国际交流",
    "life": "校园生活",
    "library": "图书馆",
    "security": "安全保卫",
    "logistics": "后勤服务",
    "campus_network": "校园网络",
    "subsidy": "资助补助",
    "medical_insurance": "医保体检",
    "archive": "档案服务",
    "lecture": "讲座活动",
    "research": "科研事务",
    "resource": "学习资料",
    "news": "校园新闻",
    "policy": "政策制度",
}

INTENT_LABELS = {
    "apply": "申请",
    "register": "报名",
    "submit": "提交",
    "attend": "参加",
    "check_result": "查结果",
    "publicity": "公示",
    "download": "下载",
    "read": "阅读",
    "schedule": "安排",
    "alert": "提醒",
    "pay": "缴费",
    "contact": "联系",
    "export": "导出",
}

SOURCE_TYPE_LABELS = {
    "central_admin": "校级部门",
    "central_notice": "校级通知",
    "central_news": "校园新闻",
    "college": "学院站",
    "service_unit": "服务单位",
    "job_platform": "就业平台",
    "github_resource": "资料仓库",
    "research_admin": "科研管理",
    "policy": "信息公开",
    "exam_vertical": "考试频道",
}

LIFECYCLE_LABELS = {
    "active": "进行中",
    "upcoming": "即将开始",
    "expired": "已过期",
    "evergreen": "长期有效",
    "unknown": "时效未知",
}


def normalize_domain(value: Any, fallback: str = "news") -> str:
    return normalize_contract_value(value, SEARCH_DOMAINS, fallback)


def normalize_intent(value: Any, fallback: str = "read") -> str:
    return normalize_contract_value(value, SEARCH_INTENTS, fallback)


def normalize_source_type(value: Any, fallback: str = "central_admin") -> str:
    return normalize_contract_value(value, SEARCH_SOURCE_TYPES, fallback)


def normalize_category(value: Any, fallback: str = "公告") -> str:
    return normalize_contract_value(value, SEARCH_CATEGORIES, fallback)


def normalize_lifecycle(value: Any, fallback: str = "unknown") -> str:
    return normalize_contract_value(value, SEARCH_LIFECYCLES, fallback)


def infer_domain(text: str, fallback_category: str = "公告", source_type: str = "central_admin") -> str:
    if source_type == "github_resource":
        return "resource"

    lowered = text.lower()
    best_domain = ""
    best_score = 0
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword.lower() in lowered)
        if score > best_score:
            best_domain = domain
            best_score = score

    if best_domain:
        return best_domain

    category_fallbacks = {
        "考试": "exam",
        "选课": "course",
        "竞赛": "competition",
        "奖助": "scholarship",
        "就业": "employment",
        "讲座": "lecture",
        "生活": "life",
        "研究生": "degree",
        "学院": "academic",
        "项目": "project",
        "资料": "resource",
    }
    if fallback_category in category_fallbacks:
        return category_fallbacks[fallback_category]
    if source_type == "college":
        return "academic"
    if source_type == "github_resource":
        return "resource"
    if source_type == "central_news":
        return "news"
    if source_type == "policy":
        return "policy"
    return "news"


def infer_intent(text: str, action_required: bool = False, attachments_count: int = 0) -> str:
    lowered = text.lower()
    best_intent = ""
    best_score = 0
    for intent, keywords in INTENT_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword.lower() in lowered)
        if score > best_score:
            best_intent = intent
            best_score = score

    if best_intent:
        return best_intent
    if action_required:
        return "submit"
    if attachments_count > 0:
        return "download"
    return "read"


def derive_display_category(domain: str, intent: str, fallback: str = "公告") -> str:
    if intent == "publicity" and domain in {"scholarship", "competition", "degree"}:
        return DISPLAY_CATEGORY_BY_DOMAIN.get(domain, fallback)
    return DISPLAY_CATEGORY_BY_DOMAIN.get(domain, fallback if fallback else "公告")


def infer_lifecycle(published_at: str | None, deadline: str | None, now: datetime, kind: str = "notice") -> str:
    if kind == "resource":
        return "evergreen"

    if deadline:
        try:
            deadline_dt = datetime.fromisoformat(deadline)
            compare_now = now
            if deadline_dt.tzinfo is None and now.tzinfo is not None:
                deadline_dt = deadline_dt.replace(tzinfo=now.tzinfo)
            elif deadline_dt.tzinfo is not None and now.tzinfo is None:
                compare_now = now.replace(tzinfo=deadline_dt.tzinfo)
            return "expired" if deadline_dt < compare_now else "active"
        except ValueError:
            return "unknown"

    if not published_at:
        return "unknown"

    try:
        published = datetime.fromisoformat(published_at)
        if published.tzinfo is None:
            published = published.replace(tzinfo=now.tzinfo)
    except ValueError:
        return "unknown"

    days = (now.date() - published.date()).days
    if days < -1:
        return "upcoming"
    if days <= 45:
        return "active"
    if days <= 365:
        return "unknown"
    return "expired"


def extract_evidence(text: str, keywords: list[str] | tuple[str, ...], limit: int = 3) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    sentences = re.split(r"(?<=[。！？!?；;])", cleaned)
    evidence: list[str] = []
    for sentence in sentences:
        snippet = sentence.strip()
        if not snippet:
            continue
        if any(keyword and keyword in snippet for keyword in keywords):
            evidence.append(snippet[:160])
        if len(evidence) >= limit:
            break
    if not evidence:
        evidence.append(cleaned[:160])
    return evidence
