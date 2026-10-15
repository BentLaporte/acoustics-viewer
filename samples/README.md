# Sample files (not in the repository)

The `.SVL` files are measurements of clients and are git-ignored. The tests that need them are
skipped when they are missing; with all of them present nothing is skipped. Put these files in
this folder:

| File | What it is | Used by |
|---|---|---|
| `A_L1.SVL` | SV 977D, level file (source room), checked against SvanPC++ `Total results` and header information | parser, dates, instruments |
| `A_L2.SVL` | SV 977D, level file (source room) | airborne, building, report, CLI |
| `B_L2.SVL` | SV 977D, level file (receiving room) | airborne, building, report, CLI |
| `B_L4.SVL` | SV 977D, tapping machine level file | impact, building, report, CLI |
| `C_L20.SVL` | SV 977D, background level file | everything with a background |
| `B_L11.SVL` | SV 977D, reverberation time file, checked against SvanPC++ `RT60` | reverberation, building, report |
| `B_L15.SVL` | SV 977D, reverberation time file whose buffer was exactly full (no 4-word preamble) | alignment of the buffer |
| `977C_example.SVL` | SV 977C, level file, checked against SvanPC++ `Total results` | instruments, 977C |
| `977C_RT.SVL` | SV 977C, reverberation time file, checked against SvanPC++ `RT60` | instruments, 977C |

Run `python -m pytest -rs` to see which tests are skipped and why.
