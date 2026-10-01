"""无参数启动桌面界面；传入 PDF 路径则执行命令行转换。"""

import argparse
import getpass
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="English Preview：PDF 转 Markdown")
    parser.add_argument("pdf", nargs="?", type=Path, help="PDF 路径；不指定则启动桌面窗口")
    parser.add_argument("-o", "--output", type=Path, help="Markdown 保存位置")
    parser.add_argument("--columns", choices=["auto", "single", "double"], default="auto")
    parser.add_argument("--no-images", action="store_true", help="跳过图片导出")
    parser.add_argument("--keep-headers", action="store_true", help="保留页眉页脚和页码")
    parser.add_argument("--keep-hyphens", action="store_true", help="保留断行处的连字符")
    parser.add_argument("--ask-password", action="store_true", help="交互输入 PDF 打开密码")
    parser.add_argument("--analyze", action="store_true", help="读取后生成独立分析报告")
    parser.add_argument("--mode", choices=["auto", "article", "vocabulary"], default="auto")
    parser.add_argument("--targets", type=Path, help="UTF-8 TXT/CSV 目标词清单，启用分析")
    parser.add_argument("--analysis-output", type=Path, help="分析报告位置（.md/.json），启用分析")
    parser.add_argument("--max-sentence-words", type=int, default=25, help="长句词数阈值")
    parser.add_argument("--min-frequency", type=int, default=2, help="关键词最低频次")
    parser.add_argument("--top-keywords", type=int, default=15)
    parser.add_argument("--include-lists", action="store_true", help="把列表项也作为正文分析单元")
    args = parser.parse_args(argv)
    try:
        if args.pdf is None:
            from ui.main_window import launch
            launch()
            return 0
        from core.exporter import save_markdown
        from core.models import ReaderConfig
        from core.pdf_reader import PDFReadError, read_pdf
    except ModuleNotFoundError as exc:
        print(f"缺少依赖 {exc.name}。请先运行：python -m pip install -r requirements.txt", file=sys.stderr)
        return 1
    except Exception as exc:
        if type(exc).__name__ == "TclError":
            print("无法启动桌面窗口。请在有图形界面的电脑运行；Linux 还需安装 python3-tk。", file=sys.stderr)
            return 1
        raise

    target = args.output or Path(__file__).resolve().parent / "output" / (args.pdf.stem + ".md")
    config = ReaderConfig(
        columns=args.columns, extract_images=not args.no_images,
        remove_headers=not args.keep_headers, dehyphenate=not args.keep_hyphens,
    )
    password = getpass.getpass("PDF 打开密码：") if args.ask_password else None
    try:
        result = read_pdf(args.pdf, config=config, password=password)
        saved = save_markdown(result, target)
    except (PDFReadError, OSError, ValueError) as exc:
        print(f"转换失败：{exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("已停止读取。", file=sys.stderr)
        return 130
    print(f"已保存：{saved}")
    for warning in dict.fromkeys(result.warnings):
        print(f"提示：{warning}", file=sys.stderr)
    if args.analyze or args.targets or args.analysis_output:
        try:
            from core.analyzer import AnalysisError, analyze_document, load_target_words
            from core.analysis.report import save_analysis
            from core.models import AnalysisConfig
        except ImportError:
            print("缺少分析依赖。请运行 python -m pip install -r requirements.txt。", file=sys.stderr)
            return 1
        try:
            analysis = analyze_document(result.document, AnalysisConfig(
                mode=args.mode, target_words=load_target_words(args.targets) if args.targets else None,
                max_words_per_sentence=args.max_sentence_words, min_frequency=args.min_frequency,
                top_keywords=args.top_keywords, include_lists=args.include_lists,
            ))
            report_path = args.analysis_output or saved.with_name(saved.stem + "_analysis.md")
            if report_path.expanduser().resolve() == saved:
                raise ValueError("分析报告位置不能与正文 Markdown 相同。")
            report_saved = save_analysis(analysis, report_path)
        except (AnalysisError, ValueError, OSError) as exc:
            print(f"正文已保存，但分析失败：{exc}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("已停止分析；正文 Markdown 已保存。", file=sys.stderr)
            return 130
        print(f"分析报告已保存：{report_saved}")
        for warning in dict.fromkeys(analysis.warnings):
            if warning not in result.warnings:
                print(f"提示：{warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
