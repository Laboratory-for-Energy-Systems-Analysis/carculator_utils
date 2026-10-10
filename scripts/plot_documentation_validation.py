"""Plot the saved documentation comparisons without rerunning or fitting models.

Requires matplotlib. Inputs retain source-file checksums and observation IDs.
Run from a source checkout; output is independent of the installed runtime data.
"""

import argparse
import json
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "docs/_static/validation/plot_inputs.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.source.read_text())
    args.output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update(
        {"font.size": 10, "axes.spines.top": False, "axes.spines.right": False}
    )
    for name, spec in data["figures"].items():
        rows = spec["rows"]
        x = np.arange(len(rows))
        width = max(7.5, len(rows) * 1.6)
        fig, ax = plt.subplots(figsize=(width, 5.2))
        first = ax.bar(
            x - 0.2,
            [r["first"] for r in rows],
            0.38,
            label=spec["series"][0],
            color="#888888",
        )
        second = ax.bar(
            x + 0.2,
            [r["second"] for r in rows],
            0.38,
            label=spec["series"][1],
            color="#176CA4",
        )
        for bars in (first, second):
            ax.bar_label(bars, fmt="%.1f", padding=3, fontsize=9)
        ax.set_xticks(
            x,
            [
                "\n".join(textwrap.fill(line, 16) for line in r["label"].splitlines())
                for r in rows
            ],
        )
        ax.set_ylabel(spec["unit"])
        ax.set_ylim(0, max(max(r["first"], r["second"]) for r in rows) * 1.28)
        ax.set_title(spec["title"], pad=37, fontweight="bold")
        ax.legend(
            loc="lower center", bbox_to_anchor=(0.5, 1.005), ncol=2, frameon=False
        )
        ax.set_axisbelow(True)
        ax.yaxis.grid(True, color="#e4e4e4")
        fig.text(0.02, 0.018, spec["note"], fontsize=9, color="#444444")
        fig.tight_layout(rect=(0, 0.065, 1, 1))
        fig.savefig(args.output / f"{name}.png", dpi=180)
        fig.savefig(args.output / f"{name}.svg")
        plt.close(fig)


if __name__ == "__main__":
    main()
