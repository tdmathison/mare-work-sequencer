"""Offline validated recovery of an administrator installation backup."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from installation_backup import restore_installation


def main():
    parser = argparse.ArgumentParser(
        description="Stop MARE first. Restore a complete installation into an ABSENT data directory. Never merges or overwrites existing instances. Use trusted installation backups only."
    )
    parser.add_argument("archive", type=Path)
    parser.add_argument(
        "--destination",
        required=True,
        type=Path,
        help="Absent directory to become MARE_DATA_DIR. Its parent must exist.",
    )
    args = parser.parse_args()
    try:
        result = restore_installation(args.archive, args.destination)
    except Exception as exc:
        parser.exit(1, f"Restore refused: {exc}\n")
    print(json.dumps(result, indent=2))
    print(
        "Restore complete. Restore service-account ownership and deployment environment/secrets separately, then start this compatible application version."
    )


if __name__ == "__main__":
    main()
