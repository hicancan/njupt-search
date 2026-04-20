# 📊 Data Inventory & Quality Report

> **Generated on:** 2026-04-20 21:12:11 (Beijing Time)
>
> This report provides complete visibility into raw Excel data and processing results.
> You do NOT need to open the original Excel files - all information is captured here.

## 📋 Executive Summary

| Metric | Value |
|--------|-------|
| Total Files Processed | 2 |
| Total Records Extracted | 344 |
| Parse Success Rate | 344/344 (100.0%) |
| Date Range (All Files) | 2026-04-27 ~ 2026-05-27 |
| Unique Classes | ~280 |
| Unique Courses | ~19 |
| Campus Distribution | 仙林 (300), 三牌楼 (35), 锁金 (9) |

---

## ✅ File: `2025-2026学年第二学期考试安排表（学院组织）-学生用表.xlsx`

**Rows:** 93 | **Columns:** 9 | **Parse Success:** 93/93 | **Date Range:** 2026-04-27 ~ 2026-05-27

### 🔹 Part A: Raw Excel Analysis

#### Original Column Names (as in Excel)

| # | Excel Column Name | Data Type | Non-Null % | Unique Values | Sample Values |
|---|-------------------|-----------|------------|---------------|---------------|
| 1 | `校区` | object | 100.0% | 2 | 仙林, 三牌楼 |
| 2 | `开课学院` | object | 100.0% | 5 | 电子与光学工程学院, 管理学院, 自动化学院 |
| 3 | `课程代码` | object | 100.0% | 17 | DG1113F4S, DG1219F4S, GL1516GLS |
| 4 | `课程名称` | object | 100.0% | 16 | 光电子学（全英文）, 电波传播理论, 企业资源规划系统与应用(混合式) |
| 5 | `班级名称` | object | 100.0% | 75 | B230200, B230205, B220204 |
| 6 | `任课教师` | object | 100.0% | 19 | 郭艳东/曾红丽, 智婷/汪金, 笪海霞 |
| 7 | `人数` | int64 | 100.0% | 27 | 28, 2, 1 |
| 8 | `考试时间` | object | 100.0% | 12 | 第11周周3(2026-05-13) 13:30-15:20, 第11周周2(2026-05-12) |
| 9 | `考试教室` | object | 100.0% | 18 | 教2－101, 教2－102, 教2－201 |

#### Column Mapping (Excel → Standard Field)

| Standard Field | Excel Column | Status |
|----------------|--------------|--------|
| `campus` | `校区` | ✅ Mapped |
| `course_name` | `课程名称` | ✅ Mapped |
| `course_code` | `课程代码` | ✅ Mapped |
| `class_name` | `班级名称` | ✅ Mapped |
| `teacher` | `任课教师` | ✅ Mapped |
| `location` | `考试教室` | ✅ Mapped |
| `raw_time` | `考试时间` | ✅ Mapped |
| `count` | `人数` | ✅ Mapped |
| `school` | `开课学院` | ✅ Mapped |
| `student_school` | _(tried: 学生所在学院, 所在学院)_ | ❌ Not Found |
| `major` | _(tried: 专业名称, 专业)_ | ❌ Not Found |
| `grade` | _(tried: 年级)_ | ❌ Not Found |
| `notes` | _(tried: 备注)_ | ❌ Not Found |

#### Raw Data Sample (First 3 Rows, Unprocessed)

| 校区 | 开课学院 | 课程代码 | 课程名称 | 班级名称 | 任课教师 | 人数 | 考试时间 | 考试教室 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 仙林 | 电子与光学工程学院 | DG1113F4S | 光电子学（全英文） | B230200 | 郭艳东/曾红丽 | 28 | 第11周周3(2026-05-13) 1 | 教2－101 |
| 仙林 | 电子与光学工程学院 | DG1113F4S | 光电子学（全英文） | B230205 | 郭艳东/曾红丽 | 2 | 第11周周3(2026-05-13) 1 | 教2－101 |
| 仙林 | 电子与光学工程学院 | DG1113F4S | 光电子学（全英文） | B220204 | 智婷/汪金 | 2 | 第11周周3(2026-05-13) 1 | 教2－101 |

### 🔹 Part B: Processing Results

#### Processing Statistics

| Metric | Value |
|--------|-------|
| Records Processed | 93 |
| Time Parse Success | 93 |
| Time Parse Failed | 0 |
| Unique Classes | 75 |
| Unique Courses | 16 |
| Avg Exam Duration | 110.0 min |
| Campus Distribution | 仙林 (86), 三牌楼 (7) |

#### ✅ Validation: All Passed

#### Processed Data Sample (First 3 Rows)

| class_name | course_name | campus | start_timestamp | location | teacher | count |
| --- | --- | --- | --- | --- | --- | --- |
| B230200 | 光电子学（全英文） | 仙林 | 2026-05-13T13:30:00+08:00 | 教2－101 | 郭艳东/曾红丽 | 28 |
| B230205 | 光电子学（全英文） | 仙林 | 2026-05-13T13:30:00+08:00 | 教2－101 | 郭艳东/曾红丽 | 2 |
| B220204 | 光电子学（全英文） | 仙林 | 2026-05-13T13:30:00+08:00 | 教2－101 | 智婷/汪金 | 2 |

---

## ✅ File: `2025-2026学年第二学期集中考试周1安排表（学校组织）-学生用表.xlsx`

**Rows:** 251 | **Columns:** 12 | **Parse Success:** 251/251 | **Date Range:** 2026-04-29 ~ 2026-05-23

### 🔹 Part A: Raw Excel Analysis

#### Original Column Names (as in Excel)

| # | Excel Column Name | Data Type | Non-Null % | Unique Values | Sample Values |
|---|-------------------|-----------|------------|---------------|---------------|
| 1 | `校区` | object | 100.0% | 3 | 锁金, 三牌楼, 仙林 |
| 2 | `开课学院` | object | 100.0% | 3 | 通信与信息工程学院, 马克思主义学院, 电子与光学工程学院 |
| 3 | `课程代码` | object | 100.0% | 4 | TX5262YYS, MY1002T0S, MY3002T0S |
| 4 | `课程名称` | object | 100.0% | 3 | 模式识别基础, 毛泽东思想和中国特色社会主义理论体系概论, 工程管理与经济决策 |
| 5 | `班级名称` | object | 100.0% | 205 | B221803, B221805, B221807 |
| 6 | `任课教师` | object | 100.0% | 20 | 谭智一/傅杰, 周静/韩芬, 王义 |
| 7 | `人数` | int64 | 100.0% | 27 | 1, 2, 37 |
| 8 | `考试时间` | object | 100.0% | 3 | 2026年04月29日(13:30-15:20), 2026年05月20日(13:30-15:20) |
| 9 | `教室名称` | object | 100.0% | 43 | 锁金－604, 锁金－100, 无1 |
| 10 | `学生所在学院` | object | 100.0% | 18 | 应用技术学院, 通信与信息工程学院, 自动化学院 |
| 11 | `年级` | int64 | 100.0% | 3 | 2022, 2023, 2024 |
| 12 | `专业名称` | object | 100.0% | 59 | 信息工程（专转本）, 通信工程, 电子信息工程 |

#### Column Mapping (Excel → Standard Field)

| Standard Field | Excel Column | Status |
|----------------|--------------|--------|
| `campus` | `校区` | ✅ Mapped |
| `course_name` | `课程名称` | ✅ Mapped |
| `course_code` | `课程代码` | ✅ Mapped |
| `class_name` | `班级名称` | ✅ Mapped |
| `teacher` | `任课教师` | ✅ Mapped |
| `location` | `教室名称` | ✅ Mapped |
| `raw_time` | `考试时间` | ✅ Mapped |
| `count` | `人数` | ✅ Mapped |
| `school` | `开课学院` | ✅ Mapped |
| `student_school` | `学生所在学院` | ✅ Mapped |
| `major` | `专业名称` | ✅ Mapped |
| `grade` | `年级` | ✅ Mapped |
| `notes` | _(tried: 备注)_ | ❌ Not Found |

#### Raw Data Sample (First 3 Rows, Unprocessed)

| 校区 | 开课学院 | 课程代码 | 课程名称 | 班级名称 | 任课教师 | 人数 | 考试时间 | 教室名称 | 学生所在学院 | 年级 | 专业名称 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 锁金 | 通信与信息工程学院 | TX5262YYS | 模式识别基础 | B221803 | 谭智一/傅杰 | 1 | 2026年04月29日(13:30-15 | 锁金－604 | 应用技术学院 | 2022 | 信息工程（专转本） |
| 锁金 | 通信与信息工程学院 | TX5262YYS | 模式识别基础 | B221805 | 谭智一/傅杰 | 2 | 2026年04月29日(13:30-15 | 锁金－604 | 应用技术学院 | 2022 | 信息工程（专转本） |
| 锁金 | 通信与信息工程学院 | TX5262YYS | 模式识别基础 | B221807 | 谭智一/傅杰 | 1 | 2026年04月29日(13:30-15 | 锁金－604 | 应用技术学院 | 2022 | 信息工程（专转本） |

### 🔹 Part B: Processing Results

#### Processing Statistics

| Metric | Value |
|--------|-------|
| Records Processed | 251 |
| Time Parse Success | 251 |
| Time Parse Failed | 0 |
| Unique Classes | 205 |
| Unique Courses | 3 |
| Avg Exam Duration | 110.0 min |
| Campus Distribution | 锁金 (9), 三牌楼 (28), 仙林 (214) |

#### ✅ Validation: All Passed

#### Processed Data Sample (First 3 Rows)

| class_name | course_name | campus | start_timestamp | location | teacher | count |
| --- | --- | --- | --- | --- | --- | --- |
| B221803 | 模式识别基础 | 锁金 | 2026-04-29T13:30:00+08:00 | 锁金－604 | 谭智一/傅杰 | 1 |
| B221805 | 模式识别基础 | 锁金 | 2026-04-29T13:30:00+08:00 | 锁金－604 | 谭智一/傅杰 | 2 |
| B221807 | 模式识别基础 | 锁金 | 2026-04-29T13:30:00+08:00 | 锁金－604 | 谭智一/傅杰 | 1 |

---

## 📚 Appendix

### A. Field Mapping Reference

The following table shows how Excel column names are mapped to standard field names:

| Standard Field | Possible Excel Column Names |
|----------------|----------------------------|
| `campus` | 校区, 校区名称 |
| `course_name` | 课程名称, 课程, 考试课程 |
| `course_code` | 课程代码, 选课课号 |
| `class_name` | 班级名称, 班级, 班级代码, 行政班级 |
| `teacher` | 任课教师, 教师, 监考教师 |
| `location` | 考试教室, 教室名称, 地点, 考试地点 |
| `raw_time` | 考试时间, 时间 |
| `count` | 人数, 学生人数, 考试人数 |
| `school` | 开课学院, 学院 |
| `student_school` | 学生所在学院, 所在学院 |
| `major` | 专业名称, 专业 |
| `grade` | 年级 |
| `notes` | 备注 |

### B. Supported Time Formats

The system can parse the following time formats:

| Format | Example | Regex Pattern |
|--------|---------|---------------|
| Chinese Date | `2025年11月15日(10:25-12:15)` | `(\d{4})年(\d{1,2})月(\d{1,2})日.*?(\d{1,2}:\d{2})\s*[-~至]\s*(\d{1,2}:\d{2})` |
| ISO Date | `第11周周2(2025-11-18) 13:30-15:20` | `\(?(\d{4}-\d{1,2}-\d{1,2})\)?.*?(\d{1,2}:\d{2})\s*[-~至]\s*(\d{1,2}:\d{2})` |

### C. Output JSON Fields

The processed `all_exams.json` contains these fields per record:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier (filename-row) |
| `class_name` | string | Class identifier (e.g., B240402) |
| `course_name` | string | Course name |
| `course_code` | string | Course code |
| `campus` | string | Campus name |
| `teacher` | string | Teacher name |
| `location` | string | Exam location |
| `raw_time` | string | Original time string from Excel |
| `start_timestamp` | string | Parsed ISO datetime |
| `end_timestamp` | string | Parsed ISO datetime |
| `duration_minutes` | integer | Exam duration in minutes |
| `count` | integer | Number of students |
| `notes` | string | Additional notes |

---

*End of Report*