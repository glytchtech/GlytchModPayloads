# Release notices and provenance

The standard release binaries are statically linked using **Zig 0.14.1**,
targeting `mipsel-linux-musleabi` / MIPS32r2. Static linking removes shared-library
installation requirements, not the obligation to distribute runtime notices.
`scripts/copy-release-licenses.sh` collects these notices for the payload and
installed package. The notice texts themselves are copied without modification.

| Distributed notice | Source in the pinned build inputs |
| --- | --- |
| Pager-MeshCore-MIT.txt | Project `LICENSE` |
| DejaVu.txt | `LICENSES/DEJAVU.txt`; native UI font subset |
| Monocypher-BSD-2-CLAUSE.txt | `LICENSES/MONOCYPHER-BSD-2-CLAUSE.txt`; bundled Monocypher crypto |
| TinyCrypt-BSD-3-Clause.txt | `third_party/tinycrypt/LICENSE` at `b1fed54ce0f79e0e2ffbec7684bb4988a5f20607` |
| ZephCore-MIT-and-notices.txt | `third_party/ZephCore/zephcore/LICENSE` at `788e4dd48b5b32f39d4c175c8233c499db125cc0` |
| MeshCore-MIT.txt | `third_party/MeshCore/license.txt` at `03b6ef4b0de98fc70b49ef10a6d0d61f8381fb7a`; protocol/reference attribution |
| Zig-0.14.1-MIT.txt | Zig 0.14.1 distribution `LICENSE`; compiler runtime |
| musl-COPYRIGHT.txt | Zig 0.14.1 `lib/libc/musl/COPYRIGHT`; C runtime and constituent notices |
| libcxx-LICENSE.txt | Zig 0.14.1 `lib/libcxx/LICENSE.TXT`; C++ standard library |
| libcxxabi-LICENSE.txt | Zig 0.14.1 `lib/libcxxabi/LICENSE.TXT`; C++ ABI runtime |
| libunwind-LICENSE.txt | Zig 0.14.1 `lib/libunwind/LICENSE.TXT`; toolchain runtime notice included conservatively |

The five Zig-distribution notices are vendored in this directory as
`ZIG-0.14.1-MIT.txt`, `MUSL-COPYRIGHT.txt`, `LIBCXX-LICENSE.txt`,
`LIBCXXABI-LICENSE.txt`, and `LIBUNWIND-LICENSE.txt`, respectively. They were
copied from the same Zig 0.14.1 distribution used to build the release, not from
a newer upstream license page. Some runtime objects can be discarded by the
linker; including the complete notices avoids depending on that optimization.

## Alternate OpenWrt SDK builds

The optional OpenWrt SDK path uses GCC, libgcc, and libstdc++, not Zig's C++
runtime. Before distributing an SDK-built artifact, retain the matching musl
notices and collect the exact GCC/libgcc/libstdc++ licenses and runtime-library
exceptions from that SDK. The Zig/libc++ notices alone do **not** document an
SDK build's licensing. Record the actual compiler and SDK version with that
artifact; do not describe it as the pinned Zig release.
