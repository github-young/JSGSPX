"""
把 output/ChN.txt 转换成 Typst 文件（.typ）。

用法：
    uv run --with typst python txt_to_typst.py            # 处理 output 下所有 ChN.txt
    uv run --with typst python txt_to_typst.py Ch1.txt    # 只处理指定文件
    uv run --with typst python txt_to_typst.py -d output  # 指定目录

输入 txt 格式（由 extract_questions.py 生成）：
    第1题：题干……
      A. 选项
      B. 选项
      C. 选项
      D. 选项
      正确答案：A
      知识点：第x章……
    （空行分隔）

输出：
    output/Ch1.typ
"""

import re
import sys
import argparse
from pathlib import Path


# --------------------------------------------------------------------------- #
# 解析 txt
# --------------------------------------------------------------------------- #
QUESTION_RE = re.compile(r"^第(\d+)题：(.*)$")
OPTION_RE = re.compile(r"^\s+([A-Z])[\.．、]\s*(.*)$")
ANSWER_RE = re.compile(r"^\s*正确答案：(.*)$")
KNOWLEDGE_RE = re.compile(r"^\s*知识点：(.*)$")
CHOSEN_RE = re.compile(r"^\s*你的选择：(.*)$")


def parse_txt(text: str):
    """把 txt 解析成题目列表。"""
    questions = []
    cur = None

    for raw in text.splitlines():
        line = raw.rstrip()

        m = QUESTION_RE.match(line)
        if m:
            if cur:
                questions.append(cur)
            cur = {
                "index": int(m.group(1)),
                "stem": m.group(2).strip(),
                "options": [],       # [(letter, text), ...]
                "answer": "",
                "knowledge": "",
                "chosen": "",
            }
            continue

        if cur is None:
            continue

        m = OPTION_RE.match(line)
        if m:
            cur["options"].append((m.group(1), m.group(2).strip()))
            continue

        m = ANSWER_RE.match(line)
        if m:
            cur["answer"] = m.group(1).strip()
            continue

        m = KNOWLEDGE_RE.match(line)
        if m:
            cur["knowledge"] = m.group(1).strip()
            continue

        m = CHOSEN_RE.match(line)
        if m:
            cur["chosen"] = m.group(1).strip()
            continue

        # 续行（题干太长被折行的情况）
        if line.strip():
            if not cur["options"] and not cur["answer"]:
                cur["stem"] += " " + line.strip()

    if cur:
        questions.append(cur)
    return questions


# --------------------------------------------------------------------------- #
# Typst 转义
# --------------------------------------------------------------------------- #
TYPST_SPECIAL = {
    "\\": "\\\\",
    "#": "\\#",
    "$": "\\$",
    "*": "\\*",
    "_": "\\_",
    "`": "\\`",
    "<": "\\<",
    ">": "\\>",
    "@": "\\@",
    "~": "\\~",
    "-": "\\-",
}


def esc(text: str) -> str:
    """转义 Typst 特殊字符。"""
    return "".join(TYPST_SPECIAL.get(ch, ch) for ch in text)


def q(text: str) -> str:
    """简单包裹成 Typst 字符串字面量（用于元数据/答案）。"""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


# --------------------------------------------------------------------------- #
# 生成 Typst
# --------------------------------------------------------------------------- #
TYPST_HEADER = """\
// 由 txt_to_typst.py 自动生成
#set page(
  paper: "a4",
  margin: (x: 2cm, y: 2cm),
  numbering: "1",
)
#set text(font: ("Source Han Sans SC", "Noto Serif SC", "Source Han Serif SC", "SimSun"), size: 11pt)
#set par(justify: true, leading: 0.9em)
#set heading(numbering: "1.")

#let answer-color = rgb("#1a6fd4")   // 正确选项蓝色
#let wrong-color  = rgb("#d40000")   // 错题题号红色
#let meta-color   = rgb("#666666")
#let stem-weight  = 600

// 题目块：is-wrong 为 true 时题号红色加粗
#let question-block(idx, stem, options, answer, knowledge, is-wrong: false) = {
  block(breakable: true, below: 1.2em)[
    #if is-wrong [
      #text(weight: "bold", fill: wrong-color)[★#idx.]
    ] else [
      #text(weight: stem-weight)[#idx.]
    ]
    #h(0.4em) #text(weight: stem-weight)[#stem] \\
    #if options.len() == 0 [
      #h(1.5em) A. 对 #h(2em) B. 错 \\
    ] else [
      #for (letter, opt_text) in options [
        #h(1.5em)
        #if letter == answer [
          #text(fill: answer-color, weight: "bold")[#letter. #opt_text]
        ] else [
          #letter. #opt_text
        ]
        \\
      ]
    ]
    #v(0.3em)
    #text(size: 9.5pt, fill: meta-color)[
      正确答案：*#answer* #if knowledge != "" [#h(1em) | #h(1em) #knowledge]
    ]
  ]
}
"""


def load_wrong_indices(txt_path: Path):
    """从同名 _错题.txt 中提取错题题号集合。"""
    wrong_path = txt_path.with_name(txt_path.stem + "_错题.txt")
    if not wrong_path.exists():
        return set()
    text = wrong_path.read_text(encoding="utf-8")
    return {int(m.group(1)) for m in re.finditer(r"^第(\d+)题：", text, re.MULTILINE)}


def build_typst(questions, title: str, wrong_set=None) -> str:
    wrong_set = wrong_set or set()
    parts = [TYPST_HEADER]
    parts.append(f'\n#align(center)[#text(size: 18pt, weight: "bold")[{esc(title)}]]\n')
    parts.append("#v(1em)\n")

    for item in questions:
        stem = esc(item["stem"])
        opts = [(esc(l), esc(t)) for l, t in item["options"]]
        answer = esc(item["answer"])
        knowledge = esc(item["knowledge"])

        if opts:
            opts_str = ", ".join(f'("{l}", "{t}")' for l, t in opts)
            opts_literal = f"({opts_str},)"
        else:
            opts_literal = "()"

        is_wrong = item["index"] in wrong_set
        wrong_arg = "true" if is_wrong else "false"

        parts.append(
            f'#question-block({item["index"]}, "{stem}", '
            f'{opts_literal}, "{answer}", "{knowledge}", is-wrong: {wrong_arg})\n\n'
        )
    return "".join(parts)


def convert_file(txt_path: Path, out_path: Path, title: str | None = None):
    text = txt_path.read_text(encoding="utf-8")
    questions = parse_txt(text)
    if not questions:
        print(f"  [跳过] {txt_path.name}：没有解析到题目")
        return 0
    title = title or txt_path.stem
    wrong_set = load_wrong_indices(txt_path)
    typ = build_typst(questions, title, wrong_set)
    out_path.write_text(typ, encoding="utf-8")
    nw = len(wrong_set)
    print(f"  {txt_path.name} -> {out_path.name}（{len(questions)} 题，错题标红 {nw} 题）")
    return len(questions)


def main():
    parser = argparse.ArgumentParser(description="把 ChN.txt 转成 Typst 文件")
    parser.add_argument("files", nargs="*", help="要转换的 txt 文件；留空则处理整个目录")
    parser.add_argument("-d", "--dir", default="output", help="txt 所在目录，默认 output")
    parser.add_argument("-o", "--out", default=None, help="输出目录，默认与 txt 同目录")
    args = parser.parse_args()

    if args.files:
        targets = [Path(f) for f in args.files]
    else:
        d = Path(args.dir)
        targets = sorted(d.glob("Ch[0-9]*.txt"),
                         key=lambda p: int(re.search(r"\d+", p.stem).group()))

    if not targets:
        print("没有找到可转换的 txt 文件")
        sys.exit(1)

    out_dir = Path(args.out) if args.out else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    for txt_path in targets:
        if not txt_path.exists():
            print(f"  [跳过] {txt_path}：不存在")
            continue
        dst = (out_dir / (txt_path.stem + ".typ")) if out_dir else txt_path.with_suffix(".typ")
        total += convert_file(txt_path, dst)

    print(f"完成：共转换 {total} 题")


if __name__ == "__main__":
    main()