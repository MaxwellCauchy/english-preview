"""针对会丢内容、乱序或导出失败的路径做端到端验证。"""

import queue
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import unquote

from core.exporter import save_markdown
from core.layout import join_lines
from core.markdown_builder import to_markdown
from core.models import Block, Document, ImageNode, Page, Paragraph, ReaderConfig, Section, TableNode
from core.pdf_reader import (
    CancelledError, OCRRequiredError, PDFReadError, PasswordRequiredError,
    clean_blocks, extract_text_blocks, read_pdf,
)
from tests.fixtures import make_encrypted, make_mixed_scan, make_sample, make_scan


class PDFReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.temporary.name)
        cls.sample = make_sample(cls.folder)
        cls.scan = make_scan(cls.folder)
        cls.encrypted = make_encrypted(cls.folder)
        cls.mixed = make_mixed_scan(cls.folder)
        cls.result = read_pdf(cls.sample, output_dir=cls.folder / "runs")
        cls.md = cls.result.markdown

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_three_pages_and_title(self):
        self.assertEqual(self.result.page_count, 3)
        self.assertTrue(self.md.startswith("# Reading Before Class\n"))
        self.assertEqual(self.md.count("# Reading Before Class"), 1)

    def test_running_headers_and_footers_removed(self):
        self.assertNotIn("ENGLISH CLASS HANDOUT", self.md)
        self.assertNotIn("Page 1 of 3", self.md)
        self.assertNotIn("Page 2 of 3", self.md)
        self.assertNotIn("Page 3 of 3", self.md)

    def test_body_number_is_kept(self):
        self.assertIn("2026", self.md)

    def test_discretionary_and_real_hyphens(self):
        self.assertIn("international example", self.md)
        self.assertIn("well-known method", self.md)
        self.assertNotIn("inter- national", self.md)

    def test_double_column_regions_in_reading_order(self):
        positions = [self.md.index(token) for token in (
            "LEFT-A1", "LEFT-A6", "RIGHT-A1", "RIGHT-A6",
            "A full-width bridge", "LEFT-B1", "LEFT-B5", "RIGHT-B1", "RIGHT-B5",
        )]
        self.assertEqual(positions, sorted(positions))
        for side in ("LEFT-A", "RIGHT-A", "LEFT-B", "RIGHT-B"):
            count = 6 if side.endswith("A") else 5
            for index in range(1, count + 1):
                self.assertEqual(self.md.count(f"{side}{index}"), 1)

    def test_ordered_list_and_wrapped_item(self):
        self.assertIn("1. Read the title", self.md)
        self.assertIn("2. Underline useful words. Keep their meanings", self.md)
        self.assertIn("3. Summarise", self.md)

    def test_numbered_large_headings_are_not_list_items(self):
        self.assertIn("## 1. Getting started\n", self.md)
        self.assertIn("## 2. A simple plan\n", self.md)
        self.assertIn("### Study schedule\n", self.md)

    def test_ruled_table_and_position(self):
        self.assertIn("| Activity | Minutes | Purpose |", self.md)
        self.assertIn("| Preview | 10 | Find the topic |", self.md)
        self.assertLess(self.md.index("| Review |"), self.md.index("This sentence follows the table."))

    def test_borderless_table_and_warning(self):
        self.assertIn("| Word | Hits | Note |", self.md)
        self.assertIn("| preview | 4 | important |", self.md)
        self.assertTrue(any("无框线表格" in warning for warning in self.result.warnings))

    def test_images_exist_and_follow_page_body(self):
        images = [
            node for section in self.result.document.sections for node in section.content
            if isinstance(node, ImageNode)
        ]
        self.assertEqual(len(images), 1)
        self.assertTrue((self.result.work_dir / images[0].path).is_file())
        self.assertLess(self.md.index("The illustration belongs here."), self.md.index("!["))
        self.assertLess(self.md.index("This sentence follows the image."), self.md.index("!["))

    def test_save_copies_assets_and_preserves_edits(self):
        target = self.folder / "export" / "课堂 notes (1).md"
        saved = save_markdown(self.result, target, markdown=self.md + "\nMy own note.\n")
        text = saved.read_text(encoding="utf-8")
        self.assertIn("My own note.", text)
        import re
        links = re.findall(r"!\[[^]]*\]\(([^)]+)\)", text)
        self.assertEqual(len(links), 1)
        self.assertTrue((saved.parent / unquote(links[0])).is_file())
        self.assertNotIn("](assets/", text)
        # 再次保存到另一处，也应复制资源，不破坏先前结果。
        second = save_markdown(self.result, self.folder / "second" / "notes.md")
        self.assertTrue(second.is_file())
        self.assertTrue(saved.is_file())

    def test_scan_fails_with_ocr_message(self):
        with self.assertRaisesRegex(OCRRequiredError, "OCR"):
            read_pdf(self.scan, output_dir=self.folder / "runs")

    def test_partial_scan_is_reported_without_losing_text(self):
        result = read_pdf(self.mixed, output_dir=self.folder / "runs")
        self.assertEqual(result.page_count, 2)
        self.assertIn("selectable text", result.markdown)
        self.assertTrue(any("第 2 页" in message and "OCR" in message for message in result.warnings))

    def test_encrypted_pdf(self):
        with self.assertRaises(PasswordRequiredError):
            read_pdf(self.encrypted, output_dir=self.folder / "runs")
        with self.assertRaises(PasswordRequiredError):
            read_pdf(self.encrypted, password="wrong", output_dir=self.folder / "runs")
        result = read_pdf(self.encrypted, password="reader", output_dir=self.folder / "runs")
        self.assertIn("password-protected", result.markdown)

    def test_invalid_and_missing_pdf(self):
        with self.assertRaises(PDFReadError):
            read_pdf(self.folder / "missing.pdf", output_dir=self.folder / "runs")
        fake = self.folder / "fake.pdf"
        fake.write_text("not a PDF", encoding="utf-8")
        with self.assertRaises(PDFReadError):
            read_pdf(fake, output_dir=self.folder / "runs")

    def test_cancel_before_read(self):
        cancelled = threading.Event()
        cancelled.set()
        with self.assertRaises(CancelledError):
            read_pdf(self.sample, cancel_event=cancelled, output_dir=self.folder / "runs")

    def test_cancel_during_read_removes_partial_run(self):
        cancelled = threading.Event()
        output = self.folder / "cancel-output"
        def progress(done, total, message):
            cancelled.set()
        with self.assertRaises(CancelledError):
            read_pdf(self.sample, cancel_event=cancelled, progress_callback=progress, output_dir=output)
        self.assertEqual(list(output.iterdir()), [])

    def test_no_images_option(self):
        result = read_pdf(self.sample, config=ReaderConfig(extract_images=False), output_dir=self.folder / "runs")
        self.assertNotIn("![", result.markdown)
        self.assertFalse(result.assets_dir.exists())

    def test_keep_headers_option(self):
        result = read_pdf(self.sample, config=ReaderConfig(remove_headers=False), output_dir=self.folder / "runs")
        self.assertIn("ENGLISH CLASS HANDOUT", result.markdown)
        self.assertIn("Page 1 of 3", result.markdown)

    def test_raw_coordinates_and_cleaning_do_not_mutate_input(self):
        pages = extract_text_blocks(self.sample)
        texts_before = [b.text for p in pages for b in p.blocks]
        clean_blocks(pages)
        self.assertEqual(texts_before, [b.text for p in pages for b in p.blocks])
        self.assertTrue(any(b.font_size >= 20 and b.is_bold for b in pages[0].blocks))
        self.assertTrue(all(b.x0 <= b.x1 and b.y0 <= b.y1 for p in pages for b in p.blocks))

    def test_cli_conversion(self):
        project = Path(__file__).resolve().parent.parent
        output = self.folder / "cli" / "result.md"
        completed = subprocess.run(
            [sys.executable, str(project / "main.py"), str(self.sample), "-o", str(output)],
            capture_output=True, text=True, cwd=project,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Reading Before Class", output.read_text(encoding="utf-8"))

    def test_cli_password_is_passed_to_reader(self):
        project = Path(__file__).resolve().parent.parent
        output = self.folder / "cli" / "protected.md"
        completed = subprocess.run(
            [sys.executable, str(project / "main.py"), str(self.encrypted),
             "-o", str(output), "--ask-password"],
            input="reader\n", capture_output=True, text=True, cwd=project,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("password-protected", output.read_text(encoding="utf-8"))

    def test_worker_reports_to_queue_without_using_tk(self):
        from ui.main_window import MainWindow
        window = MainWindow.__new__(MainWindow)
        window.events = queue.Queue()
        window._read_worker(self.encrypted, ReaderConfig(), None, threading.Event())
        messages = []
        while not window.events.empty():
            messages.append(window.events.get())
        self.assertEqual(messages[-1][0], "password")


class TextSafetyTests(unittest.TestCase):
    def test_hyphen_control_and_compound_word(self):
        self.assertEqual(join_lines("inter-", "national"), "international")
        self.assertEqual(join_lines("inter-", "national", False), "inter-national")
        self.assertEqual(join_lines("state-of-the-", "art"), "state-of-the-art")
        self.assertEqual(join_lines("self-", "study"), "self-study")

    def test_literal_markdown_and_table_escape(self):
        document = Document(sections=[Section(content=[
            Paragraph("# literal *stars* and <html>"),
            TableNode([["A", "B"], ["x|y", "one\ntwo"]]),
        ])])
        md = to_markdown(document)
        self.assertIn(r"\# literal \*stars\* and &lt;html&gt;", md)
        self.assertIn(r"x\|y", md)
        self.assertIn("one<br>two", md)

    def test_one_page_title_and_body_number_not_deleted(self):
        page = Page(1, 600, 800, blocks=[
            Block("A real title", 50, 20, 250, 45, 24, True),
            Block("2026", 50, 200, 80, 210, 10),
            Block("1", 290, 780, 300, 790, 10),
        ])
        cleaned = clean_blocks([page])[0]
        texts = [block.text for block in cleaned.blocks]
        self.assertIn("A real title", texts)
        self.assertIn("2026", texts)
        self.assertNotIn("1", texts)


if __name__ == "__main__":
    unittest.main()
