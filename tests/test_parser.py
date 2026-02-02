"""Tests for command parser."""

import pytest

from fundcli.parser import (
    extract_executable,
    extract_executables,
    split_command_segments,
    normalize_executable,
)


class TestSplitCommandSegments:
    """Test command segment splitting."""

    def test_simple_command(self):
        assert split_command_segments("ls -la") == ["ls -la"]

    def test_pipe(self):
        assert split_command_segments("cat foo | grep bar") == ["cat foo", "grep bar"]

    def test_multiple_pipes(self):
        result = split_command_segments("cat foo | grep bar | wc -l")
        assert result == ["cat foo", "grep bar", "wc -l"]

    def test_and_operator(self):
        assert split_command_segments("make && make install") == ["make", "make install"]

    def test_or_operator(self):
        assert split_command_segments("test -f foo || echo missing") == ["test -f foo", "echo missing"]

    def test_semicolon(self):
        assert split_command_segments("cd /tmp; ls") == ["cd /tmp", "ls"]

    def test_quoted_pipe(self):
        # Pipe inside quotes should not split
        result = split_command_segments('echo "hello | world"')
        assert result == ['echo "hello | world"']


class TestExtractExecutable:
    """Test executable extraction from single segments."""

    def test_simple_command(self):
        assert extract_executable("ls -la") == "ls"

    def test_with_path(self):
        assert extract_executable("/usr/bin/curl http://example.com") == "curl"

    def test_relative_path(self):
        assert extract_executable("./script.py") == "script.py"

    def test_sudo(self):
        assert extract_executable("sudo apt install vim") == "apt"

    def test_env(self):
        assert extract_executable("env VAR=1 python script.py") == "python"

    def test_time(self):
        assert extract_executable("time make") == "make"

    def test_variable_assignment(self):
        assert extract_executable("FOO=bar python script.py") == "python"

    def test_comment(self):
        assert extract_executable("# this is a comment") is None

    def test_empty(self):
        assert extract_executable("") is None
        assert extract_executable("   ") is None


class TestExtractExecutables:
    """Test extracting all executables from a command."""

    def test_simple(self):
        assert extract_executables("git status") == ["git"]

    def test_pipe(self):
        result = extract_executables("cat foo.txt | grep error | wc -l")
        assert result == ["cat", "grep", "wc"]

    def test_and_chain(self):
        result = extract_executables("make && make install")
        assert result == ["make", "make"]

    def test_sudo_counted(self):
        result = extract_executables("sudo apt install vim")
        assert result == ["sudo", "apt"]

    def test_sudo_in_pipe(self):
        result = extract_executables("cat /etc/passwd | sudo tee /tmp/foo")
        assert result == ["cat", "sudo", "tee"]

    def test_builtins_excluded(self):
        result = extract_executables("cd /tmp && ls")
        assert "cd" not in result
        assert "ls" in result

    def test_builtins_included(self):
        result = extract_executables("cd /tmp && ls", include_builtins=True)
        assert "cd" in result
        assert "ls" in result


class TestNormalizeExecutable:
    """Test executable normalization."""

    def test_simple(self):
        assert normalize_executable("curl") == "curl"

    def test_path(self):
        assert normalize_executable("/usr/bin/curl") == "curl"

    def test_relative(self):
        assert normalize_executable("./foo.py") == "foo.py"

    def test_home_path(self):
        assert normalize_executable("~/bin/mytool") == "mytool"
