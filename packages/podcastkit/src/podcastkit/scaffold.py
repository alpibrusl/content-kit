from __future__ import annotations

import shutil
from pathlib import Path

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def scaffold_project(name: str, dest: Path, num_episodes: int = 1) -> None:
    """Create a new podcast project directory at dest.

    Creates the top-level project folder plus one sub-directory per episode,
    each pre-populated with episode.yaml and script.json templates.
    """
    dest.mkdir(parents=True, exist_ok=True)
    for ep_num in range(1, num_episodes + 1):
        scaffold_episode(dest / f"episode_{ep_num:02d}", ep_num)


def scaffold_episode(episode_dir: Path, episode_num: int) -> None:
    """Write episode.yaml and script.json templates into episode_dir.

    If episode.yaml already exists it is left untouched. script.json is
    likewise preserved so existing work is never clobbered.
    """
    episode_dir.mkdir(parents=True, exist_ok=True)

    yaml_src = _TEMPLATES_DIR / "episode.yaml"
    json_src = _TEMPLATES_DIR / "script.json"

    yaml_dest = episode_dir / "episode.yaml"
    json_dest = episode_dir / "script.json"

    if not yaml_dest.exists():
        shutil.copy2(yaml_src, yaml_dest)

    if not json_dest.exists():
        shutil.copy2(json_src, json_dest)
