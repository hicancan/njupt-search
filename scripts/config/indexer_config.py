import os
import json
from dataclasses import dataclass
from datetime import timezone, timedelta

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")
INDEX_DIR = os.path.join(PUBLIC_DIR, "index")
DOCUMENTS_PATH = os.path.join(INDEX_DIR, "documents.json")
MANIFEST_PATH = os.path.join(INDEX_DIR, "manifest.json")
SOURCE_CHANNEL_CONFIG_PATH = os.path.join(BASE_DIR, "config", "source_channels.json")
QUERY_ALIASES_PATH = os.path.join(BASE_DIR, "config", "query_aliases.json")
ONTOLOGY_PATH = os.path.join(BASE_DIR, "config", "ontology.json")
GITHUB_SOURCE_CONFIG_PATH = os.path.join(BASE_DIR, "config", "github_search_sources.json")
LLM_CACHE_PATH = os.path.join(BASE_DIR, "cache", "search_llm_cache.json")

BEIJING_TZ = timezone(timedelta(hours=8))
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

MAX_DOCS_PER_SOURCE = 18
DETAIL_FETCH_LIMIT_PER_SOURCE = 14
REQUEST_TIMEOUT = 16
MIN_STUDENT_SCORE = 0.55
GITHUB_TOKEN_ENV = "NJUPT_SEARCH_GITHUB_TOKEN"

def clean_env_value(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default)).strip().lstrip("\ufeff").strip()


GEMINI_API_KEYS = clean_env_value("GEMINI_API_KEYS") or clean_env_value("GEMINI_API_KEY")
DEEPSEEK_API_KEY = clean_env_value("DEEPSEEK_API_KEY")
DEEPSEEK_MODEL = clean_env_value("DEEPSEEK_MODEL", "deepseek-v4-flash")
DEEPSEEK_API_BASE = clean_env_value("DEEPSEEK_API_BASE", "https://api.deepseek.com").rstrip("/")
GITHUB_API_BASE = "https://api.github.com"
GITHUB_FILE_SIZE_LIMIT_BYTES = 250_000
JOB_API_BASE = "https://njupt.91job.org.cn/web/wsjysc/lbxq"
JOB_STATION_CODE = "10293"

ATTACHMENT_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".zip", ".rar",
}

STATIC_EXTENSIONS = {
    ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".mp4", ".mp3",
}

NAV_TITLES = {
    "首页", "学校首页", "联系我们", "设为首页", "加入收藏", "更多", "more",
    "通知公告", "新闻动态", "下载专区", "规章制度", "政策文件", "工作职能",
    "部门领导", "机构设置", "学生事务", "教师事务", "教学运行", "信息公开",
    "校历查询", "办事流程", "常用下载", "旧版回顾",
}

CATEGORY_KEYWORDS = {
    "考试": ["考试", "期末", "补考", "重修", "四六级", "考场", "准考证", "考试安排", "课程结束考试"],
    "选课": ["选课", "课程", "慕课", "教学安排", "培养方案", "成绩", "学籍", "校历", "转专业", "推免"],
    "竞赛": ["竞赛", "挑战杯", "互联网+", "大创", "创新创业", "创业", "科创", "iCAN", "校赛", "获奖"],
    "奖助": ["奖学金", "助学金", "资助", "困难认定", "评优", "公示", "助研", "助管", "助教"],
    "就业": ["就业", "招聘", "宣讲", "岗位", "实习", "双选会", "用人单位", "生源信息"],
    "讲座": ["讲座", "报告", "论坛", "学术", "活动预告", "沙龙", "培训"],
    "生活": ["宿舍", "返校", "离校", "医保", "体检", "停水", "停电", "交通", "消防", "户籍", "班车", "图书馆", "开放"],
    "学院": ["学院", "毕业设计", "答辩", "导师", "班级事务", "实验安排"],
    "研究生": ["研究生", "硕士", "博士", "学位", "答辩", "培养", "硕博连读", "研工"],
    "项目": ["项目", "课题", "基金", "申报", "科研", "成果转化", "专利"],
    "资料": ["资料", "下载", "手册", "指南", "流程", "表格"],
}

POSITIVE_KEYWORDS = [
    "考试", "选课", "课程", "成绩", "四六级", "重修", "补考", "转专业", "推免",
    "培养", "学位", "答辩", "毕业设计", "实习", "奖学金", "助学金", "困难认定",
    "评优", "公示", "宿舍", "返校", "离校", "医保", "体检", "停水", "停电",
    "交通管制", "讲座", "竞赛", "报名", "开放", "安排", "评选", "大创", "挑战杯",
    "互联网+", "校赛", "创新大赛", "创业基金", "社团", "志愿服务", "招聘", "宣讲会",
    "实习岗位",
]

NEGATIVE_KEYWORDS = [
    "党委理论学习", "巡察", "审计", "干部任免", "教职工", "职工", "离休人员",
    "离退休", "退休", "幼儿园", "会议纪要", "采购", "招标", "比选", "中标",
    "成交", "验收", "资产处置", "责任书签订", "签订仪式", "领导责任制",
    "党建研究", "行政统计", "工会活动",
]

@dataclass(frozen=True)
class SelectorConfig:
    list_item: str | None = None
    title: str | None = None
    date: str | None = None
    link: str | None = None
    content: str | None = None
    attachments: str | None = None


@dataclass(frozen=True)
class ChannelConfig:
    id: str
    source_id: str
    name: str
    list_urls: tuple[str, ...]
    student_value: float
    expected_domains: tuple[str, ...] = ()
    expected_intents: tuple[str, ...] = ()
    priority: float = 0.7
    crawl_depth: int = 1
    pagination_type: str = "none"
    pagination_pattern: str | None = None
    selectors: SelectorConfig = SelectorConfig()
    sensitive_risks: tuple[str, ...] = ()
    positive_keywords: tuple[str, ...] = ()
    negative_keywords: tuple[str, ...] = ()
    audit_status: str = "manual_seeded"
    production_enabled: bool = True
    notes: str = ""


@dataclass(frozen=True)
class SourceConfig:
    id: str
    name: str
    base_url: str
    list_urls: tuple[str, ...]
    audience: tuple[str, ...]
    source_weight: float
    source_type: str = "central_admin"
    adapter_kind: str = "njupt_wp"
    include_patterns: tuple[str, ...] = ()
    exclude_patterns: tuple[str, ...] = ()
    enabled: bool = True
    requires_devtools_audit: bool = False
    allow_insecure_tls: bool = False
    max_pages: int = 1
    notes: str = ""
    channels: tuple[ChannelConfig, ...] = ()

@dataclass(frozen=True)
class GitHubSourceConfig:
    repo: str
    label: str
    category: str
    audience: tuple[str, ...]
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    max_files: int
    source_weight: float
    enabled: bool

def _coerce_string_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _selector_config(value: object) -> SelectorConfig:
    if not isinstance(value, dict):
        return SelectorConfig()
    return SelectorConfig(
        list_item=str(value.get("list_item") or "").strip() or None,
        title=str(value.get("title") or "").strip() or None,
        date=str(value.get("date") or "").strip() or None,
        link=str(value.get("link") or "").strip() or None,
        content=str(value.get("content") or "").strip() or None,
        attachments=str(value.get("attachments") or "").strip() or None,
    )


def _read_source_channel_payload(path: str = SOURCE_CHANNEL_CONFIG_PATH) -> list[dict]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"source-channel graph is required: {path}")
    with open(path, "r", encoding="utf-8") as config_file:
        payload = json.load(config_file)
    raw_sources = payload.get("sources", []) if isinstance(payload, dict) else []
    sources = [item for item in raw_sources if isinstance(item, dict) and bool(item.get("enabled", True))]
    if not sources:
        raise ValueError(f"source-channel graph has no enabled sources: {path}")
    return sources


def _channel_configs_from_item(source_id: str, source_priority: float, raw_channels: object) -> tuple[ChannelConfig, ...]:
    channels: list[ChannelConfig] = []
    if not isinstance(raw_channels, list):
        return ()
    for raw in raw_channels:
        if not isinstance(raw, dict) or not bool(raw.get("production_enabled", True)):
            continue
        channel_id = str(raw.get("id", "")).strip()
        name = str(raw.get("name", "")).strip()
        list_urls = _coerce_string_tuple(raw.get("list_urls"))
        if not channel_id or not name or not list_urls:
            continue
        try:
            priority = max(0.05, min(1.0, float(raw.get("priority", source_priority))))
        except (TypeError, ValueError):
            priority = source_priority
        try:
            student_value = max(0.05, min(1.0, float(raw.get("student_value", priority))))
        except (TypeError, ValueError):
            student_value = priority
        pagination = raw.get("pagination") if isinstance(raw.get("pagination"), dict) else {}
        try:
            crawl_depth = max(1, min(int(raw.get("crawl_depth", 1)), 5))
        except (TypeError, ValueError):
            crawl_depth = 1
        channels.append(
            ChannelConfig(
                id=channel_id,
                source_id=str(raw.get("source_id") or source_id),
                name=name,
                list_urls=list_urls,
                student_value=student_value,
                expected_domains=_coerce_string_tuple(raw.get("expected_domains")),
                expected_intents=_coerce_string_tuple(raw.get("expected_intents")),
                priority=priority,
                crawl_depth=crawl_depth,
                pagination_type=str(pagination.get("type") or "none"),
                pagination_pattern=pagination.get("pattern"),
                selectors=_selector_config(raw.get("selectors")),
                sensitive_risks=_coerce_string_tuple(raw.get("sensitive_risks")),
                positive_keywords=_coerce_string_tuple(raw.get("positive_keywords")),
                negative_keywords=_coerce_string_tuple(raw.get("negative_keywords")),
                audit_status=str(raw.get("audit_status") or "manual_seeded"),
                production_enabled=True,
                notes=str(raw.get("notes") or "").strip(),
            )
        )
    return tuple(channels)


def read_source_channel_configs(path: str = SOURCE_CHANNEL_CONFIG_PATH) -> tuple[SourceConfig, ...]:
    channel_sources = _read_source_channel_payload(path)
    raw_sources = channel_sources

    sources: list[SourceConfig] = []
    for item in raw_sources:
        if not isinstance(item, dict) or not bool(item.get("enabled", True)):
            continue

        source_id = str(item.get("id", "")).strip()
        name = str(item.get("name", "")).strip()
        base_url = str(item.get("base_url", "")).strip()
        try:
            priority = float(item.get("authority", item.get("priority", item.get("source_weight", 0.72))))
        except (TypeError, ValueError):
            priority = 0.72

        channels = _channel_configs_from_item(source_id, priority, item.get("channels"))
        list_urls = tuple(dict.fromkeys(url for channel in channels for url in channel.list_urls))
        audience = _coerce_string_tuple(item.get("default_audience") or item.get("audience_hint") or item.get("audience"))
        if not source_id or not name or not base_url or not channels or not list_urls:
            continue

        try:
            max_pages = max(1, min(int(item.get("max_pages", max(channel.crawl_depth for channel in channels))), 5))
        except (TypeError, ValueError):
            max_pages = 1

        sources.append(
            SourceConfig(
                id=source_id,
                name=name,
                base_url=base_url,
                list_urls=list_urls,
                audience=audience or ("本科生", "研究生"),
                source_weight=max(0.05, min(1.0, priority)),
                source_type=str(item.get("source_type") or "central_admin").strip(),
                adapter_kind=str(item.get("adapter_kind") or "njupt_wp").strip(),
                include_patterns=_coerce_string_tuple(item.get("include_patterns")),
                exclude_patterns=_coerce_string_tuple(item.get("exclude_patterns")),
                enabled=True,
                requires_devtools_audit=bool(item.get("requires_devtools_audit", False)),
                allow_insecure_tls=bool(item.get("allow_insecure_tls", False)),
                max_pages=max_pages,
                notes=str(item.get("notes") or "").strip(),
                channels=channels,
            )
        )

    if not sources:
        raise ValueError(f"no valid source-channel sources loaded from {path}")
    return tuple(sources)


SOURCES: tuple[SourceConfig, ...] = read_source_channel_configs()
