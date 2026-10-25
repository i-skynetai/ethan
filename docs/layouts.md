# A dashboard layout is display configuration

The first dynamic-layout slice has six approved card types: agents, tasks, approvals,
activity, conversation and core. Each has one stable instance ID matching its type.
Core and conversation cannot be removed, retyped, retitled or resized, and core
remains before conversation. Other cards can be added from the registry, hidden,
reordered, resized to one or two columns and given a plain title of at most 64
characters. The renderer supplies the data; configuration cannot choose arbitrary
HTML, JavaScript, URLs, connectors or data bindings.

The schema is `{version: 1, widgets: [{id, type, width, title}]}` with at most six
cards. Unknown fields/types, repeated instances, invalid mandatory cards, Boolean
widths/revisions and malformed titles are refused. An invalid layout already on disk
falls back to the fixed safe default and reports recovery. No code runs from a layout.

## Preview before application

Typed rules such as `hide tasks`, `show activity`, `move agents before tasks` and
`reset dashboard` create a preview only. The response includes the proposed diff,
the current revision, an exact preview ID and expiry. Nothing visible is changed
until the person explicitly sends `apply dashboard <preview-id>` from the originating
conversation and door. Previews expire after ten minutes and can be consumed once.
Scheduled asks cannot reach these rules through the router.

The local API can also explicitly apply an exact validated layout with its expected
previous revision. If another update landed first, the application is refused and a
fresh preview is needed. Previews, immutable revisions and their previous-revision
links are stored in the existing Ethan SQLite ledger. Rollback validates the previous
layout and creates a new revision rather than rewriting history. It also requires
the expected current revision.

These changes affect presentation only. Hiding an approval card never approves an
action; showing an agent card never starts or contacts a session. The normal backend
policy, approvals and orchestration remain authoritative. Loopback HTTP protections
do not authenticate other local processes; layout configuration does not add identity.

## Verification

Ten isolated backend tests cover preview without mutation of the current layout,
add/order/resize/title configuration, schema limits, mandatory cards, unknown bindings,
wrong conversation/door, expiry, replay, stale and Boolean revisions, corrupt stored
data, validated rollback, restart persistence and exactly one winner for concurrent
applications of the same previous revision. HUD/API and typed-router integration need
their separate end-to-end checks; a module test is not visual QA.
