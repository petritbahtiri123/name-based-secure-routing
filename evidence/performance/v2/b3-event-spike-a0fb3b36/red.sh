#!/bin/sh
set -eu
rustc --edition=2024 --test /evidence/gate.rs -o /tmp/gate-red
/tmp/gate-red --nocapture
