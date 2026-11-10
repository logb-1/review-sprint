import base64
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from review_sprint.ingest import extract_doc

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class ImageExtractionTest(unittest.TestCase):
    def test_pptx_and_docx_images_are_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets = root / "assets"
            assets.mkdir()
            image = root / "dot.png"
            image.write_bytes(PNG)

            from pptx import Presentation
            prs = Presentation()
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            slide.shapes.add_picture(str(image), 0, 0, width=100000)
            deck_path = root / "deck.pptx"
            prs.save(deck_path)
            deck = extract_doc(deck_path, "materials/deck.pptx", assets)
            self.assertEqual(len(deck.images), 1)
            self.assertEqual(deck.images[0]["page"], 1)
            self.assertTrue((root / deck.images[0]["file"]).exists())

            import docx
            document = docx.Document()
            document.add_paragraph("含图讲义")
            document.add_picture(str(image))
            docx_path = root / "notes.docx"
            document.save(docx_path)
            notes = extract_doc(docx_path, "materials/notes.docx", assets)
            self.assertEqual(len(notes.images), 1)
            self.assertTrue((root / notes.images[0]["file"]).exists())


if __name__ == "__main__":
    unittest.main()
