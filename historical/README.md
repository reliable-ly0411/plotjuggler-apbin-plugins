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
