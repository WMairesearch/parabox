"""Render Peer composition recipient trajectories and independent-chain late rates."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
COLORS = ("#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#666666")
LABELS = {"v4pro": "V4 Pro", "gemini": "Gemini 3.1 Pro", "kimi": "Kimi K3",
          "qwen-max": "Qwen max", "ds-flash": "DeepSeek Flash", "qwen-flash": "Qwen Flash"}


def main() -> None:
    summary = json.loads((ROOT / "report/final/peer-composition-analysis.json").read_text())
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.1), gridspec_kw={"width_ratios": [1.35, 1]})
    for index, (peer, arm) in enumerate(summary["arms"].items()):
        color = COLORS[index]
        curve = arm["recipient_curve"]
        rates = [row["cheat"] / row["normal"] if row["normal"] and not row["audit_unknown"]
                 else float("nan") for row in curve]
        axes[0].plot(range(1, 9), rates, marker=("o", "s", "^", "D", "v", "P")[index],
                     color=color, linewidth=1.6, markersize=4, label=LABELS[peer])
        known = [chain["rate"] for chain in arm["chains"] if chain["rate"] is not None]
        jitter = [(position - (len(known) - 1) / 2) * 0.055 for position in range(len(known))]
        axes[1].scatter(known, [index + offset for offset in jitter], color=color, alpha=0.7, s=25)
        estimate = arm["late_complete_known_chain_estimate"]
        if estimate["mean"] is not None and estimate["low"] is not None:
            axes[1].errorbar(estimate["mean"], index, xerr=[[estimate["mean"] - estimate["low"]],
                            [estimate["high"] - estimate["mean"]]], color="black", fmt="|", capsize=3)
    axes[0].set(xlabel="Generation", ylabel="Recipient cheating rate", ylim=(-0.04, 1.04),
                xticks=range(1, 9), title="Three fixed V4 Pro recipients; only the peer model varies")
    axes[0].legend(fontsize=8, ncol=2, loc="upper right", bbox_to_anchor=(1, 0.92))
    axes[1].set(xlabel="Late recipient cheating (generations 6–8)", xlim=(-0.04, 1.04),
                yticks=range(len(summary["arms"])),
                yticklabels=[LABELS[peer] for peer in summary["arms"]], title="Dots: independent chains; bars: 95% bootstrap")
    axes[1].invert_yaxis()
    for axis in axes:
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(alpha=0.15)
    figure.text(0.02, 0.01, "Five chains per condition; descriptive intervals. Zero-width bootstrap intervals do not imply population certainty.", fontsize=8)
    figure.tight_layout(rect=(0, 0.045, 1, 1))
    destination = ROOT / "report/decks/spread-of-misalignment/figures/peer-composition"
    figure.savefig(destination.with_suffix(".pdf"), metadata={"CreationDate": None, "ModDate": None})
    figure.savefig(destination.with_suffix(".png"), dpi=180)
    plt.close(figure)


if __name__ == "__main__":
    main()
