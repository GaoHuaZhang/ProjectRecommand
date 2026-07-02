"""课题推荐 Agent —— 命令行入口。

用法：
  python main.py                      # 全量运行，走 config/.env
  python main.py --dry-run            # 只读表校验，不调模型（省 token）
  python main.py --limit 1            # 只处理前 1 位同学（联调用）
  python main.py --top-n 5            # 覆盖每人推荐数量
  python main.py --students a.xlsx --topics b.xlsx
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from src.config import ConfigError, load_config
from src.excel_reader import ExcelReadError, read_students, read_topics
from src.llm_client import LLMClient
from src.recommender import Recommender
from src.report_writer import write_markdown, write_xlsx

console = Console()


def parse_args():
    p = argparse.ArgumentParser(description="课题推荐 Agent")
    p.add_argument("--students", type=Path, help="同学评价 xlsx 路径（覆盖 .env）")
    p.add_argument("--topics", type=Path, help="课题清单 xlsx 路径（覆盖 .env）")
    p.add_argument("--top-n", type=int, help="每位同学推荐课题数（覆盖 .env）")
    p.add_argument("--limit", type=int, help="只处理前 N 位同学（联调用）")
    p.add_argument("--dry-run", action="store_true", help="只读表校验，不调用模型")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    # 1. 配置（dry-run 时允许无 LLM 配置，只需文件路径）
    try:
        cfg = load_config()
    except ConfigError as e:
        if args.dry_run:
            # dry-run 用默认路径即可继续
            from src.config import Config, ROOT

            cfg = Config(
                base_url="", api_key="", model="",
                students_xlsx=(args.students or ROOT / "data/students.xlsx"),
                topics_xlsx=(args.topics or ROOT / "data/topics.xlsx"),
                output_dir=ROOT / "output", top_n=3, temperature=0.2,
                timeout=60, max_retries=3,
            )
        else:
            console.print(f"[red]配置错误：[/red]{e}")
            return 1

    students_path = args.students or cfg.students_xlsx
    topics_path = args.topics or cfg.topics_xlsx
    top_n = args.top_n or cfg.top_n
    cfg.top_n = top_n

    # 2. 读表
    try:
        students = read_students(students_path)
        topics = read_topics(topics_path)
    except ExcelReadError as e:
        console.print(f"[red]读表失败：[/red]{e}")
        return 1

    console.print(f"[green]✓[/green] 读取同学 {len(students)} 人，课题 {len(topics)} 个。")

    if args.limit:
        students = students[: args.limit]
        console.print(f"[yellow]--limit 生效，仅处理前 {len(students)} 人。[/yellow]")

    if args.dry_run:
        _print_dry_run(students, topics)
        console.print("\n[green]dry-run 完成。[/green]列名解析正确后，去掉 --dry-run 即可正式运行。")
        return 0

    # 3. 推荐
    client = LLMClient(cfg)
    rec = Recommender(cfg, client, topics)

    console.print(f"\n开始推荐（模型 {cfg.model}，每人 Top{top_n}）...")
    results = []
    with console.status("[bold green]调用模型中...") as status:
        for i, s in enumerate(students, start=1):
            status.update(f"[bold green]({i}/{len(students)}) 正在推荐：{s.name}")
            results.append(rec.recommend_one(s))

    # 4. 打印
    _print_results(results)

    # 5. 报告
    md_path = write_markdown(results, cfg.output_dir)
    xlsx_path = write_xlsx(results, cfg.output_dir)
    console.print(f"\n[green]✓ 报告已生成：[/green]")
    console.print(f"  Markdown: {md_path}")
    console.print(f"  Excel:    {xlsx_path}")

    failed = [r for r in results if r.error]
    if failed:
        console.print(f"[yellow]⚠ {len(failed)} 人推荐失败，需人工复核（见报告）。[/yellow]")
    return 0


def _print_dry_run(students, topics):
    t = Table(title="同学（前 5 条预览）")
    t.add_column("姓名"); t.add_column("投递岗位"); t.add_column("专业面试意见")
    for s in students[:5]:
        review = s.professional_review or s.overall_review
        ev = review[:40] + ("…" if len(review) > 40 else "")
        t.add_row(s.name, s.position or "-", ev)
    console.print(t)

    t2 = Table(title="课题（前 5 条预览）")
    t2.add_column("编号"); t2.add_column("课题"); t2.add_column("目标/描述")
    for tp in topics[:5]:
        summary = tp.objective or tp.background or tp.content or tp.description
        desc = summary[:40] + ("…" if len(summary) > 40 else "")
        t2.add_row(tp.topic_id, tp.name, desc)
    console.print(t2)


def _print_results(results):
    for r in results:
        console.print(f"\n[bold cyan]{r.student.name}[/bold cyan]（{r.student.position or '未填岗位'}）")
        if r.error:
            console.print(f"  [red]推荐失败：{r.error}[/red]")
            continue
        t = Table(show_header=True, header_style="bold")
        t.add_column("排名", width=4); t.add_column("课题")
        t.add_column("匹配度", width=6); t.add_column("理由")
        for rank, item in enumerate(r.items, start=1):
            t.add_row(str(rank), f"[{item.topic_id}] {item.topic_name}",
                      f"{item.score:.0f}", item.reason)
        console.print(t)


if __name__ == "__main__":
    sys.exit(main())
