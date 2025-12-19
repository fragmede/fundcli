"""Investigate unknown executables to determine their origin and classification."""

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from fundcli.local_db import LocalDatabase, UnknownExecutable


# Patterns to detect copyright/authorship in scripts
COPYRIGHT_PATTERNS = [
    re.compile(r'\(c\)\s*\d{4}', re.IGNORECASE),
    re.compile(r'©\s*\d{4}', re.IGNORECASE),
    re.compile(r'copyright\s+\d{4}', re.IGNORECASE),
    re.compile(r'copyright\s+\(c\)', re.IGNORECASE),
    re.compile(r'author:\s*\S+', re.IGNORECASE),
    re.compile(r'license:\s*\S+', re.IGNORECASE),
    re.compile(r'mit license', re.IGNORECASE),
    re.compile(r'apache license', re.IGNORECASE),
    re.compile(r'gnu general public license', re.IGNORECASE),
    re.compile(r'\bgpl\b', re.IGNORECASE),
    re.compile(r'\bbsd\b.*license', re.IGNORECASE),
    re.compile(r'all rights reserved', re.IGNORECASE),
]

# System directories that indicate built-in commands
SYSTEM_DIRS = [
    '/usr/bin',
    '/bin',
    '/usr/sbin',
    '/sbin',
    '/System',
]

# macOS-specific built-in commands that may not have --help
MACOS_BUILTINS = {
    'open', 'pbcopy', 'pbpaste', 'say', 'osascript', 'defaults',
    'launchctl', 'diskutil', 'hdiutil', 'ditto', 'plutil',
    'security', 'codesign', 'spctl', 'xattr', 'chflags',
    'mdls', 'mdfind', 'mdutil', 'screencapture', 'sips',
    'caffeinate', 'pmset', 'systemsetup', 'networksetup',
}


@dataclass
class InvestigationResult:
    """Result of investigating an executable."""
    executable: str
    path: str | None
    file_type: str  # 'script', 'binary', 'not_found'
    copyright_line: str | None
    help_text: str | None
    suggested_classification: str  # 'system', 'third_party', 'user', 'unknown'
    suggestion_reason: str


def which_executable(exe: str) -> str | None:
    """Find the path to an executable using shutil.which."""
    return shutil.which(exe)


def get_file_type(path: str) -> str:
    """
    Determine if a file is a script or binary.

    Uses the `file` command to detect type.
    Returns: 'script', 'binary', or 'unknown'
    """
    try:
        result = subprocess.run(
            ['file', path],
            capture_output=True,
            text=True,
            timeout=5,
        )
        output = result.stdout.lower()

        if 'script' in output or 'text' in output:
            return 'script'
        elif 'executable' in output or 'mach-o' in output or 'elf' in output:
            return 'binary'
        else:
            return 'unknown'
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return 'unknown'


def run_help(exe: str, timeout: float = 2.0) -> str | None:
    """
    Run --help on an executable and capture output.

    Returns first 10 lines of output, or None if failed.
    """
    try:
        # Try --help first, then -h, then no args
        for args in [[exe, '--help'], [exe, '-h']]:
            try:
                result = subprocess.run(
                    args,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                output = result.stdout or result.stderr
                if output and len(output.strip()) > 10:
                    lines = output.strip().split('\n')[:10]
                    return '\n'.join(lines)
            except (subprocess.TimeoutExpired, OSError):
                continue
        return None
    except Exception:
        return None


def extract_copyright(path: str, max_lines: int = 50) -> str | None:
    """
    Extract copyright/license info from a script file.

    Reads first max_lines lines and looks for copyright patterns.
    Returns the matching line, or None if not found.
    """
    try:
        with open(path, 'r', errors='ignore') as f:
            for i, line in enumerate(f):
                if i >= max_lines:
                    break
                for pattern in COPYRIGHT_PATTERNS:
                    if pattern.search(line):
                        return line.strip()[:200]  # Truncate long lines
        return None
    except (OSError, IOError):
        return None


def is_user_directory(path: str) -> bool:
    """Check if path is in a user directory (home, scripts, etc.)."""
    home = str(Path.home())
    path_lower = path.lower()

    # Check if in home directory
    if path.startswith(home):
        # But not in standard package managers
        if any(pkg in path_lower for pkg in ['/homebrew/', '/.nvm/', '/.npm/', '/.yarn/', '/miniconda/', '/anaconda/', '/.local/share/', '/.cargo/']):
            return False
        return True

    return False


def is_system_path(path: str) -> bool:
    """Check if path is in a system directory."""
    for sys_dir in SYSTEM_DIRS:
        if path.startswith(sys_dir):
            return True
    return False


def suggest_classification(
    exe: str,
    path: str | None,
    file_type: str,
    copyright_line: str | None,
) -> tuple[str, str]:
    """
    Suggest a classification for an executable.

    Returns: (classification, reason)
    """
    # Not found
    if path is None:
        return ('not_found', 'executable not found in PATH')

    # Known macOS builtins
    if exe in MACOS_BUILTINS:
        return ('system', f'macOS built-in command')

    # System path without copyright = system tool
    if is_system_path(path):
        if copyright_line:
            return ('third_party', f'system path with copyright: {copyright_line[:50]}')
        return ('system', f'system path: {path}')

    # User directory without copyright = user script
    if is_user_directory(path) and not copyright_line:
        return ('user', f'user directory, no copyright detected')

    # Has copyright = third party
    if copyright_line:
        return ('third_party', f'copyright found: {copyright_line[:50]}')

    # Script in package manager location = third party
    path_lower = path.lower()
    if any(pkg in path_lower for pkg in ['/homebrew/', '/.nvm/', '/.npm/', '/.yarn/', '/miniconda/', '/anaconda/', '/.cargo/']):
        return ('third_party', f'installed via package manager')

    # Default
    return ('unknown', 'unable to determine classification')


def investigate_executable(exe: str) -> InvestigationResult:
    """
    Fully investigate an unknown executable.

    Returns InvestigationResult with all gathered info.
    """
    path = which_executable(exe)

    if path is None:
        return InvestigationResult(
            executable=exe,
            path=None,
            file_type='not_found',
            copyright_line=None,
            help_text=None,
            suggested_classification='not_found',
            suggestion_reason='executable not found in PATH',
        )

    file_type = get_file_type(path)
    copyright_line = None

    # Only look for copyright in scripts
    if file_type == 'script':
        copyright_line = extract_copyright(path)

    help_text = run_help(exe)

    classification, reason = suggest_classification(
        exe, path, file_type, copyright_line
    )

    return InvestigationResult(
        executable=exe,
        path=path,
        file_type=file_type,
        copyright_line=copyright_line,
        help_text=help_text,
        suggested_classification=classification,
        suggestion_reason=reason,
    )


def investigate_and_save(
    exe: str,
    db: LocalDatabase,
    force: bool = False,
) -> UnknownExecutable:
    """
    Investigate an executable and save to database.

    Args:
        exe: Executable name
        db: LocalDatabase instance
        force: If True, re-investigate even if cached

    Returns:
        UnknownExecutable record
    """
    # Check cache
    if not force:
        cached = db.get_unknown(exe)
        if cached and cached.path is not None:  # Has been investigated
            return cached

    # Investigate
    result = investigate_executable(exe)

    # Create record
    unknown = UnknownExecutable(
        executable=result.executable,
        path=result.path,
        file_type=result.file_type,
        classification=result.suggested_classification,
        copyright_found=result.copyright_line,
        help_text=result.help_text,
        suggested_project=None,  # User sets this
    )

    # Save
    db.save_unknown(unknown)

    return unknown


def classify_executable(
    exe: str,
    classification: str,
    db: LocalDatabase,
    project: str | None = None,
    notes: str | None = None,
) -> UnknownExecutable:
    """
    Manually classify an executable.

    Args:
        exe: Executable name
        classification: 'system', 'third_party', 'user', 'ignored'
        db: LocalDatabase instance
        project: Suggested project ID for third_party
        notes: User notes

    Returns:
        Updated UnknownExecutable record
    """
    # Get existing or create new
    unknown = db.get_unknown(exe)
    if unknown is None:
        # Investigate first
        unknown = investigate_and_save(exe, db)

    # Update classification
    unknown.classification = classification
    if project:
        unknown.suggested_project = project
    if notes:
        unknown.user_notes = notes

    # If user or system, add to exception list
    if classification in ('user', 'system', 'ignored'):
        db.add_exception(exe, classification)

    # Save
    db.save_unknown(unknown)

    return unknown
