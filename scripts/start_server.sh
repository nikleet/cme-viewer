#!/usr/bin/env bash
set -e

DATA_DIR="$1"

if [ -z "$DATA_DIR" ]; then
    echo "Usage: $0 /path/to/data"
    exit 1
fi

if [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
    conda activate pyvisual-dev
fi

python -m app.server --mode remote --data-dir "$DATA_DIR"