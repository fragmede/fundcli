"""Detect shell aliases and resolve them to base executables."""

import os
import re
import subprocess
from pathlib import Path


def detect_shell() -> str:
    """Detect the user's login shell from $SHELL.

    Returns: 'bash', 'zsh', 'fish', or 'unknown'
    """
    shell_path = os.environ.get("SHELL", "")
    basename = Path(shell_path).name
    if basename in ("bash", "zsh", "fish"):
        return basename
    return "unknown"


def _clean_env_for_shell() -> dict[str, str]:
    """Create a clean environment for shell subprocess.

    Removes common bashrc/zshrc guard variables (like *ALREADY_RUN*, *SOURCED*)
    so the shell sources its config files fresh and loads aliases.
    """
    env = dict(os.environ)
    guard_patterns = ("ALREADY_RUN", "_SOURCED", "_LOADED", "_INITIALIZED")
    to_remove = [k for k in env if any(p in k for p in guard_patterns)]
    for k in to_remove:
        del env[k]
    return env


def get_aliases(shell: str | None = None, timeout: float = 5.0) -> dict[str, str]:
    """Get all active shell aliases by running the shell interactively.

    Args:
        shell: Shell name ('bash', 'zsh', 'fish'). Auto-detected if None.
        timeout: Maximum seconds to wait for shell subprocess.

    Returns:
        Dict mapping alias name to alias value string.
    """
    if shell is None:
        shell = detect_shell()
    if shell == "unknown":
        return {}

    env = _clean_env_for_shell()

    try:
        if shell in ("bash", "zsh"):
            result = subprocess.run(
                [shell, "-ic", "alias"],
                capture_output=True, text=True, timeout=timeout,
                env=env,
            )
            return _parse_bash_zsh_aliases(result.stdout)
        elif shell == "fish":
            result = subprocess.run(
                ["fish", "-c", "alias"],
                capture_output=True, text=True, timeout=timeout,
                env=env,
            )
            return _parse_fish_aliases(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return {}
    return {}


def _parse_bash_zsh_aliases(output: str) -> dict[str, str]:
    """Parse output of `alias` from bash or zsh.

    Bash format:  alias name='value'
    Zsh format:   name='value' or name=value
    """
    aliases = {}
    for line in output.strip().splitlines():
        line = line.strip()
        # Remove optional "alias " prefix (bash includes it, zsh may not)
        if line.startswith("alias "):
            line = line[6:]
        # Parse name=value
        match = re.match(r"^([A-Za-z0-9_.:-]+)=(.+)$", line)
        if match:
            name = match.group(1)
            value = match.group(2)
            # Strip surrounding quotes
            if len(value) >= 2:
                if (value[0] == "'" and value[-1] == "'") or \
                   (value[0] == '"' and value[-1] == '"'):
                    value = value[1:-1]
            aliases[name] = value
    return aliases


def _parse_fish_aliases(output: str) -> dict[str, str]:
    """Parse output of `alias` from fish shell.

    Fish format: alias name 'value' or alias name value
    """
    aliases = {}
    for line in output.strip().splitlines():
        line = line.strip()
        if line.startswith("alias "):
            line = line[6:]
        # Split on first space
        parts = line.split(None, 1)
        if len(parts) == 2:
            name = parts[0]
            value = parts[1]
            # Strip surrounding quotes
            if len(value) >= 2:
                if (value[0] == "'" and value[-1] == "'") or \
                   (value[0] == '"' and value[-1] == '"'):
                    value = value[1:-1]
            aliases[name] = value
    return aliases


def resolve_alias_to_executable(alias_value: str) -> str | None:
    """Resolve an alias value string to its base executable name.

    Takes the first token of the alias value and normalizes it.
    Unlike extract_executable, this does NOT skip wrapper commands,
    because the alias itself is the thing being resolved
    (e.g., alias suod='sudo' should resolve to 'sudo').
    """
    import shlex
    from fundcli.parser import normalize_executable

    alias_value = alias_value.strip()
    if not alias_value:
        return None

    try:
        tokens = shlex.split(alias_value)
    except ValueError:
        tokens = alias_value.split()

    if not tokens:
        return None

    return normalize_executable(tokens[0])


def build_alias_mappings(mapper) -> dict[str, str]:
    """Build alias-to-project_id mappings for aliases that resolve to known projects.

    Args:
        mapper: ProjectMapper instance.

    Returns:
        Dict mapping alias name to project_id.
    """
    aliases = get_aliases()
    if not aliases:
        return {}

    # Resolve each alias to its base executable
    alias_to_exe: dict[str, str] = {}
    for alias_name, alias_value in aliases.items():
        exe = resolve_alias_to_executable(alias_value)
        if exe:
            alias_to_exe[alias_name] = exe

    # Resolve alias chains (alias pointing to another alias, 1 level)
    for _ in range(2):
        changed = False
        for alias_name, exe in list(alias_to_exe.items()):
            if exe in alias_to_exe and exe != alias_name:
                alias_to_exe[alias_name] = alias_to_exe[exe]
                changed = True
        if not changed:
            break

    # Map resolved executables to projects
    result: dict[str, str] = {}
    for alias_name, exe in alias_to_exe.items():
        # Skip if alias name is already a known executable
        if mapper.is_known(alias_name):
            continue
        project_id = mapper.map_executable(exe)
        if project_id:
            result[alias_name] = project_id

    return result
