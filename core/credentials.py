from keyring.backends.macOS import Keyring


KEYCHAIN_SERVICE = "com.henryjessie.MacLiveSubtitle.credentials"
ASR_DASHSCOPE_ACCOUNT = "asr.dashscope"
TRANSLATION_ACCOUNTS = {
    "deepseek": "translation.deepseek",
    "google": "translation.google",
    "custom": "translation.custom",
}


def infer_translation_provider(base_url: str | None) -> str:
    normalized = (base_url or "").rstrip("/")
    if normalized == "https://api.deepseek.com/v1":
        return "deepseek"
    if normalized == "https://generativelanguage.googleapis.com/v1beta/openai":
        return "google"
    return "custom"


def translation_account(provider: str) -> str:
    return TRANSLATION_ACCOUNTS[provider]


class CredentialStore:
    def __init__(self, service: str = KEYCHAIN_SERVICE):
        self._service = service
        self._keyring = Keyring()

    def get(self, account: str) -> str | None:
        return self._keyring.get_password(self._service, account)

    def save(self, account: str, value: str) -> None:
        secret = value.strip()
        if not secret:
            raise ValueError("API Key cannot be empty")
        self._keyring.set_password(self._service, account, secret)

    def delete(self, account: str) -> None:
        if self.get(account) is not None:
            self._keyring.delete_password(self._service, account)


credential_store = CredentialStore()
