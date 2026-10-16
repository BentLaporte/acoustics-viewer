# Sample files (not in the repository)

The `.SVL` files are measurements of clients and are git-ignored. The tests that need them are
skipped when they are missing; with all of them present nothing is skipped. Put these files in
this folder. Names are `<type>_<role>_L<number>`: the kind of measurement (luchtgeluid,
contactgeluid, installatiegeluid; ontvangstruimte = shared by airborne and impact), the role
(bron, ontvangst, BG = background, RT = reverberation time) and the instrument's file number.

| File | What it is | Used by |
|---|---|---|
| `luchtgeluid_bron_L1.SVL` | SV 977D, level file (source room), checked against SvanPC++ `Total results` and header information | parser, dates, instruments |
| `luchtgeluid_bron_L2.SVL` | SV 977D, level file (source room) | airborne, building, report, CLI |
| `luchtgeluid_ontvangst_L2.SVL` | SV 977D, level file (receiving room) | airborne, building, report, CLI |
| `contactgeluid_L4.SVL` | SV 977D, tapping machine level file | impact, building, report, CLI |
| `ontvangstruimte_BG_L20.SVL` | SV 977D, background level file | everything with a background |
| `ontvangstruimte_RT_L11.SVL` | SV 977D, reverberation time file, checked against SvanPC++ `RT60` | reverberation, building, report |
| `parser_RT_volle_buffer_L15.SVL` | SV 977D, reverberation time file whose buffer was exactly full (no 4-word preamble) | alignment of the buffer |
| `977C_L1.SVL` | SV 977C, level file, checked against SvanPC++ `Total results` | instruments, 977C |
| `977C_RT_L34.SVL` | SV 977C, reverberation time file, checked against SvanPC++ `RT60` | instruments, 977C |
| `installatiegeluid_L22.SVL` | SV 977D, installation noise level file (stationary), checked against SvanPC++ `Main results` (LAeq, LAFmax) | installation noise |
| `installatiegeluid_BG_L39.SVL` | SV 977D, background level file of that room | installation noise |
| `installatiegeluid_RT_L15.SVL`, `installatiegeluid_RT_L16.SVL` | SV 977D, reverberation time files of that room (no T30 at 400-630 Hz) | installation noise |

Run `python -m pytest -rs` to see which tests are skipped and why.
