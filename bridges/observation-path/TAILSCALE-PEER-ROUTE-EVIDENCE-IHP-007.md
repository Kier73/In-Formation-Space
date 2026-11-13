# Tailscale peer-route evidence from the E-CPU application session

**Experiment:** IHP-007  
**Status:** implementation and CI validation in progress; live IHP-006 tailnet run pending  
**Depends on:** IHP-006 E-CPU mTLS operation path over Tailscale  
**Question:** Can each application host independently record the Tailscale path class associated with the exact peer socket used for a successful mTLS operation, and can a third verifier bind those observations to the same reciprocal socket endpoints?

## Motivation

IHP-005 probes overlay reachability before application transport. IHP-006 carries a signed E-CPU operation over the actual Tailscale TCP endpoint and completes mutual TLS, ReliableChannel delivery, ACK, a signed receiver receipt, and third-host reconstruction.

There was still a useful gap between the two: a route probe performed before the application exchange does not tell us which path class was active for the later application session. Tailscale can use a direct path, a DERP relay, or a peer relay. These are all valid encrypted overlay routes; route class is not an application-authentication result.

IHP-007 adds a local route observation immediately after each participant establishes the authenticated socket. The observation is embedded in the participant's E-CPU operation span. It is therefore covered by the existing signed sender envelope or receiver receipt and by the host-record attestation. The verifier then compares the two peers' socket addresses and reports the two route classifications independently.

## Observation method

Each IHP-006 participant obtains the local and peer IPv4 addresses from its live TLS socket:

- client: socket local address and the signed server endpoint address;
- server: socket local address and the signed endpoint address it advertised, with the client address taken from the accepted socket peer.

The participant then runs `tailscale status` and selects the peer row whose first column exactly matches the socket's peer Tailscale IPv4 address. The documented status column identifies whether traffic is active and, when known, whether the connection is `direct`, `relay`, or `peer-relay`.

The parser is intentionally conservative:
- `active; direct` becomes `direct`;
- `active; relay` becomes `derp_relay`;
- `active; peer-relay` becomes `peer_relay`;
- an active row with an unfamiliar marker, an idle row, a missing row, duplicate peer rows, or a failed status command remains `reachable_unclassified`; duplicate rows are also marked `ambiguous`.

This avoids turning an idle or changed CLI format into a false assertion that the application session was unavailable. The mTLS socket itself is the application reachability evidence; the status snapshot supplies only the route-class observation.

## Evidence and privacy

Each host's operation-span context contains one `peer_route_observation` with:
- observer role;
- local and peer Tailscale IPv4 addresses from the live TLS socket;
- status state and normalized route type;
- command name, exit code, local elapsed nanoseconds;
- a local monotonic coordinate and elapsed nanoseconds for the status observation;
- a SHA-256 digest of the complete `tailscale status` stdout;
- a short error marker when the status command could not be completed.

The complete CLI output is not copied into the public host record. The matching peer row can contain device names, owner emails, operating-system labels, public direct endpoints, and relay region identifiers. The observation therefore retains only the normalized route marker and the digest commitment to the full output. This provides a repeatable classification result without exporting the rest of the tailnet inventory.

The route observation is not an independent signature on its own. Its integrity comes from its placement inside the measured E-CPU operation span: the client span is bound into the sender's Ed25519-signed handoff envelope, and the server span is bound into the receiver's signed receipt. The two host records are then covered by GitHub artifact attestations, and the third verifier checks their span digests and route observations.

## Independent reconstruction

The third verifier requires both observations for a successful IHP-006 mTLS report and checks the reciprocal endpoint relations:

```text
client.local_overlay_ipv4 == server.peer_overlay_ipv4
client.peer_overlay_ipv4  == server.local_overlay_ipv4
client.peer_overlay_ipv4  == signed_server_endpoint.host
server.local_overlay_ipv4 == signed_server_endpoint.host
```

Only after those bindings match does the report include the pair under `direct_transport.peer_route_observations`. The two route classes remain separate. If the client and server snapshots differ, the report records `asymmetric: true`; it does not silently choose one side or average them.

This reconstruction establishes that both participants' route observations refer to the same two socket endpoints. It does not prove that Tailscale's status snapshot is a packet-level trace of every TCP segment. It also does not establish cross-host timing: the elapsed time for `tailscale status` is measured independently on each host, and no shared physical clock is assumed.

## Interpretation

- `direct`: the matching peer row reported a direct Tailscale path.
- `derp_relay`: the matching peer row reported a DERP relay.
- `peer_relay`: the matching peer row reported a Tailscale peer relay.
- `reachable_unclassified`: the application socket exists, but the status row was inactive, absent, unavailable, or did not contain a recognized route marker.
- `asymmetric: true`: client and server reported different route classes at their respective observation times.

A DERP or peer-relay result does not mean plaintext fallback. Tailscale's WireGuard layer continues to protect overlay traffic; the application still independently authenticates both participants with mTLS and checks each live peer certificate fingerprint against its attested bootstrap certificate.

## Reproduction

The evidence is produced by the existing manually dispatched workflow:

`.github/workflows/tailscale-mtls-operation-path.yml`

Implementation and tests:

- `bridges/observation-path/direct_mtls_operation_path.py`
- `bridges/observation-path/test_direct_mtls_operation_path.py`
- `bridges/observation-path/direct-mtls-host-record.schema.json`

The existing IHP-006 workflow identity, tag, TCP-only grant, signed endpoint, and three-host verification topology are unchanged. The original IHP-002 public endpoint workflow does not run Tailscale status and retains its prior record shape.

## Official Tailscale references

- [Tailscale CLI: status](https://tailscale.com/docs/reference/tailscale-cli) — human-readable peer status distinguishes direct, relay, and peer-relay connections; JSON output is available but its schema is documented as subject to change.
- [Connection types](https://tailscale.com/docs/reference/connection-types) — explains how to determine the connection type from status or ping.
- [DERP routing diagnostics](https://tailscale.com/docs/reference/troubleshooting/network-configuration/derp-routing) — examples of the status and ping output for direct and DERP-relayed paths.
