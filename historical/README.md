# Original upstream release rebuilds

This tooling is separate from the product source. It checks out each original
upstream commit in `original/` and refuses a modified product tree.

| Tag | Exact product commit | Original asset matrix |
| --- | --- | --- |
| v1.0.0 | 30f0afde2082b18fb4fec0e79a5c8282eb14f308 | Linux no_units / with_units |
| v1.1.0 | 399136d91394fc838e813147438e822d8418233c | Linux no_units / with_units; Windows no_units |

The host is PlotJuggler 3.9.2. Linux builds run in Ubuntu 22.04 x86-64;
Windows builds use Qt 5.15.2 and MSVC x86-64. Host caches are isolated by the
verified full PlotJuggler source SHA and contain an identity marker checked before
packaging. Historical source omits some
standard headers, so Linux explicitly passes `-include array -include cstring`.
This changes no product-source file and backports no parser feature.

The build workflow validates actual final shared libraries with Qt DataLoader
loading, real BIN parsing, and exact unit-label assertions. Each CI artifact
contains SOURCE.json, full original license, and one native binary. The promotion
workflow requires the exact successful build source, run and attempt, original
upstream/fork tag identity, and all five plugin jobs. It promotes the same bytes;
it never rebuilds, moves a tag, or overwrites an existing Release.

Public downloads preserve the original bare-library naming and matrix. Their
single README-licenses.txt includes exact per-binary provenance and licenses;
SHA256SUMS covers every library and this README. Public URLs are downloaded
without authentication after publication. Historical releases never replace
v1.2.0 as Latest. These are source rebuilds, not mirrors or byte-identical copies
of upstream binaries. Old-source limitations remain; no PJ4 SDK compatibility
is claimed.

## Published release verification — 2026-10-20

### Result and exact identities

Both original-tag rebuilds are published:
[v1.0.0](https://github.com/reliable-ly0411/plotjuggler-apbin-plugins/releases/tag/v1.0.0)
and [v1.1.0](https://github.com/reliable-ly0411/plotjuggler-apbin-plugins/releases/tag/v1.1.0).
The public library filenames and two-/three-library matrices match the
corresponding upstream Releases exactly. No additional binary variant was added.
The only supplemental downloads are SHA256SUMS and one README-licenses.txt.

- v1.0.0 product and unchanged fork/upstream tag:
  `30f0afde2082b18fb4fec0e79a5c8282eb14f308`.
- v1.1.0 product and unchanged fork/upstream tag:
  `399136d91394fc838e813147438e822d8418233c`.
- Candidate build tooling:
  `6a30016daacf0ae7a140bf77301cb5936a8a2903`.
- Promotion workflow:
  `31cd66bd2d09ebbeefae24611b00a63ee1d8203d`.
- PlotJuggler host: 3.9.2,
  `d115b540c4f2664259a594259b9e11595f0263fc`,
  repository `PlotJuggler/PlotJuggler`.
- Original build:
  [run 39360759728, attempt 1](https://github.com/reliable-ly0411/plotjuggler-apbin-plugins/actions/runs/39360759728).
- v1.0.0 promotion and anonymous download verification:
  [run 39376007356](https://github.com/reliable-ly0411/plotjuggler-apbin-plugins/actions/runs/39376007356).
- v1.1.0 promotion and anonymous download verification:
  [run 39376086438](https://github.com/reliable-ly0411/plotjuggler-apbin-plugins/actions/runs/39376086438).

The build run has seven successful jobs: two host builds and five final plugin
jobs. Each plugin job passed exact-source checks, dynamic Qt DataLoader loading,
real BIN parsing, and unit-label variant assertions before collecting the native
library. The two promotion jobs each passed 23 guard tests and then uploaded
the original candidate bytes without recompiling.

### Independent public-download check

At 2026-10-20T05:42:00.586991+00:00, all nine public assets were downloaded without
authentication through their ordinary GitHub Release download URLs. For every
file, the downloaded byte count and SHA-256 matched the Release API record.
Every native library also matched its original candidate SOURCE.json. Both
SHA256SUMS files cover exactly their native libraries plus README-licenses.txt.

Each README includes the exact product, build-tooling, host-source and per-binary
identities, original attribution and complete LGPL/GPL/MPL license text. The full
original upstream Release body is retained in each corresponding fork Release.
The candidate ZIP digests were independently checked before promotion.

| Release | Public file | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| v1.0.0 | `libDataAPBin_no_units_v1.0.0.so` | 2319736 | `4515995f9fce47f747bacd88190b6c1be90c0abe211a14e6a7f995b34c68851e` |
| v1.0.0 | `libDataAPBin_with_units_v1.0.0.so` | 2319648 | `f17eb2d809c7a5d26855504e5f8b47147944d6f854c4e825b1f753e89392bfcd` |
| v1.0.0 | `README-licenses.txt` | 63360 | `4293646f04bde17ee72f3024555098a8019b1a6aa5df5e5ab43b768e542e248a` |
| v1.0.0 | `SHA256SUMS` | 284 | `3ab18259768ec7acd5ef407d3069b2966cf227ba27940f0d3716ba631a417ced` |
| v1.1.0 | `DataAPBin_no_units.dll` | 78336 | `c95b36e55c81a44b82346f81c5a48218b1f030fa721f8ce426fe185687a27c2e` |
| v1.1.0 | `libDataAPBin_no_units.so` | 2319736 | `4515995f9fce47f747bacd88190b6c1be90c0abe211a14e6a7f995b34c68851e` |
| v1.1.0 | `libDataAPBin_with_units.so` | 2319648 | `f17eb2d809c7a5d26855504e5f8b47147944d6f854c4e825b1f753e89392bfcd` |
| v1.1.0 | `README-licenses.txt` | 64270 | `67001adc45227ca0aa2be35477d0755752f7152823c9bd638025f82afabb6280` |
| v1.1.0 | `SHA256SUMS` | 359 | `0d9d65b87608d0f1f9abc03359eeafdc5bfaa08751579b229defca3dcca9415f` |

### Durable candidate archive identities

These are GitHub Actions artifact ZIP digests, distinct from the native-library
hashes above. The CI artifacts were unexpired at verification.

| Artifact ID | Artifact name | ZIP SHA-256 |
| --- | --- | --- |
| 12237991055 | `historical-v1.1.0-ubuntu-22.04-with_units` | `7f16bbaac5b169a94412ac1a0bede6425a467618962e34dd54d68c3df402e0a1` |
| 12237971221 | `historical-v1.1.0-windows-2022-no_units` | `12104befd945c638b55a269c4d9884d157d728d3d4159808c000e1bd923933de` |
| 12237801434 | `historical-v1.1.0-ubuntu-22.04-no_units` | `cae908e8f24ebdec045a15615cb0f504f1dc9087fb57ec654021a78cd5d2d013` |
| 12237577074 | `historical-v1.0.0-ubuntu-22.04-no_units` | `0827b97ebb669aa6789dfb2e1a2e18efb378a277db7c1d2903c8ba2d4739ef98` |
| 12236779207 | `historical-v1.0.0-ubuntu-22.04-with_units` | `092240e6276e2447e149c1b567d744f0ea11fb35c20d682a4d248683a0cf6f7e` |

The promotion evidence artifact `historical-public-download-verification`
contains `historical-v1.0.0-verification.json` or
`historical-v1.1.0-verification.json`, respectively. Evidence ZIP IDs and hashes:

- run 39376007356: artifact 12243133655,
  `3d57344b998ef58418567d95f006d58535f073c4e669ae6b326ac0cb6718c401`.
- run 39376086438: artifact 12243059148,
  `d4d825c81d1e2a031dcfc805c95bec96cbad2defc86c985e50fe882496e10ada`.

### Preservation and test boundaries

The historical tags remain at their original commits. The existing v1.2.0 and
v1.2.0-pj4.rc.1 Release IDs, bodies, asset IDs, byte counts and digests matched
their pre-promotion snapshots; their tags were unchanged. Latest remains v1.2.0.
The main branch remained at the promotion commit during the release checks.

v1.0.0 covers only the two Ubuntu 22.04 x86-64 / Qt5 Linux variants.
v1.1.0 additionally covers Windows x86-64 / MSVC / Qt 5.15.2, no_units only.
The historical Qt/C++ plugin interface is not the PJ4 SDK 0.34.1 interface.
No compatibility claim is made for other host or Qt versions, macOS, ARM,
unpublished variants, or PJ4.

The test coverage is the final-library automated loading, BIN parsing and exact
unit-label assertions described above. An interactive PlotJuggler GUI session
was not part of this historical release acceptance. Historical parser limitations
remain. Linux's explicit `-include array -include cstring` flags supply omitted
standard headers; no product source or parser functionality was backported.

No binary mismatch, missing original variant, tag movement, Latest regression,
or existing-asset mutation was found. These are independent source rebuilds,
not byte-identical upstream binary mirrors or new-feature releases.
