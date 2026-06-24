"""yt_newsletter — turn recent YouTube uploads into a deep, readable email digest.

Cookie-free pipeline: a channel's RSS feed lists recent uploads, the transcript
API pulls the words, Claude turns the transcript into near-complete study notes,
and the renderer builds an email-friendly HTML digest.
"""

__all__ = ["models", "config", "sources", "transcript", "summarize", "render", "pipeline"]
