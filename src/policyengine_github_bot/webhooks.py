"""GitHub webhook handlers."""

import hashlib
import hmac

import logfire
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import ValidationError

from policyengine_github_bot.config import get_settings
from policyengine_github_bot.github_auth import get_github_client
from policyengine_github_bot.llm import generate_issue_response
from policyengine_github_bot.models import IssueWebhookPayload

router = APIRouter()


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify the GitHub webhook signature."""
    if not signature.startswith("sha256="):
        prefix = signature[:10] if signature else "empty"
        logfire.warn("Invalid signature format", signature_prefix=prefix)
        return False

    expected = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(f"sha256={expected}", signature)


def fetch_claude_md(github, repo_full_name: str) -> str | None:
    """Fetch CLAUDE.md from a repository if it exists."""
    try:
        repo = github.get_repo(repo_full_name)
        contents = repo.get_contents("CLAUDE.md")
        logfire.info("Found CLAUDE.md", repo=repo_full_name, size=len(contents.decoded_content))
        return contents.decoded_content.decode("utf-8")
    except Exception as e:
        logfire.info("No CLAUDE.md found", repo=repo_full_name, error=str(e))
        return None


@router.post("/webhook")
async def handle_webhook(
    request: Request,
    x_hub_signature_256: str = Header(None),
    x_github_event: str = Header(None),
):
    """Handle incoming GitHub webhooks."""
    settings = get_settings()
    payload = await request.body()

    logfire.info("Webhook received", event=x_github_event, payload_size=len(payload))

    # Verify webhook signature
    if not verify_signature(payload, x_hub_signature_256 or "", settings.github_webhook_secret):
        logfire.error("Webhook signature verification failed", event=x_github_event)
        raise HTTPException(status_code=401, detail="Invalid signature")

    logfire.info("Webhook signature verified", event=x_github_event)

    data = await request.json()

    if x_github_event == "issues":
        await handle_issue_event(data)
    elif x_github_event == "ping":
        logfire.info("Ping received", zen=data.get("zen", ""))
        return {"status": "pong"}
    else:
        logfire.info("Unhandled event type", event=x_github_event)

    return {"status": "ok"}


async def handle_issue_event(data: dict):
    """Handle issue events."""
    # Validate payload with pydantic
    try:
        payload = IssueWebhookPayload.model_validate(data)
    except ValidationError as e:
        logfire.error("Invalid issue webhook payload", errors=e.errors())
        return

    logfire.info(
        "Issue event received",
        action=payload.action,
        repo=payload.repository.full_name,
        issue_number=payload.issue.number,
        issue_title=payload.issue.title,
        sender=payload.sender.login,
    )

    # Only respond to newly opened issues
    if payload.action != "opened":
        logfire.info(
            "Ignoring issue event",
            action=payload.action,
            reason="not an 'opened' action",
        )
        return

    if not payload.installation:
        logfire.error(
            "No installation ID in webhook payload",
            repo=payload.repository.full_name,
            issue_number=payload.issue.number,
        )
        return

    with logfire.span(
        "handle_new_issue",
        repo=payload.repository.full_name,
        issue_number=payload.issue.number,
        issue_title=payload.issue.title,
    ):
        # Get authenticated GitHub client
        logfire.info("Authenticating with GitHub", installation_id=payload.installation.id)
        github = get_github_client(payload.installation.id)

        # Fetch CLAUDE.md for context
        with logfire.span("fetch_claude_md", repo=payload.repository.full_name):
            claude_md = fetch_claude_md(github, payload.repository.full_name)

        # Generate response
        with logfire.span("generate_response", issue_number=payload.issue.number):
            response_text = await generate_issue_response(
                issue=payload.issue,
                repo_context=claude_md,
            )

        # Post comment
        with logfire.span("post_comment", issue_number=payload.issue.number):
            logfire.info(
                "Posting comment",
                repo=payload.repository.full_name,
                issue_number=payload.issue.number,
                response_length=len(response_text),
            )
            gh_repo = github.get_repo(payload.repository.full_name)
            gh_issue = gh_repo.get_issue(payload.issue.number)
            gh_issue.create_comment(response_text)

        logfire.info(
            "Successfully responded to issue",
            repo=payload.repository.full_name,
            issue_number=payload.issue.number,
        )
