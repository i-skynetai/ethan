"""Optional explicit bearer configuration; never generates or persists a token."""
from dataclasses import dataclass, field
import hmac
import os
import re
import urllib.request
from urllib.parse import urlsplit

ENV_NAME = "ETHAN_LOCAL_API_TOKEN"
_TOKEN = re.compile(r"[A-Za-z0-9._~+/=-]{32,4096}", re.ASCII)


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class Auth:
    _token: bytes | None = field(default=None, repr=False)

    @classmethod
    def from_environment(cls, environ=None):
        env = os.environ if environ is None else environ
        if ENV_NAME not in env:
            return cls()
        token = env[ENV_NAME]
        if not isinstance(token, str) or not _TOKEN.fullmatch(token):
            raise ConfigurationError("ETHAN_LOCAL_API_TOKEN must be 32–4096 ASCII bearer-safe characters; configuration refused.")
        return cls(token.encode("ascii"))

    @property
    def enabled(self):
        return self._token is not None

    def __repr__(self):
        return f"Auth(enabled={self.enabled})"

    def authorized(self, authorization_values):
        if not self.enabled:
            return True
        if hasattr(authorization_values, "get_all"):
            authorization_values = authorization_values.get_all("Authorization", [])
        elif hasattr(authorization_values, "items"):
            authorization_values = [v for k, v in authorization_values.items()
                                    if isinstance(k, str) and k.lower() == "authorization"]
        if not isinstance(authorization_values, (list, tuple)) or len(authorization_values) != 1:
            return False
        value = authorization_values[0]
        if not isinstance(value, str) or len(value) > 4103:
            return False
        scheme, separator, token = value.partition(" ")
        if scheme.lower() != "bearer" or separator != " " or not _TOKEN.fullmatch(token):
            return False
        return hmac.compare_digest(self._token, token.encode("ascii"))

    def request_headers(self):
        return {"Authorization": "Bearer " + self._token.decode("ascii")} if self.enabled else {}


def load(environ=None):
    """Snapshot explicit configuration when called, never at module import."""
    return Auth.from_environment(environ)


def child_environment(environ=None):
    """Copy an environment without granting a child the local API bearer."""
    env = os.environ if environ is None else environ
    return {key: value for key, value in env.items() if key.upper() != ENV_NAME}


def _local_url(url):
    if not isinstance(url, str) or any(ord(c) < 32 or ord(c) == 127 for c in url):
        raise ValueError("Only a local HTTP console URL is permitted.")
    parsed = urlsplit(url)
    try:
        port = parsed.port if parsed.port is not None else 80
    except ValueError as e:
        raise ValueError("Invalid local console port.") from e
    if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost")
            or parsed.username or parsed.password or parsed.fragment or not 1 <= port <= 65535):
        raise ValueError("Only a local HTTP console URL is permitted.")
    return url


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def request(url, *, data=None, method=None, timeout=20, headers=None):
    """Explicit configured credentials go only to loopback, without proxy/redirect."""
    url = _local_url(url)                       # validate before even reading auth
    outgoing = dict(headers or {})
    outgoing.update(load().request_headers())
    req = urllib.request.Request(url, data=data, method=method, headers=outgoing)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    return opener.open(req, timeout=timeout)
