#!/bin/sh
set -eu
rustc --edition=2024 --test /evidence/gate.rs -o /tmp/selective-red
/tmp/selective-red --nocapture
