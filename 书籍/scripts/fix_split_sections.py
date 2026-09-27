#!/usr/bin/env python3
"""
合并 ACIM 三部源文件中被错误拆段的小节。

每个小节(由 marker 标识)的内容应在一行内完成。本脚本检测并合并:
- 同一小节内被空行拆开的延续句
- marker 后紧跟 0-缩进延续内容(原文标志)的合并

支持三套 marker:
  - W-X.Y.      (练习手册)
  - T-X.Y.Z.    (正文)
  - M-X.Y.      (教师指南)

跨课/跨章边界保持原样:
  - W: 保留 ---、第X课、练习X 等
  - T: 保留 ---、正文、导言、第X章 NAME 等
  - M: 保留 ---、教师指南、导言、壹/贰/.../拾壹 等

用法:
  python fix_split_sections.py <file> [--marker-prefix W|T|M]
                                    [--struct PATTERN] [--dry-run]

例:
  python fix_split_sections.py acim-2.练习手册.md
  python fix_split_sections.py acim-1.正文.md --marker-prefix T
  python fix_split_sections.py acim-3.教师指南.md --marker-prefix M --dry-run
"""
import argparse
import re
import shutil
import sys
from pathlib import Path


# marker 前缀 -> (正则模板, 默认结构性内容正则)
PRESETS = {
    'W': {
        'marker_re': r'^(\s*)(W-[^\s]+?)\.',
        'struct_re': r'^(---|第[一二三四五六七八九十百千]+课|练习[一二三四五六七八九十百千]+)$',
        'description': '练习手册 (W-X.Y.)',
    },
    'T': {
        'marker_re': r'^(\s*)(T-[^\s]+?)\.',
        'struct_re': r'^(---|第[一二三四五六七八九十百千]+章.*|导言|正文)$',
        'description': '正文 (T-X.Y.Z.)',
    },
    'M': {
        'marker_re': r'^(\s*)(M-[^\s]+?)\.',
        'struct_re': r'^(---|教师指南|导言|[壹贰叁肆伍陆柒捌玖拾]+\. .*)$',
        'description': '教师指南 (M-X.Y.)',
    },
}


def marker_prefix(line: str, marker_re: re.Pattern) -> str | None:
    """提取 marker 前缀(用于判断是否同章/同课,本函数当前不被状态机使用)。"""
    m = marker_re.match(line)
    if not m:
        return None
    indent, full_id = m.group(1), m.group(2)
    parts = full_id.split('.')
    return indent + '.'.join(parts[:-1]) + '.'


def is_blank(line: str) -> bool:
    return line.strip() == ''


def fix_file(
    src: Path,
    marker_re: re.Pattern,
    struct_re: re.Pattern,
    dry_run: bool = False,
    backup_suffix: str = '.bak',
) -> dict:
    """处理单个文件,合并被错误拆段的小节。

    返回统计:{'merged': int, 'old_lines': int, 'new_lines': int}
    """
    content = src.read_text(encoding='utf-8')
    lines = content.split('\n')
    n = len(lines)

    output: list[str] = []
    i = 0
    merged_count = 0

    while i < n:
        line = lines[i]
        m = marker_re.match(line)
        if not m:
            # 非 marker 行,直接输出
            output.append(line)
            i += 1
            continue

        section = [line.rstrip()]
        i += 1

        # 收集延续内容:
        # - 跳过空行
        # - 在下一个 marker 之前停止
        # - 在结构性内容之前停止
        while i < n:
            nl = lines[i]
            if is_blank(nl):
                i += 1
                continue
            if marker_re.match(nl):
                break
            s = nl.strip()
            if s and struct_re.match(s):
                break
            section.append(nl.strip())
            i += 1

        if len(section) > 1:
            merged_count += 1

        output.append(' '.join(section))
        # 跳过尾部空行,只保留一个空行作分隔
        while i < n and is_blank(lines[i]):
            i += 1
        if i < n:
            output.append('')

    new_content = '\n'.join(output)

    if not dry_run:
        backup = src.with_suffix(src.suffix + backup_suffix)
        # 若备份已存在,移到 .bak2 以避免覆盖
        if backup.exists():
            backup2 = src.with_suffix(src.suffix + backup_suffix + '2')
            shutil.copy2(backup, backup2)
        shutil.copy2(src, backup)
        src.write_text(new_content, encoding='utf-8')

    return {
        'merged': merged_count,
        'old_lines': n,
        'new_lines': len(output),
        'path': str(src),
    }


def main():
    parser = argparse.ArgumentParser(
        description='合并 ACIM 源文件中被错误拆段的小节',
    )
    parser.add_argument('file', help='源文件路径')
    parser.add_argument(
        '--marker-prefix', '-p',
        choices=['W', 'T', 'M'],
        help='marker 前缀(W=练习手册, T=正文, M=教师指南)。不指定则按文件路径自动推断。',
    )
    parser.add_argument(
        '--marker-re',
        help='自定义 marker 正则(覆盖预设)',
    )
    parser.add_argument(
        '--struct-re',
        help='自定义结构性内容正则(覆盖预设)',
    )
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='只预览,不修改文件、不备份',
    )
    parser.add_argument(
        '--backup-suffix', '-b',
        default='.bak',
        help='备份后缀(默认 .bak)',
    )

    args = parser.parse_args()
    src = Path(args.file)
    if not src.is_file():
        print(f"错误:文件不存在 — {src}", file=sys.stderr)
        sys.exit(1)

    prefix = args.marker_prefix
    if not prefix:
        name = src.name
        if name.startswith('acim-2'):
            prefix = 'W'
        elif name.startswith('acim-1'):
            prefix = 'T'
        elif name.startswith('acim-3'):
            prefix = 'M'
        else:
            print(f"错误:无法从文件名推断 marker 前缀,请用 --marker-prefix 指定", file=sys.stderr)
            sys.exit(1)
        print(f"[自动推断] marker 前缀: {prefix} ({PRESETS[prefix]['description']})")

    preset = PRESETS[prefix]
    marker_re = re.compile(args.marker_re or preset['marker_re'])
    struct_re = re.compile(args.struct_re or preset['struct_re'])

    result = fix_file(
        src=src,
        marker_re=marker_re,
        struct_re=struct_re,
        dry_run=args.dry_run,
        backup_suffix=args.backup_suffix,
    )

    print(f"\n{'[预览] ' if args.dry_run else ''}处理: {result['path']}")
    print(f"  合并的小节数: {result['merged']}")
    print(f"  原行数: {result['old_lines']}, 新行数: {result['new_lines']}")
    if not args.dry_run:
        print(f"  备份: {src.with_suffix(src.suffix + args.backup_suffix)}")


if __name__ == '__main__':
    main()
