#!/usr/bin/env python3
"""
Download PMCore model weights from HuggingFace.

Downloads all three models into ./checkpoints/:
  - checkpoints/planner/best.pt          (PMPlanner, 171.8M)
  - checkpoints/reasoner/best.pt         (PMReasoner, 125.3M)
  - checkpoints/communicator_phi3/merged/ (PMCommunicator, 3.8B LoRA fine-tune)

Usage:
    python scripts/download_models.py
    python scripts/download_models.py --org pmcore --dir ./checkpoints
    python scripts/download_models.py --skip-communicator   # planner + reasoner only
"""

import argparse
import os
import sys
from pathlib import Path


def download_pt_model(repo_id: str, filename: str, dest_path: Path, token: str = None):
    """Download a single .pt file from a HuggingFace repo."""
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("ERROR: huggingface-hub not installed. Run: pip install huggingface-hub")
        sys.exit(1)

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if dest_path.exists():
        print(f"  Already exists: {dest_path}")
        return

    print(f"  Downloading {repo_id}/{filename} -> {dest_path} ...")
    local = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        local_dir=str(dest_path.parent),
        token=token,
    )
    # hf_hub_download may put it in a subdirectory; rename if needed
    downloaded = Path(local)
    if downloaded != dest_path:
        downloaded.rename(dest_path)
    print(f"  OK Saved to {dest_path}")


def download_hf_model(repo_id: str, dest_dir: Path, token: str = None):
    """Download a full HuggingFace model (safetensors) using snapshot_download."""
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("ERROR: huggingface-hub not installed. Run: pip install huggingface-hub")
        sys.exit(1)

    dest_dir.mkdir(parents=True, exist_ok=True)

    # Check if already downloaded (look for config.json as sentinel)
    if (dest_dir / "config.json").exists():
        print(f"  Already exists: {dest_dir}")
        return

    print(f"  Downloading {repo_id} -> {dest_dir} ...")
    snapshot_download(
        repo_id=repo_id,
        local_dir=str(dest_dir),
        token=token,
        ignore_patterns=["*.msgpack", "flax_model*", "tf_model*", "rust_model*"],
    )
    print(f"  OK Saved to {dest_dir}")


def main():
    parser = argparse.ArgumentParser(description="Download PMCore models from HuggingFace")
    parser.add_argument("--org", default=os.environ.get("PMCORE_HF_ORG", "pmcore"),
                        help="HuggingFace organization (default: pmcore)")
    parser.add_argument("--dir", default="./checkpoints",
                        help="Local checkpoints directory (default: ./checkpoints)")
    parser.add_argument("--token", default=os.environ.get("HF_TOKEN"),
                        help="HuggingFace read token (or set HF_TOKEN env var)")
    parser.add_argument("--skip-communicator", action="store_true",
                        help="Skip downloading the large PMCommunicator (3.8B) model")
    args = parser.parse_args()

    checkpoints = Path(args.dir)
    org = args.org
    token = args.token

    print(f"PMCore Model Downloader")
    print(f"  Organization : {org}")
    print(f"  Destination  : {checkpoints.resolve()}")
    print(f"  Token        : {'set' if token else 'not set (public repos only)'}")
    print()

    # --- PMPlanner ---
    print("1/3  PMPlanner (171.8M)...")
    download_pt_model(
        repo_id=f"{org}/pmplanner",
        filename="best.pt",
        dest_path=checkpoints / "planner" / "best.pt",
        token=token,
    )

    # --- PMReasoner ---
    print("2/3  PMReasoner (125.3M)...")
    download_pt_model(
        repo_id=f"{org}/pmreasoner",
        filename="best.pt",
        dest_path=checkpoints / "reasoner" / "best.pt",
        token=token,
    )

    # --- PMCommunicator (from-scratch 746M, pipeline model) ---
    print("3/3  PMCommunicator (746M from-scratch, ~1.4GB)...")
    download_pt_model(
        repo_id=f"{org}/pmcommunicator-pt",
        filename="best.pt",
        dest_path=checkpoints / "communicator" / "best.pt",
        token=token,
    )

    # --- PMCommunicator Phi-3.5 LoRA (optional, for Ollama / enhanced comms) ---
    if not args.skip_communicator:
        print("4/4  PMCommunicator-Phi (Phi-3.5-mini LoRA merged, ~7GB)...")
        print("     Large download. Only needed for Ollama / enhanced mode.")
        download_hf_model(
            repo_id=f"{org}/pmcommunicator",
            dest_dir=checkpoints / "communicator_phi3" / "merged",
            token=token,
        )
    else:
        print("4/4  PMCommunicator-Phi skipped (--skip-communicator).")

    print()
    print("OK All models downloaded. You can now start PMCore:")
    print("  uvicorn api:app --host 0.0.0.0 --port 8765")
    print("  or: docker compose up")


if __name__ == "__main__":
    main()
