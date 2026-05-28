import os
import tempfile
import unittest

from backend.memory import create_conversation_memory_store


class EmptyState:
    department = ""
    cohort_year = None


class LocalMem0MemoryStoreTest(unittest.TestCase):
    def setUp(self):
        fd, self.store_path = tempfile.mkstemp()
        os.close(fd)
        os.unlink(self.store_path)
        self.store = create_conversation_memory_store(provider="mem0", store_path=self.store_path)

    def tearDown(self):
        if os.path.exists(self.store_path):
            os.unlink(self.store_path)

    def test_extracts_corrections_and_multiple_credit_areas(self):
        self.store.update(
            "s1",
            "나는 21학번 컴공 아니고 22학번 소웨야. 전공 60학점, 교양 35학점 들었어.",
            {},
            EmptyState(),
        )

        context = self.store.build_context("s1", "내 졸업요건 볼 때 내가 알려준 정보가 뭐였지?")

        self.assertIn("학과/전공은 소프트웨어학부", context)
        self.assertIn("입학연도는 2022년", context)
        self.assertIn("전공 영역 이수학점은 60학점", context)
        self.assertIn("교양 영역 이수학점은 35학점", context)

    def test_sensitive_input_is_not_stored(self):
        self.store.update("s1", "나는 22학번 컴공이야. 전공 60학점이야.", {}, EmptyState())
        self.store.update("s1", "내 전화번호는 010-1234-5678이고 전공 80학점이야.", {}, EmptyState())

        context = self.store.build_context("s1", "전공 학점 알려줘")

        self.assertIn("60학점", context)
        self.assertNotIn("80학점", context)
        self.assertNotIn("010-1234-5678", context)

    def test_partial_delete_and_clear(self):
        self.store.update(
            "s1",
            "나는 22학번 컴공이야. 전공 60학점, 교양 35학점 들었어.",
            {},
            EmptyState(),
        )

        deleted = self.store.delete_matching("s1", "학점 정보는 지워줘")
        context = self.store.build_context("s1", "내 정보 알려줘")

        self.assertEqual(deleted, 2)
        self.assertIn("컴퓨터공학과", context)
        self.assertNotIn("60학점", context)
        self.assertNotIn("35학점", context)
        self.assertEqual(self.store.clear("s1"), 2)
        self.assertEqual(self.store.build_context("s1", "내 정보 알려줘"), "")

    def test_memory_opt_out_and_enable(self):
        self.store.update("s1", "나는 22학번 컴공이야.", {}, EmptyState())
        self.store.set_enabled("s1", False)
        self.store.update("s1", "교양 35학점이야.", {}, EmptyState())

        self.assertFalse(self.store.is_enabled("s1"))
        self.assertEqual(self.store.build_context("s1", "교양 학점 알려줘"), "")

        self.store.set_enabled("s1", True)
        self.store.update("s1", "교양 35학점이야.", {}, EmptyState())

        self.assertTrue(self.store.is_enabled("s1"))
        self.assertIn("교양 영역 이수학점은 35학점", self.store.build_context("s1", "교양 학점 알려줘"))

    def test_broader_natural_language_corrections_and_delete_by_id(self):
        self.store.update("s1", "나는 22학번 컴공이야. 전공 60학점이야.", {}, EmptyState())
        self.store.update("s1", "아니고 23학번 소웨야. 전공은 65로 정정, 교양은 40으로 수정.", {}, EmptyState())

        context = self.store.build_context("s1", "내 학과 학번 학점 알려줘")

        self.assertIn("학과/전공은 소프트웨어학부", context)
        self.assertIn("입학연도는 2023년", context)
        self.assertIn("전공 영역 이수학점은 65학점", context)
        self.assertIn("교양 영역 이수학점은 40학점", context)

        self.assertEqual(self.store.delete_by_id("s1", "credit_progress:전공"), 1)
        context = self.store.build_context("s1", "내 학점 알려줘")
        self.assertNotIn("전공 영역 이수학점은 65학점", context)
        self.assertIn("교양 영역 이수학점은 40학점", context)

    def test_correction_variants_and_broader_delete_phrases(self):
        self.store.update("s1", "나는 소웨 22학번이고 전공 60학점이야.", {}, EmptyState())
        self.store.update("s1", "소웨가 아니라 컴공이고 학번은 23으로 정정. 전공은 66으로 바꿔줘.", {}, EmptyState())

        context = self.store.build_context("s1", "내 정보 알려줘")

        self.assertIn("학과/전공은 컴퓨터공학과", context)
        self.assertIn("입학연도는 2023년", context)
        self.assertIn("전공 영역 이수학점은 66학점", context)

        deleted = self.store.delete_matching("s1", "내 전공 학점은 기억에서 빼줘")
        context = self.store.build_context("s1", "내 정보 알려줘")

        self.assertEqual(deleted, 1)
        self.assertNotIn("전공 영역 이수학점은 66학점", context)
        self.assertIn("학과/전공은 컴퓨터공학과", context)


if __name__ == "__main__":
    unittest.main()
