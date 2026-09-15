"""
Downloads a GGUF model from Hugging Face at image-build time ("baking").

Invoked by the Dockerfile when LLAMA_ARG_HF_REPO is passed as a build arg.
Selects a GGUF file in the repo by quant tag or exact filename, downloads it
(complete shard sets included) into the destination directory, and writes a
manifest (baked.json) that src/start.sh reads at runtime.
"""

import argparse
import json
import os
import re
import shutil
import sys

from huggingface_hub import HfApi, hf_hub_download

DEFAULT_QUANT = "Q4_K_M"  # matches the template default in .runpod/hub.json
MANIFEST_NAME = "baked.json"
SHARD_RE = re.compile(r"^(?P<stem>.*)-(?P<idx>\d{5})-of-(?P<total>\d{5})\.gguf$")


def die(message, gguf_files=()):
    """Exit non-zero, optionally listing the repo's GGUF files for context."""
    print(f"fetch_model.py: ERROR: {message}", file=sys.stderr)
    if gguf_files:
        print("fetch_model.py: Available GGUF files in the repo:", file=sys.stderr)
        for name in gguf_files:
            print(f"  {name}", file=sys.stderr)
    sys.exit(1)


def select_file(quant_or_file, gguf_files):
    """
    Resolve the requested quant tag or GGUF filename to a single repo file.

    A quant tag is matched case-insensitively as a substring of the file
    basename (mirrors llama.cpp's repo:quant semantics). An empty selector
    defaults to DEFAULT_QUANT when available.
    """
    if quant_or_file.endswith(".gguf"):
        for name in gguf_files:
            if quant_or_file in (name, os.path.basename(name)):
                return name
        die(f"GGUF file '{quant_or_file}' not found in the repo.", gguf_files)

    quant = quant_or_file or DEFAULT_QUANT
    hint = "" if quant_or_file else " (the default when no quantization is given)"
    for name in gguf_files:
        if quant.lower() in os.path.basename(name).lower():
            return name
    die(f"No GGUF file matches quantization '{quant}'{hint}.", gguf_files)


def expand_shards(selected, gguf_files):
    """A sharded GGUF is only usable as a complete set: add all siblings."""
    match = SHARD_RE.match(os.path.basename(selected))
    if not match:
        return [selected]
    siblings = [
        name for name in gguf_files
        if (shard := SHARD_RE.match(os.path.basename(name)))
        and shard.group("stem") == match.group("stem")
        and shard.group("total") == match.group("total")
    ]
    return sorted(siblings)


def main():
    parser = argparse.ArgumentParser(
        description="Download a GGUF model from Hugging Face into a directory "
        "and write a baked.json manifest."
    )
    parser.add_argument(
        "repo", type=str, help="Hugging Face GGUF repo, e.g. unsloth/Qwen3.8-27B-GGUF"
    )
    parser.add_argument(
        "quant_or_file",
        type=str,
        nargs="?",
        default="",
        help="Quantization tag (e.g. Q6_K, case-insensitive) or exact GGUF "
        "filename in the repo. Defaults to " + DEFAULT_QUANT + " when available.",
    )
    parser.add_argument(
        "--dest",
        type=str,
        default="/models",
        help="Directory to download the model into (default: /models)",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="Hugging Face token; also read from the HF_TOKEN environment "
        "variable natively by huggingface_hub",
    )
    args = parser.parse_args()

    api = HfApi(token=args.token)
    try:
        files = api.list_repo_files(args.repo)
    except Exception as exc:
        die(f"Could not list files in repo '{args.repo}': {exc}")

    gguf_files = sorted(f for f in files if f.lower().endswith(".gguf"))
    if not gguf_files:
        die(f"Repo '{args.repo}' contains no GGUF files.")

    selected = select_file(args.quant_or_file, gguf_files)
    targets = expand_shards(selected, gguf_files)
    if len(targets) > 1:
        print(f"fetch_model.py: Sharded model, downloading all {len(targets)} shards.",
              file=sys.stderr)

    os.makedirs(args.dest, exist_ok=True)
    local_paths = {}
    for name in targets:
        try:
            local_paths[name] = hf_hub_download(
                repo_id=args.repo, filename=name, local_dir=args.dest, token=args.token
            )
        except Exception as exc:
            die(f"Could not download '{name}' from '{args.repo}': {exc}")

    # huggingface_hub leaves download metadata under <dest>/.cache; drop it so
    # the image layer contains only model files.
    shutil.rmtree(os.path.join(args.dest, ".cache"), ignore_errors=True)

    # For a shard set the first shard is what llama.cpp must be pointed at;
    # otherwise there is just the one file. Same 5-digit index ordering makes
    # min() the first shard in both cases.
    model_path = local_paths[min(targets)]
    manifest = {
        "model": model_path,
        "repo": args.repo,
        "quant": args.quant_or_file or DEFAULT_QUANT,
    }
    with open(os.path.join(args.dest, MANIFEST_NAME), "w") as fh:
        json.dump(manifest, fh, indent=2)

    print(model_path)


if __name__ == "__main__":
    main()
