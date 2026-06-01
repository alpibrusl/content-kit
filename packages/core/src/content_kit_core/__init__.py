"""content-kit-core — the shared spine of the content platform.

Everything here is renderer-agnostic and depended on by every tool in the
platform (bookkit, podcastkit, and future media tiers): the CLI output/exit-code
conventions, the LLM-agnostic ``Writer`` factory, the canonical *bridge*
contracts that one tool produces and another consumes (``EpisodeConfig`` /
``script.json``, the storyboard, the story bible), and the shared error type.

Core never imports a renderer — the dependency arrow points one way. The link
between tools stays a *data* contract (a written artifact validated against the
models here), never a function call, so the tools remain decoupled siblings.
"""

from __future__ import annotations

VERSION = "0.1.0"
