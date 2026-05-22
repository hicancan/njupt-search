import os
from dataclasses import dataclass
from datetime import timezone, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")
INDEX_DIR = os.path.join(PUBLIC_DIR, "index")
DOCUMENTS_PATH = os.path.join(INDEX_DIR, "documents.json")
MANIFEST_PATH = os.path.join(INDEX_DIR, "manifest.json")
GITHUB_SOURCE_CONFIG_PATH = os.path.join(BASE_DIR, "config", "github_search_sources.json")

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
GITHUB_API_BASE = "https://api.github.com"
GITHUB_FILE_SIZE_LIMIT_BYTES = 250_000

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
class SourceConfig:
    id: str
    name: str
    base_url: str
    list_urls: tuple[str, ...]
    audience: tuple[str, ...]
    source_weight: float

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

SOURCES: tuple[SourceConfig, ...] = (
    SourceConfig("jwc", "本科生院 / 教务处", "https://jwc.njupt.edu.cn/", ("https://jwc.njupt.edu.cn/1594/list.htm",), ("本科生",), 1.0),
    SourceConfig("xsc", "学生工作处", "https://xsc.njupt.edu.cn/", ("https://xsc.njupt.edu.cn/",), ("本科生",), 0.96),
    SourceConfig("pg", "研究生院", "https://pg.njupt.edu.cn/", ("https://pg.njupt.edu.cn/",), ("研究生",), 0.96),
    SourceConfig("ygb", "研究生工作部", "https://ygb.njupt.edu.cn/", ("https://ygb.njupt.edu.cn/",), ("研究生",), 0.92),
    SourceConfig("youth", "团委 / 青春南邮", "https://youth.njupt.edu.cn/", ("https://youth.njupt.edu.cn/",), ("本科生", "研究生"), 0.9),
    SourceConfig("cxcy", "创新创业教育学院", "https://cxcy.njupt.edu.cn/", ("https://cxcy.njupt.edu.cn/",), ("本科生", "研究生"), 0.9),
    SourceConfig("job", "就业信息网", "https://njupt.91job.org.cn/", ("https://njupt.91job.org.cn/",), ("本科生", "研究生"), 0.88),
    SourceConfig("lib", "图书馆", "https://lib.njupt.edu.cn/", ("https://lib.njupt.edu.cn/",), ("本科生", "研究生", "教职工"), 0.82),
    SourceConfig("bwc", "保卫处", "https://bwc.njupt.edu.cn/", ("https://bwc.njupt.edu.cn/",), ("本科生", "研究生", "教职工"), 0.8),
    SourceConfig("hqc", "后勤管理处", "https://hqc.njupt.edu.cn/", ("https://hqc.njupt.edu.cn/",), ("本科生", "研究生", "教职工"), 0.8),
)
