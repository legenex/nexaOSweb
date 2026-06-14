"""Project modes for the build pipeline.

A project mode layers on the Flow pipeline without changing its stages. The mode adjusts
three things: the capture questions surfaced during Clarify, the set of files a project of
that mode is expected to carry (required files), and the default build destination. Modes
are a presentation and routing concern; the internal pipeline name stays Flow.

US market only. Destination identifiers are abstract targets, resolved to concrete hosts
by a later milestone.
"""

from dataclasses import dataclass

DEFAULT_MODE = "app"

# Files every mode shares. Mode specific files are appended in each ProjectMode.
_COMMON_FILES = ["project_plan.md", "requirements.md", "change_summary.md"]


@dataclass(frozen=True)
class ProjectMode:
    key: str
    label: str
    capture_questions: list[str]
    required_files: list[str]
    build_destination: str


PROJECT_MODES: dict[str, ProjectMode] = {
    "app": ProjectMode(
        key="app",
        label="App",
        capture_questions=[
            "Which platforms does this app target (web, iOS, Android, desktop)?",
            "What is the single most important action a user takes?",
            "Does it need user accounts and authentication?",
            "What data does it store, and where does that data live?",
        ],
        required_files=[*_COMMON_FILES, "project_preview.html"],
        build_destination="code_repo",
    ),
    "automation": ProjectMode(
        key="automation",
        label="Automation",
        capture_questions=[
            "What event or schedule triggers this automation?",
            "Which systems does it read from and write to?",
            "What are the ordered steps from trigger to result?",
            "How should it behave when a step fails?",
        ],
        required_files=[*_COMMON_FILES, "automation_flow.md"],
        build_destination="automation_runner",
    ),
    "website": ProjectMode(
        key="website",
        label="Website",
        capture_questions=[
            "What are the core pages or sections?",
            "Is this a static site or does it need a content management system?",
            "What brand assets and copy already exist?",
            "What domain will it be served on?",
        ],
        required_files=[*_COMMON_FILES, "project_preview.html"],
        build_destination="static_site",
    ),
    "funnel": ProjectMode(
        key="funnel",
        label="Funnel",
        capture_questions=[
            "What offer is the funnel selling?",
            "What are the funnel stages from first touch to conversion?",
            "Where does the traffic come from?",
            "What is the single conversion goal you measure?",
        ],
        required_files=[*_COMMON_FILES, "funnel_map.md"],
        build_destination="funnel_host",
    ),
    "data_pipeline": ProjectMode(
        key="data_pipeline",
        label="Data pipeline",
        capture_questions=[
            "What are the data sources?",
            "What transforms or enrichments are applied?",
            "Where does the processed data land?",
            "What schedule and data volume should it handle?",
        ],
        required_files=[*_COMMON_FILES, "pipeline_spec.md"],
        build_destination="data_warehouse",
    ),
    "campaign": ProjectMode(
        key="campaign",
        label="Campaign",
        capture_questions=[
            "Who is the target audience?",
            "Which channels will the campaign run on?",
            "What is the offer and the timeline?",
            "What budget and success metric apply?",
        ],
        required_files=[*_COMMON_FILES, "campaign_brief.md"],
        build_destination="campaign_manager",
    ),
    "content_system": ProjectMode(
        key="content_system",
        label="Content system",
        capture_questions=[
            "What content types does the system produce?",
            "What publishing cadence are you aiming for?",
            "Which channels does it distribute to?",
            "What voice and editorial rules must it follow?",
        ],
        required_files=[*_COMMON_FILES, "content_plan.md"],
        build_destination="content_library",
    ),
    "product_concept": ProjectMode(
        key="product_concept",
        label="Product concept",
        capture_questions=[
            "What problem does the concept solve, and for whom?",
            "Who is the specific target user?",
            "What makes it different from existing options?",
            "How will you validate demand before building?",
        ],
        required_files=[*_COMMON_FILES, "concept_brief.md"],
        build_destination="concept_doc",
    ),
}


@dataclass(frozen=True)
class ModeCheck:
    """One executor check for a mode: a name and the argv to run inside the worktree.

    The command is the toolchain a built project of that mode is expected to carry. The executor
    runs it in the isolated worktree; when the tool is not present, the check is recorded as
    unable to run rather than a pass, so a missing toolchain never reads as green.
    """

    name: str
    command: tuple[str, ...]


# Checks per mode, lint then build then test where applicable. Modes that produce no runnable
# artifact (campaign, content_system, product_concept, funnel) carry no checks. Kept separate
# from ProjectMode so adding checks is additive and does not rewrite the existing mode table.
MODE_CHECKS: dict[str, list[ModeCheck]] = {
    "app": [
        ModeCheck("lint", ("npm", "run", "lint")),
        ModeCheck("build", ("npm", "run", "build")),
        ModeCheck("test", ("npm", "test")),
    ],
    "website": [
        ModeCheck("lint", ("npm", "run", "lint")),
        ModeCheck("build", ("npm", "run", "build")),
    ],
    "automation": [ModeCheck("test", ("npm", "test"))],
    "data_pipeline": [ModeCheck("test", ("npm", "test"))],
}


def checks_for(key: str | None) -> list[ModeCheck]:
    """The executor checks for a mode, empty for modes that produce no runnable artifact."""
    return list(MODE_CHECKS.get(key or "", []))


def mode_keys() -> list[str]:
    return list(PROJECT_MODES.keys())


def is_valid_mode(key: str | None) -> bool:
    return key in PROJECT_MODES


def get_mode(key: str | None) -> ProjectMode:
    """Return the mode config, falling back to the default mode for unknown keys."""
    return PROJECT_MODES.get(key or "", PROJECT_MODES[DEFAULT_MODE])


def capture_questions_for(key: str | None) -> list[str]:
    return list(get_mode(key).capture_questions)


def required_files_for(key: str | None) -> list[str]:
    return list(get_mode(key).required_files)


def destination_for(key: str | None) -> str:
    return get_mode(key).build_destination
