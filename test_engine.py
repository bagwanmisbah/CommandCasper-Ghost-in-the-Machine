"""
Tests for ghost_engine.py. Run from the folder that holds these files:
    python test_engine.py
Needs nothing installed. It only reads rules.json; it never runs any command
it is testing and never touches your files.
"""
import sys
import unittest

from ghost_engine import classify

# Pretend only this file already exists (so we can test "creates" vs "overwrites")
EXISTING = {"report.txt"}


def exists(path):
    return path in EXISTING


GREEN = [
    "Get-ChildItem", "ls", "dir", "dir C:\\Users", "cat notes.txt", "type notes.txt",
    "Get-Content a.txt | Select-Object -First 5", "cd ..", "Set-Location D:\\ghost", "pwd", "cls",
    "echo hello", "Write-Host 'hi; there | rm x'", "echo \"a > b\"",
    "Get-Process | Where-Object { $_.CPU -gt 10 }", "Test-Path x", "Get-Date", "whoami",
    "Remove-Item x -WhatIf", "rm -r x -whatif",
    "git status", "git log --oneline", "git fetch", "git clean -n", "git -C D:\\repo status", "git --version",
    "python --version", "pip list", "npm ls", "winget list", "reg query HKCU\\Software",
    "ipconfig", "ping google.com", "$x = Get-Content a.txt",
    "Get-ChildItem | Sort-Object Length | Format-Table",
    "Get-ChildItem 2>$null", "shutdown /a",
]

YELLOW = [
    "mkdir newfolder", "New-Item a.txt", "Copy-Item a b", "Move-Item a b", "Rename-Item a b",
    "Add-Content a.txt hi", "Set-Content new.txt hi", "echo hi >> log.txt", "echo hi > newfile.txt",
    "pip install requests", "npm install", "git add .", "git commit -m 'x'", "git pull", "git push",
    "git checkout main", "Start-Process notepad", "Stop-Process -Name foo", "Invoke-WebRequest http://x",
    "curl http://x", "unknowncmd arg", ".\\run.ps1", "python app.py", "winget install foo",
    "Set-ExecutionPolicy RemoteSigned", "taskkill /im foo.exe", "Get-ChildItem; Copy-Item a b",
    "robocopy a b", "powershell -Command x", "ipconfig /flushdns", "git branch -d old",
    "[Math]::Sqrt(4)", "foo-bar thing",
]

RED = [
    "Remove-Item a.txt", "rm a.txt", "del a.txt", "rd /s folder", "rmdir folder", "ri x",
    "Remove-Item -Recurse -Force .\\x", "Get-ChildItem | Remove-Item",
    "Get-ChildItem *.log | ForEach-Object { Remove-Item $_ }", "Clear-Content a.txt",
    "Set-Content report.txt hi", "echo hi > report.txt",
    "Copy-Item a b -Force", "Move-Item a b -fo", "New-Item a -Force",
    "iex (iwr http://x)", "Invoke-Expression $cmd",
    "powershell -EncodedCommand AAA", "powershell -enc AAA",
    "Format-Volume -DriveLetter D", "format D:", "Stop-Computer", "Restart-Computer", "shutdown /s",
    "git reset --hard", "git clean -fd", "git push --force", "git push -f origin main", "git rebase main",
    "git branch -D x", "git rm a", "git checkout .", "git checkout -- a.txt", "git stash drop",
    "reg delete HKCU\\x", "sc.exe delete svc", "diskpart",
    "[System.IO.File]::Delete('a')", "$f.Delete()", "Get-ChildItem; Remove-Item x", "echo hi; rm x",
    "robocopy a b /mir", "certutil -urlcache -f http://x a", "if ($x) { Remove-Item a }",
]


class EngineTests(unittest.TestCase):
    def check(self, cases, colour):
        for cmd in cases:
            with self.subTest(cmd=cmd):
                self.assertEqual(classify(cmd, exists=exists).colour, colour, cmd)

    def test_green(self):
        self.check(GREEN, "green")

    def test_yellow(self):
        self.check(YELLOW, "yellow")

    def test_red(self):
        self.check(RED, "red")

    def test_idle(self):
        for cmd in ("", "   "):
            self.assertEqual(classify(cmd).colour, "idle")

    def test_overwrite_without_context_is_yellow(self):
        self.assertEqual(classify("Set-Content report.txt hi").colour, "yellow")

    def test_reasons_present_for_red(self):
        v = classify("Remove-Item a.txt")
        self.assertTrue(v.reasons)


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=1).result
    total = len(GREEN) + len(YELLOW) + len(RED)
    print("\nCommands checked: %d (green %d, yellow %d, red %d)" % (total, len(GREEN), len(YELLOW), len(RED)))
    sys.exit(0 if result.wasSuccessful() else 1)
