"""Benchmark streaming vs. bulk parse across digest sizes.

Usage: python benchmarks/bench_streaming.py [--count N]
"""

from __future__ import annotations

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from git_undigest import parse_digest, parse_stream


def _generate_digest(file_count: int, avg_size: int = 1024) -> str:
    """Generate a GitIngest digest with *file_count* files."""
    lines: list[str] = []
    lines.append("Directory structure:\n")
    lines.append("└── bench/\n")
    for i in range(file_count):
        data = f"x{avg_size}"[:avg_size]
        lines.append("=" * 48 + "\n")
        lines.append(f"File: f{i:06d}.txt\n")
        lines.append("=" * 48 + "\n")
        lines.append(data + "\n")
        lines.append("\n")
    return "".join(lines)


def _human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def bench(file_count: int, avg_size: int = 1024) -> dict:
    digest_text = _generate_digest(file_count, avg_size)
    digest_size = len(digest_text.encode("utf-8"))

    # Write digest to temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(digest_text)
        tmp_path = tmp.name

    result: dict = {
        "file_count": file_count,
        "avg_file_size": avg_size,
        "digest_size": digest_size,
        "digest_size_human": _human_size(digest_size),
    }

    # -- Bulk parse (parse_digest) --
    t0 = time.perf_counter()
    summary = parse_digest(tmp_path)
    t1 = time.perf_counter()
    result["bulk_time"] = round(t1 - t0, 4)
    result["bulk_files"] = summary.file_count

    # -- Streaming parse (parse_stream) --
    t0 = time.perf_counter()
    stream_count = 0
    for _ in parse_stream(tmp_path):
        stream_count += 1
    t1 = time.perf_counter()
    result["stream_time"] = round(t1 - t0, 4)
    result["stream_files"] = stream_count

    result["speedup"] = (
        round(result["bulk_time"] / result["stream_time"], 2)
        if result["stream_time"] > 0
        else 0
    )

    os.unlink(tmp_path)
    return result


def main() -> None:
    counts = [100, 1000, 10000]
    if "--all" in sys.argv:
        counts += [100000, 1000000]

    header = f"{'Files':>10}  {'Digest':>10}  {'Bulk (s)':>10}  {'Stream (s)':>10}  {'Speedup':>8}"  # noqa: E501
    print(header)
    print("-" * 58)
    for c in counts:
        r = bench(c)
        print(
            f"{r['file_count']:>10,}  "
            f"{r['digest_size_human']:>10}  "
            f"{r['bulk_time']:>10.4f}  "
            f"{r['stream_time']:>10.4f}  "
            f"{r['speedup']:>7.2f}x"
        )


if __name__ == "__main__":
    main()
