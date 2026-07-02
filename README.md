# 课题推荐 Agent

根据同学的**面试评价**和**投递岗位**，从**课题清单**中用大模型为每人推荐最匹配的 Top N 个课题，
给出匹配度与中文理由，输出到命令行并生成 Markdown + Excel 报告。

## 特性

- 读取本地 xlsx（同学评价表 + 课题清单表），列名**模糊匹配**，无需固定表头顺序。
- 大模型走 **OpenAI 兼容接口**，支持内网私有网关（自定义 `base_url` + `api_key`）。
- 模型返回**结构化 JSON**并做校验：过滤编造的课题、按匹配度排序、截断到 Top N。
- 单个同学调用失败不中断整体，记入报告"待人工复核"。
- `--dry-run` 先校验读表（不花 token），`--limit N` 只跑前 N 人联调。

## 安装

```bash
python3 -m pip install -r requirements.txt
```

## 配置

复制配置模板并填写内网模型信息：

```bash
cp config/.env.example config/.env
# 编辑 config/.env，填 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL
```

| 变量             | 说明                                                   |
| ---------------- | ------------------------------------------------------ |
| `LLM_BASE_URL` | 内网网关地址，OpenAI 兼容，形如`http://host:port/v1` |
| `LLM_API_KEY`  | 网关密钥                                               |
| `LLM_MODEL`    | 模型名                                                 |
| `TOP_N`        | 每人推荐数（默认 3）                                   |
| `TEMPERATURE`  | 采样温度（默认 0.2，越低越稳定）                       |

## 准备数据

把两张表放到 `data/`（列名支持中英文别名，见下）：

**students.xlsx**（同学面试评价）

- 姓名 *(必需)*：姓名 / name / 同学 …
- 投递岗位 *(可选)*：岗位 / 应聘岗位 / position …
- 面试评价 *(必需)*：评价 / 面评 / 评语 …
- 其余列会原样附加给模型作为参考。

**topics.xlsx**（课题清单）

- 课题名称 *(必需)*：课题 / 题目 / topic …
- 编号 *(可选)*：无则自动生成 T1、T2…
- 其余列（方向 / 技能 / 导师 / 名额…）会拼成课题描述喂给模型。

没有真实数据时，可先生成示例：

```bash
python3 scripts/make_sample_data.py
```

## 运行

```bash
# 1) 先校验读表是否正确（不调模型）
python3 main.py --dry-run

# 2) 只跑 1 人，验证 API 连通 + 报告生成
python3 main.py --limit 1

# 3) 全量运行
python3 main.py
```

结果打印在命令行，并在 `output/` 生成带时间戳的 `recommendations_*.md` 和 `recommendations_*.xlsx`。
Excel 每行一条推荐，便于回粘到在线表格。

### 常用参数

| 参数                                    | 说明                   |
| --------------------------------------- | ---------------------- |
| `--dry-run`                           | 只读表校验，不调用模型 |
| `--limit N`                           | 只处理前 N 位同学      |
| `--top-n N`                           | 覆盖每人推荐数量       |
| `--students PATH` / `--topics PATH` | 覆盖 .env 里的文件路径 |

## 目录结构

```
config/.env.example   配置模板
data/                 输入 xlsx（自备或用脚本生成）
output/               生成的报告
scripts/make_sample_data.py  示例数据生成
src/
  config.py           配置加载
  models.py           数据模型
  excel_reader.py     读表 + 列名映射
  llm_client.py       OpenAI 兼容客户端（重试 + JSON 降级）
  recommender.py      核心推荐 + JSON 校验
  report_writer.py    Markdown / Excel 报告
main.py               CLI 入口
```

## 说明与后续扩展

- 当前把**全部课题清单**塞进 prompt。课题非常多（上百）导致超长时，可加"粗筛→精排"两段式。
- 数据源目前为本地 xlsx；后续可扩展飞书多维表格 / 腾讯文档在线读取与写回。
- 目前串行调用，`recommender.py` 已预留并发入口，可用线程池提速。
