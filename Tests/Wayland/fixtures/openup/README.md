# Owned OpenUp archive fixtures

These small archives contain repository-authored payloads. They exercise the
existing ARJ, LHA, BinHex, MacBinary, StuffIt, PackIt and Compact Pro extraction
commands. StuffIt, PackIt and Compact Pro also contain the nonempty
`resource.txt` resource fork.
Tests copy them to filenames with spaces and Unicode characters, and verify the
exact extracted bytes and native Workspace folder at all five densities.
The `.lha` and `.lzh` extensions share the same LHA fixture; `.bin` and `.macbin`
share the same MacBinary fixture. The legacy Macintosh fixtures use stored
StuffIt and PackIt records and literal Compact Pro RLE records. These fixtures
cover those records, not every compression method in each format.

The LHA fixture uses a level-zero `-lh0-` header, an 8-bit header checksum and
the payload's CRC-16/IBM (polynomial `0xa001`, initial value zero). It passes
`lha t` and `lha xf` with Debian 13 ARM64 lhasa 0.4.0-1+b2.
The other fixtures were produced on Debian 13 ARM64 using:

```
arj a -y -m0 legacy.arj legacy.txt
binhex -d legacy.txt > legacy.hqx
macstream -d legacy.txt > legacy.bin
```

Producer versions are arj 3.10.22-28 and macutils 2.0b3-17. The application uses
`arj e`, `lha xf`, `hexbin -3` and `macunpack -3` to extract them. The Macintosh
commands emit `.info`, `.data` and `.rsrc` files; `.data` must match `legacy.txt`.
Production packages need only the extraction tools. No archive producer runs
in the regression suite.

| File | SHA-256 |
| --- | --- |
| legacy.arj | `f9c3e544f2a23ae7181ead2f3243e52ddb7879a17a7e13a6086ec8d2e4fa0da3` |
| legacy.bin | `69ede1dab50e0d3f0e76144f4c8bbb68ec081af5d516a0755dfa24640f1f33e5` |
| legacy.hqx | `a0bb25b2fab9536da8a6237f538d19fcef785df6bf5a600406947ff647745685` |
| legacy.lzh | `4b9a8886a381b5a1bd72d467ff40282e9e9bbbfa20a6cbdef0e75bed2e626f6b` |
| legacy.txt | `8c157a64a6a3e81bd5720a1ac2117b83802649ed12e9f60a2308f6110ef1b3f8` |

`make-macintosh.py` regenerates the three owned Macintosh archives without an
external encoder. Their headers use the existing macutils definitions; data
and resource forks must match `legacy.txt` and `resource.txt` exactly. The
Compact Pro CRC uses unsigned 32-bit arithmetic. The bundle-local decoder fixes
signed polynomial extension in macutils' CRC table generator; checksum checks
remain enabled.

- `legacy.sit`: `81fb0f1468657bc924245163cc4556c8cc8d5a32c7957c1e3041869745819d24`
- `legacy.pit`: `68b578a8eb8c3564aa761bd92aafbca93ce947dba3af5ea051c74bd5690f3d57`
- `legacy.cpt`: `90b1bec24dc06ef17a78dbc57d6de549ff5fde562173ddade9ee9d06d4f7932a`
- `resource.txt`: `63abedffffb78250787d94dd6bf5bcb73c8833226176eb5b9b28bc978bdab423`
