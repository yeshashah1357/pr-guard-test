from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import Role, RunStatus, Severity


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    email: EmailStr
    # bcrypt only looks at the first 72 bytes, so longer passwords are rejected.
    password: str = Field(min_length=8, max_length=72)


class UserOut(ORM):
    id: int
    email: str
    role: Role


class RoleUpdate(BaseModel):
    role: Role


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 (OAuth2 token type, not a secret)


class RepositoryCreate(BaseModel):
    full_name: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", max_length=200)


class RepositoryOut(ORM):
    id: int
    full_name: str
    is_active: bool
    last_event_at: datetime | None


class RepositoryCheck(BaseModel):
    full_name: str
    found: bool
    private: bool | None
    already_registered: bool
    message: str


class WebhookSetup(BaseModel):
    webhook_url: str | None
    content_type: str = "application/json"
    events: list[str] = ["Pull requests"]
    # The secret itself never leaves the server; this says where an admin finds it.
    secret_location: str = "GITHUB_WEBHOOK_SECRET in the server's .env file"  # noqa: S105 (a hint, not a secret)


class FindingOut(ORM):
    id: int
    run_id: int
    tool: str
    rule_id: str
    severity: Severity
    file_path: str
    line: int
    message: str
    suggestion: str | None
    confidence: str | None
    created_at: datetime


class FindingRow(FindingOut):
    repository: str
    pr_number: int
    pr_url: str


class FindingPage(BaseModel):
    items: list[FindingRow]
    total: int


class RunOut(ORM):
    id: int
    head_sha: str
    status: RunStatus
    notes: str | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None


class PullRequestSummary(ORM):
    id: int
    number: int
    title: str
    author: str
    # Empty for pull requests that don't exist on GitHub, such as the offline demo's.
    html_url: str
    repository_name: str


class RunDetail(RunOut):
    pull_request: PullRequestSummary
    findings: list[FindingOut]


class PullRequestOut(PullRequestSummary):
    latest_run: RunOut | None


class TrendPoint(BaseModel):
    day: date
    severity: Severity
    count: int


# --- GitHub webhook payload: only the fields we use ---


class _GHUser(BaseModel):
    login: str


class _GHHead(BaseModel):
    sha: str


class _GHPullRequest(BaseModel):
    number: int
    title: str
    html_url: str
    user: _GHUser
    head: _GHHead


class _GHRepository(BaseModel):
    full_name: str


class PullRequestEvent(BaseModel):
    action: str
    pull_request: _GHPullRequest
    repository: _GHRepository
