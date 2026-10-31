"""
Tests for ghost_context.py (the read-only facts + explanation text).
    python test_context.py
It builds a small throw-away folder in your system temp area, only READS it,
and removes it afterwards. It never touches your own files.
"""
import os
import shutil
import tempfile
import unittest

from ghost_context import analyse, gather_facts


class ContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="ghost_test_")
        with open(os.path.join(cls.dir, "notes.txt"), "w") as f:
            f.write("x" * 2048)
        os.makedirs(os.path.join(cls.dir, "old", "sub"))
        for i in range(3):
            with open(os.path.join(cls.dir, "old", "f%d.log" % i), "w") as f:
                f.write("hi")
        for n in ("a.log", "b.log"):
            open(os.path.join(cls.dir, n), "w").close()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_file_fact(self):
        facts = gather_facts("Remove-Item notes.txt", self.dir)
        self.assertEqual(len(facts), 1)
        self.assertIn("2.0 KB", facts[0])
        self.assertIn("edited today", facts[0])

    def test_folder_fact(self):
        facts = gather_facts("Remove-Item ." + os.sep + "old -Recurse", self.dir)
        self.assertTrue(any("3 files, 1 subfolder" in f for f in facts), facts)

    def test_wildcard_fact(self):
        facts = gather_facts("del *.log", self.dir)
        self.assertTrue(any("matches 2 items" in f for f in facts), facts)

    def test_missing_path_gives_no_fact(self):
        self.assertEqual(gather_facts("Remove-Item nothing_here.txt", self.dir), [])

    def test_flags_and_urls_are_ignored(self):
        self.assertEqual(gather_facts("rd /s /q http://x -Force", self.dir), [])

    def test_analyse_red_has_title_facts_and_tip(self):
        verdict, facts, body = analyse("Remove-Item notes.txt", self.dir)
        self.assertEqual(verdict.colour, "red")
        self.assertIn("Deletes files or folders", body)
        self.assertIn("In this folder:", body)
        self.assertIn("-WhatIf", body)

    def test_analyse_green_has_no_facts(self):
        verdict, facts, body = analyse("Get-ChildItem notes.txt", self.dir)
        self.assertEqual(verdict.colour, "green")
        self.assertEqual(facts, [])

    def test_analyse_idle(self):
        verdict, facts, body = analyse("   ", self.dir)
        self.assertEqual(verdict.colour, "idle")
        self.assertIn("Alt+G", body)

    def test_overwrite_uses_cwd(self):
        verdict, _f, body = analyse("echo hi > notes.txt", self.dir)
        self.assertEqual(verdict.colour, "red")
        verdict2, _f2, _b2 = analyse("echo hi > brand_new.txt", self.dir)
        self.assertEqual(verdict2.colour, "yellow")

    def test_never_modifies_files(self):
        before = sorted(os.listdir(self.dir))
        analyse("Remove-Item old -Recurse -Force", self.dir)
        self.assertEqual(before, sorted(os.listdir(self.dir)))


if __name__ == "__main__":
    unittest.main(verbosity=1)
