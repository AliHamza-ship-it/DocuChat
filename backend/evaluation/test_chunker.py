import unittest

from backend.rag.chunker import process_document_to_chunks


class ChunkerRegressionTests(unittest.TestCase):
    """
    Regression tests for the ingestion bug where generic title detection
    converted bullet/list items into tiny blocks and those blocks were
    discarded by a minimum-length filter.
    """

    def test_list_items_are_not_dropped(self):
        text = """
Services:
- Web Development
- Business Websites
- AI Automation

Office Hours:
Monday to Friday 9:00 AM - 5:00 PM

Phone: +44 123456789
""".strip()

        chunks = process_document_to_chunks([
            {
                "content": text,
                "metadata": {
                    "source": "knowledge-base.pdf",
                    "page": 1,
                },
            }
        ])

        combined = "\n".join(
            chunk["content"]
            for chunk in chunks
        )

        self.assertIn(
            "Web Development",
            combined,
        )
        self.assertIn(
            "Business Websites",
            combined,
        )
        self.assertIn(
            "AI Automation",
            combined,
        )
        self.assertIn(
            "Office Hours",
            combined,
        )
        self.assertIn(
            "Phone: +44 123456789",
            combined,
        )

    def test_short_fact_is_preserved(self):
        text = """
Email: info@devorbis.com
Employee:
1- Maria MANNAN
""".strip()

        chunks = process_document_to_chunks([
            {
                "content": text,
                "metadata": {
                    "source": "knowledge-base.pdf",
                    "page": 1,
                },
            }
        ])

        combined = "\n".join(
            chunk["content"]
            for chunk in chunks
        )

        self.assertIn(
            "info@devorbis.com",
            combined,
        )
        self.assertIn(
            "Maria MANNAN",
            combined,
        )

    def test_week_day_hierarchy_is_preserved(self):
        text = """
Week 5
Day 2: Integrations
Supabase is used as the operational hub.

Day 3: Testing
Testing starts here.
""".strip()

        chunks = process_document_to_chunks([
            {
                "content": text,
                "metadata": {
                    "source": "training.pdf",
                    "page": 10,
                },
            }
        ])

        day2 = [
            chunk
            for chunk in chunks
            if chunk["metadata"].get("day_number") == 2
        ]

        day3 = [
            chunk
            for chunk in chunks
            if chunk["metadata"].get("day_number") == 3
        ]

        self.assertTrue(day2)
        self.assertTrue(day3)

        self.assertTrue(
            all(
                chunk["metadata"].get("week_number") == 5
                for chunk in day2 + day3
            )
        )

        self.assertTrue(
            all(
                "Week 5" in chunk["metadata"].get(
                    "breadcrumbs",
                    "",
                )
                for chunk in day2 + day3
            )
        )


if __name__ == "__main__":
    unittest.main()
