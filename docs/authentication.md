# Optional local API authentication — preparation only

This code is prepared and tested with synthetic credentials. Authentication remains
disabled when `ETHAN_LOCAL_API_TOKEN` is absent. This work did not generate a token,
set a live service environment, persist credentials, grant access or restart the
running service. Live activation remains a separate maintainer decision (EH-042).

The server snapshots explicit configuration when its console is created. A present
but empty or invalid value refuses startup; there is no fallback token. Configured
values must contain 32–4096 ASCII bearer-safe characters without whitespace or control
characters. No credential is generated, written to disk, injected into the page,
placed in a URL or printed by the authentication helper.

When enabled, API GET and POST handlers require exactly one Authorization header
using the Bearer scheme and the exact configured value. Comparison uses
`hmac.compare_digest`. Missing, malformed, duplicate or incorrect headers receive
a generic 401 and a closed connection before API state or request-body processing.
Cookies and URL parameters are not authentication. Static HTML and assets remain
public. Existing loopback Host, Origin, framing and body checks continue to apply.

The browser accepts a manually entered owner-provided token into tab memory only;
it does not save it in localStorage, a cookie or a URL. Reload requires re-entry.
Forgetting it clears the tab's access value; it does not rotate the server token or
revoke other clients or stop an active microphone capture. Stop or mute capture
separately before forgetting access. Browser extensions, developer tools and a compromised page or
OS account are outside this protection.

CLI and desktop HTTP clients use only an explicitly supplied process environment
value. They validate the loopback HTTP destination before reading configuration,
ignore proxy settings and refuse redirects. Headers go to `localhost` or
`127.0.0.1` only. CLI help requires neither a service nor a token. A 401 is reported
as an authentication requirement; the desktop launcher does not start a duplicate
backend when an existing service refuses authentication. The browser window still
requires manual entry; the launcher does not put the environment token into its URL.

The local bearer is explicitly removed from harness, message-bridge, browser and
speech-helper child environments. Even a misconfigured KB PAT-variable name cannot
pass this bearer to a hand. Only an explicitly launched Python service retains the
owner's environment configuration; unrelated child processes do not receive this
API credential. Synthetic subprocess tests check these boundaries without launching
agents, browsers or microphone capture.

## Proposed activation and rotation, not executed

1. Obtain separate owner approval for the actual credential and planned service
   restart. The owner supplies a cryptographically random token through an approved
   process-environment mechanism; this code does not generate it or save it. Do not
   place the value in chat, command arguments, a URL, source files or on disk.
2. Start or restart the intended local service with that explicit environment value.
   It is snapshotted at console startup. A later environment change does not alter
   the running service's verifier.
3. Give only authorized CLI/desktop clients the same explicit process environment
   configuration. Enter it manually in the browser's access field; never in the
   conversation composer. The desktop launcher does not unlock the browser tab.
4. Verify refusal without a header and access with the intended credential using an
   owner-approved local check. Token possession grants existing owner API rights;
   it is not a per-client authorization policy.
5. Rotation requires an approved service restart with a new random token. Old tokens
   then fail against that service instance, and authorized clients must be updated.
   Forgetting a browser tab does not revoke other clients or rotate the verifier.

There is no persistent enforcement setting: if the variable is omitted on a future
restart, the service returns to disabled compatibility mode. The owner must supply
it every intended authenticated start. A present invalid value fails startup instead.
Process environment and memory can be read by a compromised same-user process, and
the transport is plaintext loopback HTTP, not protection against OS compromise or
remote hosting. These implications require an explicit activation decision.

A token holder has the existing service owner's API rights. This is not per-client
roles, principal-bound permissions or protection from another process running as
the same OS user, which may read environment variables or memory. Loopback HTTP is
not remote hosting or a transport-encryption scheme. Approval checks remain separate
from API access; possession of this token does not consume an action approval.

Tests cover synthetic startup snapshots, invalid configuration, constant-time
comparison, duplicate headers, unauthorized API refusal before work, retained Origin
checks, protected client headers and local-only transport. No real credential or
microphone access is needed for these tests.
