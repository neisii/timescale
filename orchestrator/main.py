"""Entry point — Multi-Agent Pipeline for Smart Factory Time-Series Backend MVP.

Usage:
    python3.12 orchestrator/main.py [--iterations N] [--skip-git] [--planner-only]

Options:
    --iterations N    Max REVIEWER/FIXER cycles (default: 3)
    --skip-git        Disable git branch/commit automation
    --planner-only    Run PLANNER phase only (P1 검증용)
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from pipeline import Pipeline
from config import MAX_ITERATIONS


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smart Factory Multi-Agent Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--iterations", "-i",
        type=int, default=MAX_ITERATIONS,
        help=f"Max REVIEWER/FIXER iterations (default: {MAX_ITERATIONS})",
    )
    parser.add_argument(
        "--skip-git",
        action="store_true",
        help="Disable automatic git branch/commit (useful for dry runs)",
    )
    parser.add_argument(
        "--planner-only",
        action="store_true",
        help="Run PLANNER phase only (P1 검증용)",
    )
    args = parser.parse_args()

    pipeline = Pipeline(
        max_iterations=args.iterations,
        skip_git=args.skip_git,
        planner_only=args.planner_only,
    )

    try:
        pipeline.run()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
        sys.exit(1)

    print(f"  conversation/ 이력 파일 : conversation/")
    print(f"  cost/ 비용 기록 파일    : cost/")


if __name__ == "__main__":
    main()
