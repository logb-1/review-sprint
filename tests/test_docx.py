import base64
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from review_sprint.docx_writer import markdown_to_docx

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class DocxWriterTest(unittest.TestCase):
    def test_inline_styles_image_and_footer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "dot.png").write_bytes(PNG)
            src = root / "book.md"
            src.write_text(
                "# 测试册\n\n**重点结论** 与 *易错点*，代码 `x=1`。\n\n"
                "![示意图](dot.png)\n\n1. 第一步\n2. 第二步\n\n坏字符\x00与\x1f控制符\n",
                encoding="utf-8",
            )
            out = root / "book.docx"
            markdown_to_docx(src.read_text(encoding="utf-8"), out, title="测试册", base_dir=root)
            import docx
            document = docx.Document(str(out))
            text = "\n".join(p.text for p in document.paragraphs)
            self.assertNotIn("**重点结论**", text)
            self.assertIn("重点结论", text)
            self.assertIn("易错点", text)
            self.assertIn("坏字符与控制符", text)
            self.assertNotIn("\x00", text)
            self.assertTrue(any(run.bold for p in document.paragraphs for run in p.runs))
            self.assertTrue(any(run.italic for p in document.paragraphs for run in p.runs))
            self.assertEqual(len(document.inline_shapes), 1)
            self.assertIn("第", document.sections[0].footer.paragraphs[0].text)


if __name__ == "__main__":
    unittest.main()
