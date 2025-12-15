"""Parse shell commands to extract executable names."""

import re
import shlex
from pathlib import Path

# Commands that wrap other commands - we want to skip these
WRAPPER_COMMANDS = frozenset({
    "sudo", "doas",           # Privilege escalation
    "env",                    # Environment modification
    "time", "timeout",        # Timing
    "nohup", "setsid",        # Process control
    "nice", "ionice", "chrt", # Priority
    "strace", "ltrace",       # Tracing
    "watch",                  # Repeated execution
    "xargs",                  # Argument passing
    "exec",                   # Replace shell
    "command",                # Bypass aliases
    "builtin",                # Force builtin
    "caffeinate",             # macOS keep-awake
})

# Shell builtins that aren't really "tools" to donate to
SHELL_BUILTINS = frozenset({
    "cd", "pwd", "echo", "printf", "read",
    "export", "unset", "set",
    "source", ".",
    "alias", "unalias",
    "type", "which", "where",
    "true", "false", ":",
    "test", "[", "[[",
    "break", "continue", "return", "exit",
    "shift", "getopts",
    "local", "declare", "typeset",
    "eval", "exec",
    "trap", "wait", "jobs", "fg", "bg",
    "pushd", "popd", "dirs",
    "history", "fc",
    "umask", "ulimit",
    "enable", "disable",
    "shopt", "complete", "compgen",
    "let", "((",
})

# Shell control structures
CONTROL_KEYWORDS = frozenset({
    "if", "then", "else", "elif", "fi",
    "case", "esac",
    "for", "while", "until", "do", "done",
    "select", "in",
    "function",
    "{", "}",
})


def split_command_segments(command: str) -> list[str]:
    """
    Split a command into segments on pipes and logical operators.

    Handles: |, &&, ||, ;
    Does NOT split inside quotes or subshells.
    """
    # Simple approach: split on pipe/logical operators outside quotes
    # This is a simplified version - could be enhanced for edge cases
    segments = []
    current = []
    depth = 0  # Track parentheses/braces depth
    in_single_quote = False
    in_double_quote = False
    i = 0
    chars = command

    while i < len(chars):
        c = chars[i]

        # Handle quotes
        if c == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            current.append(c)
        elif c == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            current.append(c)
        elif in_single_quote or in_double_quote:
            current.append(c)
        # Handle depth (subshells, braces)
        elif c in "({":
            depth += 1
            current.append(c)
        elif c in ")}":
            depth -= 1
            current.append(c)
        # Handle operators (only at depth 0)
        elif depth == 0:
            # Check for multi-char operators
            remaining = chars[i:]
            if remaining.startswith("&&") or remaining.startswith("||"):
                if current:
                    segments.append("".join(current).strip())
                    current = []
                i += 2
                continue
            elif c == "|" and not remaining.startswith("|"):
                if current:
                    segments.append("".join(current).strip())
                    current = []
            elif c == ";":
                if current:
                    segments.append("".join(current).strip())
                    current = []
            else:
                current.append(c)
        else:
            current.append(c)

        i += 1

    if current:
        segments.append("".join(current).strip())

    return [s for s in segments if s]


def extract_executable(segment: str) -> str | None:
    """
    Extract the executable name from a single command segment.

    Handles wrapper commands, paths, and special cases.
    Returns None if no valid executable found.
    """
    # Skip empty or comment-only segments
    segment = segment.strip()
    if not segment or segment.startswith("#"):
        return None

    # Handle variable assignments at the start (VAR=value cmd)
    # Match: VAR=value, VAR="value", etc.
    while True:
        match = re.match(r'^[A-Za-z_][A-Za-z0-9_]*=\S*\s*', segment)
        if match:
            segment = segment[match.end():].strip()
        else:
            break

    if not segment:
        return None

    # Try to parse with shlex
    try:
        tokens = shlex.split(segment)
    except ValueError:
        # Unbalanced quotes - try simple split
        tokens = segment.split()

    if not tokens:
        return None

    # Find the first non-wrapper token
    for i, token in enumerate(tokens):
        # Skip wrapper commands (with their arguments)
        if token in WRAPPER_COMMANDS:
            # Some wrappers have flags we need to skip
            continue

        # Skip flags for wrappers (e.g., sudo -u user)
        if token.startswith("-"):
            continue

        # Found a non-wrapper, non-flag token
        return normalize_executable(token)

    return None


def normalize_executable(exe: str) -> str:
    """
    Normalize an executable name.

    - Strips paths: /usr/bin/curl -> curl
    - Strips ./ prefix: ./script.py -> script.py
    - Handles common extensions
    """
    # Handle subshell notation
    if exe.startswith("$(") or exe.startswith("`"):
        return None

    # Extract basename from path
    if "/" in exe:
        exe = Path(exe).name

    # Remove common script extensions for base name
    # But keep them for identification
    # e.g., python script.py -> we want "python", not "script.py"

    return exe


def extract_executables(command: str, include_builtins: bool = False) -> list[str]:
    """
    Extract all executable names from a command string.

    Args:
        command: Full command string (may contain pipes, &&, etc.)
        include_builtins: Whether to include shell builtins

    Returns:
        List of executable names found
    """
    executables = []

    for segment in split_command_segments(command):
        exe = extract_executable(segment)
        if exe:
            # Skip builtins unless requested
            if not include_builtins and exe in SHELL_BUILTINS:
                continue
            # Skip control keywords
            if exe in CONTROL_KEYWORDS:
                continue
            executables.append(exe)

    return executables


def extract_all_executables_with_counts(
    commands: list[str],
    include_builtins: bool = False,
) -> dict[str, int]:
    """
    Extract executables from multiple commands and count occurrences.

    Args:
        commands: List of command strings
        include_builtins: Whether to include shell builtins

    Returns:
        Dict mapping executable name to count
    """
    counts: dict[str, int] = {}

    for command in commands:
        for exe in extract_executables(command, include_builtins):
            counts[exe] = counts.get(exe, 0) + 1

    return counts
