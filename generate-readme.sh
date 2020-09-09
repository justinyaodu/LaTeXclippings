#!/usr/bin/env bash

script_dir="$(dirname "${0}")"

latex() {
	>&2 echo "Rendering LaTeX: '${1}'"
	"${script_dir}/latexclippings.py" --format html <<< "${1}"
}

cat > "${script_dir}/README.md" << EOF
# $(latex '\LaTeX')clippings
EOF
