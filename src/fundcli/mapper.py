"""Map executable names to open source projects."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Use tomllib (3.11+) or tomli as fallback
try:
    import tomllib
except ImportError:
    import tomli as tomllib


@dataclass
class DonationURL:
    """A donation URL for a project."""
    platform: str  # github_sponsors, opencollective, direct, etc.
    url: str


@dataclass
class Project:
    """An open source project that can receive donations."""
    id: str
    name: str
    description: str = ""
    executables: list[str] = field(default_factory=list)
    donation_urls: list[DonationURL] = field(default_factory=list)
    github: str | None = None
    website: str | None = None

    @property
    def primary_donation_url(self) -> str | None:
        """Get the first/primary donation URL."""
        if self.donation_urls:
            return self.donation_urls[0].url
        return None


class ProjectMapper:
    """Maps executables to projects and manages the project database."""

    def __init__(self):
        self._projects: dict[str, Project] = {}
        self._exe_to_project: dict[str, str] = {}  # exe name -> project id

    def load_from_toml(self, path: Path) -> None:
        """Load project mappings from a TOML file."""
        with open(path, "rb") as f:
            data = tomllib.load(f)

        for project_id, project_data in data.items():
            project = self._parse_project(project_id, project_data)
            self._projects[project_id] = project

            # Map all executables to this project
            for exe in project.executables:
                self._exe_to_project[exe] = project_id

    def load_bundled(self) -> None:
        """Load the bundled projects.toml database."""
        bundled_path = Path(__file__).parent / "data" / "projects.toml"
        if bundled_path.exists():
            self.load_from_toml(bundled_path)

    def _parse_project(self, project_id: str, data: dict[str, Any]) -> Project:
        """Parse a project from TOML data."""
        donation_urls = []
        for url_data in data.get("donation_urls", []):
            donation_urls.append(DonationURL(
                platform=url_data.get("platform", "direct"),
                url=url_data["url"],
            ))

        return Project(
            id=project_id,
            name=data.get("name", project_id),
            description=data.get("description", ""),
            executables=data.get("executables", [project_id]),
            donation_urls=donation_urls,
            github=data.get("github"),
            website=data.get("website"),
        )

    def get_project(self, project_id: str) -> Project | None:
        """Get a project by ID."""
        return self._projects.get(project_id)

    def get_project_for_executable(self, exe: str) -> Project | None:
        """Get the project associated with an executable."""
        project_id = self._exe_to_project.get(exe)
        if project_id:
            return self._projects.get(project_id)
        return None

    def map_executable(self, exe: str) -> str | None:
        """Map an executable to a project ID. Returns None if unknown."""
        return self._exe_to_project.get(exe)

    def all_projects(self) -> list[Project]:
        """Get all loaded projects."""
        return list(self._projects.values())

    def search_projects(self, query: str) -> list[Project]:
        """Search projects by name, description, or executable."""
        query = query.lower()
        results = []

        for project in self._projects.values():
            if (query in project.name.lower() or
                query in project.description.lower() or
                query in project.id.lower() or
                any(query in exe.lower() for exe in project.executables)):
                results.append(project)

        return results

    def add_custom_mapping(self, exe: str, project_id: str) -> None:
        """Add a custom executable -> project mapping."""
        self._exe_to_project[exe] = project_id

    def is_known(self, exe: str) -> bool:
        """Check if an executable has a known project mapping."""
        return exe in self._exe_to_project


def create_mapper() -> ProjectMapper:
    """Create a ProjectMapper with bundled data loaded."""
    mapper = ProjectMapper()
    mapper.load_bundled()
    return mapper
