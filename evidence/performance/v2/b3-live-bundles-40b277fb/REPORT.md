# Active B3 resource scale and repeated cleanup

40b277fb release Docker/WSL: 512 and 1024 materialized authenticated live bundles
pass five repeats each; both roles' active private-resident CV is below 1%.
The separate workload enables standard one-second QUIC keepalive. Original idle
1024 failures remain failures; matched materialized idle controls are pending.
Five same-process 100-cycle repetitions pass all owned cleanup checks, with zero
first-to-last FD/thread growth. Private-resident retention still has positive
slopes in some tails; allocator cause and a general plateau are INCONCLUSIVE.
The derived 658768 bytes/bundle slope uses only 512 and 1024, includes both
processes and transport/runtime/fixture costs, and is not pure NBSR object size.
The extension commit permits 2048/4096 only for explicit benchmark keepalive/hold;
its 53 Python tests, release clippy and default check pass after literal RED.
Larger-scale execution is not claimed here. No production optimization occurred.
