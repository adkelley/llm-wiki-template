#!/usr/bin/env bash

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  set -eou pipefail
fi

wiki_dir_input="${1:-.}"
wiki_dir=$(cd -- "${wiki_dir_input}" && pwd)
raw_dir="${wiki_dir}/raw"
parent_dir=$(cd -- "${wiki_dir}/.." && pwd)
wiki_name=$(basename -- "${wiki_dir}")

if [[ ! -d "${raw_dir}" ]]; then
  printf 'error: raw directory not found: %s\n' "${raw_dir}" >&2
  exit 1
fi

# Link every directory in PicoVoice into LLM Wiki/raw, except for LLM Wiki
# itself.  Relative links keep the raw folder portable within the parent.
while IFS= read -r -d '' source_dir; do
  name=$(basename -- "${source_dir}")
  link_path="${raw_dir}/${name}"
  relative_target="../../${name}"

  if [[ -L "${link_path}" ]]; then
    if [[ "$(readlink -- "${link_path}")" != "${relative_target}" ]]; then
      printf 'error: %s already points to %s, expected %s\n' \
        "${link_path}" "$(readlink -- "${link_path}")" "${relative_target}" >&2
      exit 1
    fi
  elif [[ -e "${link_path}" ]]; then
    printf 'error: %s exists and is not a symbolic link\n' "${link_path}" >&2
    exit 1
  else
    ln -s -- "${relative_target}" "${link_path}"
  fi
done < <(
  find "${parent_dir}" -mindepth 1 -maxdepth 1 -type d \
    ! -name "${wiki_name}" -print0
)
