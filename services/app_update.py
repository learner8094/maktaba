import json
import os
import re
from pathlib import Path
from dataclasses import dataclass
from importlib import metadata
from typing import Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class AppUpdateInfo:
    current_version: str
    latest_version: str
    latest_url: str
    update_available: bool


class AppUpdater:
    """فحص تحديثات التطبيق عبر GitHub Releases."""

    def __init__(self, repo: Optional[str] = None):
        self.repo = repo or os.environ.get("MAKTABA_GITHUB_REPO", "learner8094/maktaba")

    def _read_json(self, url: str):
        req = Request(url, headers={"Accept": "application/vnd.github+json"})
        with urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _current_version(self) -> str:
        env_ver = os.environ.get("MAKTABA_VERSION")
        if env_ver:
            return env_ver
        try:
            return metadata.version("maktaba")
        except metadata.PackageNotFoundError:
            pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
            if pyproject.exists():
                text = pyproject.read_text(encoding="utf-8")
                m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
                if m:
                    return m.group(1)
            return "0.0.0"

    def _normalize(self, value: str) -> Tuple[int, ...]:
        clean = value.strip().lstrip("vV")
        nums = re.findall(r"\d+", clean)
        if not nums:
            return (0,)
        return tuple(int(n) for n in nums)

    def check_for_update(self) -> AppUpdateInfo:
        current = self._current_version()
        data = self._read_json(f"https://api.github.com/repos/{self.repo}/releases/latest")

        latest = data.get("tag_name") or data.get("name") or "0.0.0"
        latest_url = data.get("html_url") or f"https://github.com/{self.repo}/releases"
        available = self._normalize(latest) > self._normalize(current)

        return AppUpdateInfo(
            current_version=current,
            latest_version=latest,
            latest_url=latest_url,
            update_available=available,
        )

    def is_flatpak(self) -> bool:
        return bool(os.environ.get("FLATPAK_ID")) or os.path.exists("/.flatpak-info")

    def safe_check_for_update(self) -> AppUpdateInfo:
        try:
            return self.check_for_update()
        except (HTTPError, URLError) as e:
            raise RuntimeError(f"تعذر الاتصال بـ GitHub: {e}") from e
        except Exception as e:
            raise RuntimeError(f"فشل التحقق من تحديث التطبيق: {e}") from e
