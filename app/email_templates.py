"""Content for the transactional emails Trove sends.

SEPARATE FROM `app/email.py` ON PURPOSE. That module knows how to hand a message
to Resend and nothing about what any message says; this one is the exact
reverse. Rendering returns a value instead of sending one, so a test can assert
on a subject line, a link and a plain text part with no transport, no API key
and no network involved at all.

NO TEMPLATE ENGINE, AND NOT FOR BREVITY. Mail clients render inline `style`
attributes and little else — Gmail strips `<style>` blocks from the head, and
Outlook renders through Word's engine, which ignores most of what survives that.
So the separation of structure from presentation that a template language exists
to support is precisely the thing that cannot be used here. Two messages sharing
one layout function is the whole requirement; if notifications grow into a
family of templates, that is the moment to add Jinja, not before.

THE PALETTE IS trove-web's, CONVERTED. The app defines its colours as oklch
custom properties in `src/index.css`; oklch is unusable in mail, so the hex
values below are those same colours converted once. They are literals here
because there is no shared source to read at send time — if the app's palette
moves, these follow by hand.
"""

import html
from dataclasses import dataclass

# trove-web's --primary, --foreground, --muted-foreground, --background, --card,
# --border and --primary-foreground respectively.
_PRIMARY = "#9c5f32"
_TEXT = "#241c17"
_MUTED = "#68625e"
_PAGE_BG = "#f8f6f3"
_CARD_BG = "#fbfaf7"
_BORDER = "#e1ddd8"
_ON_PRIMARY = "#faf8f5"

# Inter is trove-web's --font-sans and Georgia stands in for its Cormorant
# Garamond --font-serif. Neither can be loaded: @font-face is stripped by most
# clients, so a webfont would render as the fallback anyway. Inter is named
# first for the clients that happen to have it locally, Georgia because it ships
# with essentially every mail client there is.
_SANS = "'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
_SERIF = "Georgia,'Times New Roman',serif"


@dataclass(frozen=True, slots=True)
class RenderedEmail:
    """One message, ready to send: a subject and both body parts."""

    subject: str
    html: str
    text: str


def _humanize_seconds(seconds: int) -> str:
    """Render a token lifetime the way the copy needs to read it.

    Whole hours become hours and everything else becomes minutes, which covers
    every value a token lifetime plausibly takes without inventing a duration
    formatter for the two that are actually used.
    """
    if seconds >= 3600 and seconds % 3600 == 0:
        hours = seconds // 3600
        return "1 hour" if hours == 1 else f"{hours} hours"
    minutes = max(1, round(seconds / 60))
    return "1 minute" if minutes == 1 else f"{minutes} minutes"


def _layout(
    *,
    subject: str,
    preheader: str,
    heading: str,
    paragraphs: list[str],
    button_label: str,
    url: str,
    footer: str,
) -> str:
    """Wrap one message's content in the shared HTML shell.

    TABLES, WHICH IS NOT AN ANACHRONISM HERE. Outlook's Word-based renderer
    supports neither flexbox nor grid, and a `<div>` layout collapses in it, so
    nested tables remain the only construct that centres a fixed-width card
    across every client.
    """
    safe_url = html.escape(url, quote=True)
    # Paragraphs are interpolated as markup, unlike every other value here,
    # because the copy above is module-local and occasionally wants an <a> or a
    # <strong> in it. Nothing a request supplies reaches this argument, and
    # nothing should start to — the URL is the only caller-supplied value and it
    # is escaped.
    body = "".join(
        f'<p style="margin:0 0 16px 0;font-size:15px;line-height:1.6;color:{_TEXT};">{p}</p>'
        for p in paragraphs
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(subject)}</title>
</head>
<body style="margin:0;padding:0;background-color:{_PAGE_BG};">
<div style="display:none;font-size:1px;color:{_PAGE_BG};line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;">{html.escape(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:{_PAGE_BG};">
<tr><td align="center" style="padding:32px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:520px;background-color:{_CARD_BG};border:1px solid {_BORDER};border-radius:10px;">
<tr><td style="padding:32px;font-family:{_SANS};">
<p style="margin:0 0 24px 0;font-family:{_SERIF};font-size:22px;letter-spacing:0.01em;color:{_PRIMARY};">Trove</p>
<h1 style="margin:0 0 16px 0;font-size:20px;font-weight:600;line-height:1.3;color:{_TEXT};">{html.escape(heading)}</h1>
{body}
<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:28px 0;">
<tr><td align="center" bgcolor="{_PRIMARY}" style="border-radius:8px;">
<a href="{safe_url}" style="display:inline-block;padding:12px 26px;font-family:{_SANS};font-size:15px;font-weight:600;color:{_ON_PRIMARY};text-decoration:none;border-radius:8px;">{html.escape(button_label)}</a>
</td></tr></table>
<p style="margin:0 0 6px 0;font-size:13px;line-height:1.6;color:{_MUTED};">Or paste this link into your browser:</p>
<p style="margin:0;font-size:13px;line-height:1.6;word-break:break-all;"><a href="{safe_url}" style="color:{_PRIMARY};">{safe_url}</a></p>
<hr style="border:none;border-top:1px solid {_BORDER};margin:24px 0 20px 0;">
<p style="margin:0;font-size:13px;line-height:1.6;color:{_MUTED};">{footer}</p>
</td></tr></table>
<p style="max-width:520px;margin:16px auto 0 auto;font-family:{_SANS};font-size:12px;line-height:1.6;color:{_MUTED};text-align:center;">Trove &mdash; your personal collection, catalogued.</p>
</td></tr></table>
</body>
</html>"""


def _plain_text(*, heading: str, paragraphs: list[str], url: str, footer: str) -> str:
    """Render the text alternative.

    EVERY MESSAGE CARRIES ONE. It is what a plain text client shows, what a
    screen reader may prefer, and what receivers expect of a legitimate sender —
    HTML-only mail scores worse with spam filters for no gain. The link sits on
    its own line so clients that linkify text do not swallow trailing
    punctuation into the URL.
    """
    blocks = [heading, *paragraphs, url, footer]
    return "\n\n".join(blocks) + "\n"


def password_reset(*, url: str, expires_in_seconds: int) -> RenderedEmail:
    """The message sent when someone asks to reset their password."""
    expiry = _humanize_seconds(expires_in_seconds)
    paragraphs = [
        "Someone asked to reset the password for the Trove account at this address. "
        f"Choose a new one with the link below, which expires in {expiry}.",
    ]
    # THE DISCLAIMER IS NOT BOILERPLATE. This message goes to an address supplied
    # by an unauthenticated request, so its recipient may well be someone who
    # did nothing — and for them the only useful information is that their
    # account is untouched and no action is needed.
    footer = (
        "If you did not ask for this, you can safely ignore this email. "
        "Your password will not change until you open the link above and set a new one."
    )
    return RenderedEmail(
        subject="Reset your Trove password",
        html=_layout(
            subject="Reset your Trove password",
            preheader=f"Choose a new password. This link expires in {expiry}.",
            heading="Reset your password",
            paragraphs=paragraphs,
            button_label="Choose a new password",
            url=url,
            footer=footer,
        ),
        text=_plain_text(
            heading="Reset your Trove password",
            paragraphs=paragraphs,
            url=url,
            footer=footer,
        ),
    )


def email_verification(*, url: str, expires_in_seconds: int) -> RenderedEmail:
    """The message sent to confirm ownership of an address."""
    expiry = _humanize_seconds(expires_in_seconds)
    paragraphs = [
        "Confirm this address to finish setting up your Trove account. "
        f"The link below expires in {expiry}.",
    ]
    footer = (
        "If you did not create a Trove account, you can safely ignore this email "
        "and nothing further will happen."
    )
    return RenderedEmail(
        subject="Verify your Trove email address",
        html=_layout(
            subject="Verify your Trove email address",
            preheader=f"Confirm your address. This link expires in {expiry}.",
            heading="Verify your email address",
            paragraphs=paragraphs,
            button_label="Verify email address",
            url=url,
            footer=footer,
        ),
        text=_plain_text(
            heading="Verify your Trove email address",
            paragraphs=paragraphs,
            url=url,
            footer=footer,
        ),
    )
