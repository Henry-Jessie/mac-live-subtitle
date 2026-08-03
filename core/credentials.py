import json
from pathlib import Path

from core.paths import default_credentials_path

ASR_DASHSCOPE_ACCOUNT = "asr.dashscope"
TRANSLATION_ACCOUNTS = {
    "deepseek": "translation.deepseek",
    "google": "translation.google",
    "custom": "translation.custom",
}


def translation_account(provider: str) -> str:
    return TRANSLATION_ACCOUNTS[provider]


class CredentialStore:
    def __init__(self, path: Path | None = None):
        self.path = path or default_credentials_path()

    def get(self, account: str) -> str | None:
        return self._load().get(account)

    def exists(self, account: str) -> bool:
        return account in self._load()

    def save(self, account: str, value: str) -> None:
        secret = value.strip()
        if not secret:
            raise ValueError("API Key cannot be empty")
        values = self._load()
        values[account] = secret
        self._write(values)

    def delete(self, account: str) -> None:
        values = self._load()
        if account in values:
            del values[account]
            self._write(values)

    def _load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        with self.path.open(encoding="utf-8") as handle:
            values = json.load(handle)
        if not isinstance(values, dict) or not all(
            isinstance(account, str) and isinstance(secret, str)
            for account, secret in values.items()
        ):
            raise ValueError("Invalid credentials file")
        return values

    def _write(self, values: dict[str, str]) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path.parent.chmod(0o700)
        self.path.touch(mode=0o600, exist_ok=True)
        self.path.chmod(0o600)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(values, handle, ensure_ascii=False, indent=2)
            handle.write("\n")


credential_store = CredentialStore()
