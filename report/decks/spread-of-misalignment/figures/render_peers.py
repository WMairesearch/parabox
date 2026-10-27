"""Render the deck's fixed-peer trajectories from published session outcomes."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


MODELS = {
    "v4pro": "DeepSeek V4 Pro",
    "gemini": "Gemini 3.1 Pro",
    "kimi": "Kimi K3",
    "qwen-max": "Qwen Max",
    "ds-flash": "DeepSeek Flash",
    "qwen-flash": "Qwen Flash",
}
COLORS = ("#245A81", "#BE563C", "#27816F", "#8B5B97", "#B88624", "#697785")


def main():
    destination = Path(__file__).resolve().parent
    source = destination.parents[2] / "final/peer-composition-outcomes.json"
    outcomes = json.loads(source.read_text())
    figure, axes = plt.subplots(2, 3, figsize=(12, 4.7), sharex=True, sharey=True)
    for axis, (model, label), color in zip(axes.flat, MODELS.items(), COLORS):
        peers = [row for row in outcomes["arms"][model]["sessions"]
                 if row["normal"] and row["agent"] < 3]
        rates = []
        for generation in range(1, 9):
            group = [row for row in peers if row["generation"] == generation]
            if len(group) != 15 or any(row["audit_unknown"] for row in group):
                raise ValueError("Expected 15 audited fixed-peer sessions per generation")
            rates.append(sum(row["cheat"] for row in group) / 15)
        axis.axvspan(5.5, 8.3, color="#EAF0F3", zorder=0)
        axis.plot(range(1, 9), rates, color=color, marker="o", linewidth=2, markersize=4)
        axis.set(title=f"Fourth model: {label}", xticks=[1, 4, 8], yticks=[0, 0.5, 1],
                 ylim=(-0.05, 1.05), xlim=(0.7, 8.3))
        axis.grid(alpha=0.12)
    for axis in axes[-1]:
        axis.set_xlabel("Generation")
    for axis in axes[:, 0]:
        axis.set_ylabel("Fixed V4 Pro peers:\nviolation rate")
    figure.text(0.10, 0.015,
                "Each point: 15 V4 Pro sessions (3 peers × 5 chains). Shading: 45 sessions in generations 6–8.",
                fontsize=10)
    figure.tight_layout(rect=(0, 0.065, 1, 1))
    figure.savefig(destination / "spread-peers.pdf", metadata={"CreationDate": None, "ModDate": None})
    figure.savefig(destination / "spread-peers.png", dpi=180)
    plt.close(figure)


if __name__ == "__main__":
    main()
