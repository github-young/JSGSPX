"""
批量提取根目录下 Ch1.html、Ch2.html ... 各章节练习 HTML 中的题目，
导出全部题目 + 错题，输出文件名沿用 Ch 后的数字。

用法：
    uv run --with beautifulsoup4 python extract_questions.py
    uv run --with beautifulsoup4 python extract_questions.py --merged

目录约定：
    根目录/
      extract_questions.py
      Ch1.html
      Ch2.html
      ...
      Ch7.html
      output/               <- 脚本自动创建
        Ch1.txt
        Ch1_错题.txt
        Ch1.csv
        ...
        Ch1_全部题目.txt / Ch1_错题汇总.txt  # 本章（可能多文件）合并
        (--merged 时)
        全部章节_全部题目.txt
        全部章节_全部题目.csv
        全部章节_错题汇总.txt
"""

import sys
import csv
import re
import argparse
from pathlib import Path

from bs4 import BeautifulSoup


# --------------------------------------------------------------------------- #
# 解析
# --------------------------------------------------------------------------- #
def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def parse_questions(html: str):
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select(".test_content_nr > ul > li")
    questions = []

    for idx, li in enumerate(items, 1):
        stem_tag = li.select_one(".test_content_nr_tt font")
        stem = clean(stem_tag.get_text(" ", strip=True)) if stem_tag else ""

        options, chosen, chosen_letter, is_wrong = [], "", "", False
        for opt_li in li.select(".test_content_nr_main > ul > li.option"):
            label = opt_li.select_one("label")
            if not label:
                continue
            opt_text = clean(label.get_text(" ", strip=True))
            options.append(opt_text)

            m = re.match(r"([A-Z])[\.．、]", opt_text)
            letter = m.group(1) if m else ""

            radio = opt_li.select_one('input[type="radio"]')
            is_checked = bool(radio and radio.has_attr("checked"))

            if "errorBeenAnswer" in (opt_li.get("class") or []):
                is_wrong = True
                chosen, chosen_letter = opt_text, letter
            elif is_checked:
                chosen, chosen_letter = opt_text, letter

        ans_tag = li.select_one('label[for$="_Answer"] p')
        answer = clean(ans_tag.get_text(strip=True)) if ans_tag else ""

        if chosen_letter and answer and chosen_letter != answer:
            is_wrong = True

        kp_tag = li.select_one('label[for$="_KnowledgePoint"] p')
        knowledge = clean(kp_tag.get_text(strip=True)) if kp_tag else ""

        questions.append({
            "index": idx,
            "stem": stem,
            "options": options,
            "answer": answer,
            "knowledge": knowledge,
            "chosen": chosen,
            "is_wrong": is_wrong,
        })
    return questions


# --------------------------------------------------------------------------- #
# 输出格式
# --------------------------------------------------------------------------- #
def format_question(q, show_chosen=False, prefix="") -> str:
    lines = [f"{prefix}第{q['index']}题：{q['stem']}"]
    for opt in q["options"]:
        lines.append(f"  {opt}")
    if show_chosen and q["chosen"]:
        lines.append(f"  你的选择：{q['chosen']}")
    lines.append(f"  正确答案：{q['answer']}")
    if q["knowledge"]:
        lines.append(f"  知识点：{q['knowledge']}")
    return "\n".join(lines)


def to_txt(questions) -> str:
    if not questions:
        return "没有题目。\n"
    return "\n\n".join(format_question(q) for q in questions) + "\n"


def to_wrong_txt(questions, title="错题集") -> str:
    wrong = [q for q in questions if q["is_wrong"]]
    if not wrong:
        return f"{title}：本次没有错题。\n"
    header = f"{title}（共 {len(wrong)} 题）\n" + "=" * 40 + "\n\n"
    body = "\n\n".join(format_question(q, show_chosen=True) for q in wrong)
    return header + body + "\n"


def to_csv(questions, path: Path):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["序号", "题干", "选项A", "选项B", "选项C", "选项D",
             "你的选择", "正确答案", "是否答错", "知识点"]
        )
        for q in questions:
            opts = q["options"] + [""] * (4 - len(q["options"]))
            writer.writerow([
                q["index"], q["stem"], *opts[:4],
                q["chosen"], q["answer"],
                "是" if q["is_wrong"] else "",
                q["knowledge"],
            ])


# --------------------------------------------------------------------------- #
# 批量处理
# --------------------------------------------------------------------------- #
def find_chapter_files(root: Path):
    """找出根目录下形如 Ch1.html / ch2.htm 的文件，按数字排序。"""
    pattern = re.compile(r"^(ch|chapter)\s*(\d+)\.(html?)$", re.IGNORECASE)
    files = []
    for p in root.iterdir():
        if not p.is_file():
            continue
        m = pattern.match(p.name)
        if m:
            files.append((int(m.group(2)), p))
    files.sort(key=lambda x: x[0])
    return files


def chapter_label(num: int) -> str:
    """统一输出名：Ch + 数字，例如 Ch1、Ch7。"""
    return f"Ch{num}"


def process_file(num: int, html_file: Path, out_root: Path, merged_all, merged_wrong):
    label = chapter_label(num)
    try:
        html = html_file.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        html = html_file.read_text(encoding="gb18030", errors="replace")

    qs = parse_questions(html)
    wrong = [q for q in qs if q["is_wrong"]]
    print(f"  {html_file.name} -> {label}: {len(qs)} 题，错 {len(wrong)} 题")

    # 全部题目 txt
    (out_root / f"{label}.txt").write_text(to_txt(qs), encoding="utf-8")
    # 错题 txt
    (out_root / f"{label}_错题.txt").write_text(
        to_wrong_txt(qs, f"{label} 错题集"), encoding="utf-8"
    )
    # 全部题目 csv
    to_csv(qs, out_root / f"{label}.csv")

    # 记录到合并列表
    for q in qs:
        qq = dict(q)
        qq["source"] = label
        merged_all.append(qq)
    for q in wrong:
        qq = dict(q)
        qq["source"] = label
        merged_wrong.append(qq)

    return len(qs), len(wrong)


def main():
    parser = argparse.ArgumentParser(description="批量提取 ChN.html 中的题目")
    parser.add_argument("-r", "--root", default=".", help="根目录，默认当前目录")
    parser.add_argument("-o", "--out", default="output", help="输出目录名，默认 output")
    parser.add_argument("--merged", action="store_true", help="额外生成跨章节汇总文件")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    out_root = root / args.out
    out_root.mkdir(parents=True, exist_ok=True)

    chapter_files = find_chapter_files(root)
    if not chapter_files:
        print(f"在 {root} 下没有找到 Ch1.html / Ch2.html 这类文件")
        sys.exit(1)

    print(f"找到 {len(chapter_files)} 个章节文件：{[p.name for _, p in chapter_files]}")
    print(f"输出目录：{out_root}\n")

    merged_all, merged_wrong = [], []
    total_q = total_w = 0
    for num, html_file in chapter_files:
        nq, nw = process_file(num, html_file, out_root, merged_all, merged_wrong)
        total_q += nq
        total_w += nw

    if args.merged and merged_all:
        for i, q in enumerate(merged_all, 1):
            q["index"] = i
        (out_root / "全部章节_全部题目.txt").write_text(to_txt(merged_all), encoding="utf-8")
        to_csv(merged_all, out_root / "全部章节_全部题目.csv")

        if merged_wrong:
            for i, q in enumerate(merged_wrong, 1):
                q["index"] = i
            (out_root / "全部章节_错题汇总.txt").write_text(
                to_wrong_txt(merged_wrong, "全部章节错题汇总"), encoding="utf-8"
            )
        print(f"\n已生成跨章节汇总（全部 {len(merged_all)} 题，错题 {len(merged_wrong)} 题）")

    print("=" * 40)
    print(f"完成：共 {total_q} 题，错题 {total_w} 题")
    print(f"输出目录：{out_root}")


if __name__ == "__main__":
    main()