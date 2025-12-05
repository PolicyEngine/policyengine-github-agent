"""Pydantic models for GitHub webhook payloads."""

from pydantic import BaseModel, Field


class GitHubUser(BaseModel):
    """GitHub user information."""

    login: str
    id: int


class GitHubRepository(BaseModel):
    """GitHub repository information."""

    id: int
    name: str
    full_name: str
    private: bool = False


class GitHubIssue(BaseModel):
    """GitHub issue information."""

    id: int
    number: int
    title: str
    body: str | None = None
    state: str = "open"
    user: GitHubUser


class GitHubInstallation(BaseModel):
    """GitHub App installation information."""

    id: int


class GitHubComment(BaseModel):
    """GitHub comment information."""

    id: int
    body: str
    user: GitHubUser


class IssueWebhookPayload(BaseModel):
    """Payload for issue webhook events."""

    action: str
    issue: GitHubIssue
    repository: GitHubRepository
    installation: GitHubInstallation | None = None
    sender: GitHubUser


class IssueCommentWebhookPayload(BaseModel):
    """Payload for issue_comment webhook events."""

    action: str
    issue: GitHubIssue
    comment: GitHubComment
    repository: GitHubRepository
    installation: GitHubInstallation | None = None
    sender: GitHubUser


class PingWebhookPayload(BaseModel):
    """Payload for ping webhook events."""

    zen: str = ""
    hook_id: int = 0


class GitHubPullRequest(BaseModel):
    """GitHub pull request information."""

    id: int
    number: int
    title: str
    body: str | None = None
    state: str = "open"
    user: GitHubUser
    head: dict  # contains sha, ref, repo info
    base: dict  # contains sha, ref, repo info


class PullRequestWebhookPayload(BaseModel):
    """Payload for pull_request webhook events."""

    action: str
    pull_request: GitHubPullRequest
    repository: GitHubRepository
    installation: GitHubInstallation | None = None
    sender: GitHubUser


class PullRequestReviewWebhookPayload(BaseModel):
    """Payload for pull_request_review webhook events."""

    action: str
    review: dict
    pull_request: GitHubPullRequest
    repository: GitHubRepository
    installation: GitHubInstallation | None = None
    sender: GitHubUser


class IssueResponse(BaseModel):
    """Response generated for an issue."""

    content: str = Field(description="The response text to post as a comment")


class PRReviewComment(BaseModel):
    """A single inline comment on a PR."""

    path: str = Field(description="The file path relative to repo root")
    line: int = Field(description="The line number in the diff to comment on")
    body: str = Field(description="The comment text")


class PRReviewResponse(BaseModel):
    """Response generated for a PR review."""

    summary: str = Field(description="Overall summary of the review")
    approval: str = Field(description="One of: APPROVE, REQUEST_CHANGES, or COMMENT")
    comments: list[PRReviewComment] = Field(
        default_factory=list,
        description="Inline comments on specific lines",
    )


class ThreadAction(BaseModel):
    """Action to take on an existing review thread during re-review."""

    thread_index: int = Field(description="Index of the thread from the provided list")
    action: str = Field(description="One of: RESOLVE (issue fixed), REPLY (needs response)")
    reply: str | None = Field(
        default=None,
        description="Reply text if action is REPLY (e.g. 'Still not addressed' or a follow-up)",
    )


class PRReReviewResponse(BaseModel):
    """Response for a re-review of a PR."""

    thread_actions: list[ThreadAction] = Field(
        default_factory=list,
        description="Actions to take on existing open threads",
    )
    new_comments: list[PRReviewComment] = Field(
        default_factory=list,
        description="New inline comments on lines not previously commented on",
    )
    summary: str | None = Field(
        default=None,
        description="Optional summary if posting a new review (only if new_comments exist)",
    )
    approval: str | None = Field(
        default=None,
        description="One of: APPROVE, REQUEST_CHANGES, COMMENT - only if posting new review",
    )
