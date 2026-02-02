"""Tests for shell alias detection and resolution."""

import pytest

from fundcli.aliases import (
    _parse_bash_zsh_aliases,
    _parse_fish_aliases,
    detect_shell,
    resolve_alias_to_executable,
    build_alias_mappings,
)
from fundcli.mapper import create_mapper


class TestDetectShell:
    def test_bash(self, monkeypatch):
        monkeypatch.setenv("SHELL", "/bin/bash")
        assert detect_shell() == "bash"

    def test_zsh(self, monkeypatch):
        monkeypatch.setenv("SHELL", "/bin/zsh")
        assert detect_shell() == "zsh"

    def test_fish(self, monkeypatch):
        monkeypatch.setenv("SHELL", "/usr/bin/fish")
        assert detect_shell() == "fish"

    def test_homebrew_bash(self, monkeypatch):
        monkeypatch.setenv("SHELL", "/opt/homebrew/bin/bash")
        assert detect_shell() == "bash"

    def test_unknown(self, monkeypatch):
        monkeypatch.setenv("SHELL", "/bin/csh")
        assert detect_shell() == "unknown"

    def test_empty(self, monkeypatch):
        monkeypatch.delenv("SHELL", raising=False)
        assert detect_shell() == "unknown"


class TestParseBashZshAliases:
    def test_bash_format(self):
        output = "alias l='ls -CF'\nalias ll='ls -alF'\n"
        result = _parse_bash_zsh_aliases(output)
        assert result == {"l": "ls -CF", "ll": "ls -alF"}

    def test_zsh_format(self):
        output = "l='ls -CF'\nll='ls -alF'\n"
        result = _parse_bash_zsh_aliases(output)
        assert result == {"l": "ls -CF", "ll": "ls -alF"}

    def test_double_quotes(self):
        output = 'alias tf="terraform"\n'
        result = _parse_bash_zsh_aliases(output)
        assert result == {"tf": "terraform"}

    def test_no_quotes(self):
        output = "k=kubectl\n"
        result = _parse_bash_zsh_aliases(output)
        assert result == {"k": "kubectl"}

    def test_path_value(self):
        output = "alias vim='/opt/homebrew/bin/vim'\n"
        result = _parse_bash_zsh_aliases(output)
        assert result == {"vim": "/opt/homebrew/bin/vim"}

    def test_equals_in_value(self):
        output = "alias grep='grep --color=auto'\n"
        result = _parse_bash_zsh_aliases(output)
        assert result == {"grep": "grep --color=auto"}

    def test_empty_output(self):
        assert _parse_bash_zsh_aliases("") == {}
        assert _parse_bash_zsh_aliases("   \n  \n") == {}

    def test_multiple_aliases(self):
        output = (
            "alias k='kubectl'\n"
            "alias l='ls -CF'\n"
            "alias vim='/opt/homebrew/bin/vim'\n"
            "alias suod='sudo'\n"
        )
        result = _parse_bash_zsh_aliases(output)
        assert len(result) == 4
        assert result["k"] == "kubectl"
        assert result["suod"] == "sudo"


class TestParseFishAliases:
    def test_basic(self):
        output = "alias l 'ls -CF'\nalias k kubectl\n"
        result = _parse_fish_aliases(output)
        assert result == {"l": "ls -CF", "k": "kubectl"}

    def test_empty(self):
        assert _parse_fish_aliases("") == {}


class TestResolveAlias:
    def test_simple(self):
        assert resolve_alias_to_executable("ls -CF") == "ls"

    def test_path(self):
        assert resolve_alias_to_executable("/opt/homebrew/bin/vim") == "vim"

    def test_compound(self):
        assert resolve_alias_to_executable("git diff --color-words --no-index") == "git"

    def test_bare_command(self):
        assert resolve_alias_to_executable("kubectl") == "kubectl"

    def test_typo_alias(self):
        assert resolve_alias_to_executable("sudo") == "sudo"

    def test_wrapper_in_alias(self):
        # alias resolves to the first command, even if it's a wrapper
        assert resolve_alias_to_executable("sudo dscacheutil -flushcache") == "sudo"


class TestBuildAliasMappings:
    def test_resolves_known_aliases(self):
        mapper = create_mapper()
        aliases = {"l": "ls -CF", "k": "kubectl"}
        result = _build_with_aliases(mapper, aliases)
        assert result["l"] == "coreutils"
        assert result["k"] == "kubernetes"

    def test_skips_already_known(self):
        mapper = create_mapper()
        # grep is already mapped via projects.toml
        aliases = {"grep": "grep --color=auto"}
        result = _build_with_aliases(mapper, aliases)
        assert "grep" not in result

    def test_skips_unknown(self):
        mapper = create_mapper()
        aliases = {"foo": "some-unknown-tool --flag"}
        result = _build_with_aliases(mapper, aliases)
        assert "foo" not in result

    def test_alias_chain(self):
        mapper = create_mapper()
        # la -> l -> ls -> coreutils
        aliases = {"l": "ls -CF", "la": "l -A"}
        result = _build_with_aliases(mapper, aliases)
        assert result["l"] == "coreutils"
        assert result["la"] == "coreutils"

    def test_path_alias(self):
        mapper = create_mapper()
        aliases = {"vim": "/opt/homebrew/bin/vim"}
        # vim is already known, so skipped
        result = _build_with_aliases(mapper, aliases)
        assert "vim" not in result

    def test_empty_aliases(self):
        mapper = create_mapper()
        result = _build_with_aliases(mapper, {})
        assert result == {}


def _build_with_aliases(mapper, aliases: dict[str, str]) -> dict[str, str]:
    """Helper to call build_alias_mappings with pre-set aliases (no shell subprocess)."""
    from unittest.mock import patch
    with patch("fundcli.aliases.get_aliases", return_value=aliases):
        return build_alias_mappings(mapper)
