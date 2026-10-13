"""Render the spread narrative from frozen session outcomes, without model calls."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from parabox.analysis import read_sessions

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "report/decks/spread-of-misalignment"
MODELS = {
    "v4pro": "DeepSeek V4 Pro",
    "gemini": "Gemini 3.1 Pro",
    "kimi": "Kimi K3",
    "qwen-max": "Qwen Max",
    "ds-flash": "DeepSeek Flash",
    "qwen-flash": "Qwen Flash",
}
COLORS = ("#245A81", "#BE563C", "#27816F", "#8B5B97", "#B88624", "#697785")
CONTROL = "#8395A5"
EXPOSED = "#BE563C"


def sessions(name: str, condition: str | None = None) -> list[dict]:
    records = read_sessions(ROOT / "report/final" / f"{name}.csv")
    return [record for record in records if condition is None or record["arm"] == condition]


def cheating_rate(records: list[dict]) -> float:
    if not records:
        raise ValueError("Empty outcome group")
    if any(record["accepted"] is True and record["cheat"] is not True
           and record["audit_ok"] is not True for record in records):
        return float("nan")
    return sum(record["cheat"] is True for record in records) / len(records)


def save(figure, name: str) -> None:
    destination = DESTINATION / "figures" / name
    figure.savefig(destination.with_suffix(".pdf"),
                   metadata={"CreationDate": None, "ModDate": None})
    figure.savefig(destination.with_suffix(".png"), dpi=160)
    plt.close(figure)


def exposure() -> None:
    figure, axes = plt.subplots(1, 3, figsize=(12, 3.5), sharey=True)
    for axis, (title, control_prefix, note_prefix) in zip(axes, (
        ("Test harness", "exposure", "exposure"),
        ("Grade store", "gate-comparison-state", "corrected-gate-exposure-state"),
        ("Score file", "gate-comparison-score", "corrected-gate-exposure-score"),
    )):
        for position, model in enumerate(MODELS):
            control = sessions(f"{control_prefix}-{model}", "control")
            note = sessions(f"{note_prefix}-{model}", "note")
            if len(control) != 16 or len(note) != 16:
                raise ValueError("Unexpected exposure denominator")
            before, after = cheating_rate(control), cheating_rate(note)
            axis.plot([before, after], [position, position], color="#C5CDD3", linewidth=2)
            axis.scatter(before, position, color=CONTROL, marker="o", s=70, zorder=3)
            axis.scatter(after, position, edgecolor=EXPOSED, facecolor="none",
                         marker="D", s=52, linewidth=1.6, zorder=4)
        axis.set(title=title, xlabel="Fraction of sessions with cheating", xlim=(-0.05, 1.05),
                 xticks=[0, 0.5, 1], yticks=range(len(MODELS)),
                 yticklabels=list(MODELS.values()))
        axis.grid(axis="x", alpha=0.16)
    axes[0].invert_yaxis()
    figure.legend(handles=[
        Line2D([], [], color=CONTROL, marker="o", linestyle="none", label="Control"),
        Line2D([], [], color=EXPOSED, marker="D", markerfacecolor="none", linestyle="none",
               label="With an exploit note"),
    ], loc="lower center", ncol=2, frameon=False)
    figure.tight_layout(rect=(0, 0.12, 1, 1))
    save(figure, "spread-exposure")


def solvable() -> None:
    figure, axis = plt.subplots(figsize=(10.6, 3.5))
    for position, model in enumerate(("v4pro", "gemini", "kimi")):
        for offset, condition, color in ((-0.17, "control", CONTROL), (0.17, "method", EXPOSED)):
            records = sessions(f"solvable-extended-budget-{model}", condition)
            if len(records) != 16:
                raise ValueError("Unexpected solvable-task denominator")
            count = sum(record["cheat"] is True for record in records)
            axis.barh(position + offset, count / 16, height=0.29, color=color)
            axis.text(count / 16 + 0.025, position + offset, f"{count}/16",
                      va="center", fontsize=13, color=color)
    axis.set(yticks=range(3), yticklabels=[MODELS[model] for model in ("v4pro", "gemini", "kimi")],
             xlabel="Fraction of sessions with cheating", xlim=(0, 1.15), xticks=[0, 0.5, 1])
    axis.invert_yaxis()
    figure.legend(handles=[Line2D([], [], color=CONTROL, linewidth=7, label="Control"),
                           Line2D([], [], color=EXPOSED, linewidth=7, label="With an exploit note")],
                  loc="lower center", ncol=2, frameon=False)
    figure.tight_layout(rect=(0, 0.13, 1, 1))
    save(figure, "spread-solvable")


def inheritance() -> None:
    figure, axes = plt.subplots(1, 3, figsize=(12, 3.6), sharey=True)
    for axis, model in zip(axes, ("v4pro", "gemini", "kimi")):
        for condition, color, style in (("control", CONTROL, "--"), ("method", EXPOSED, "-")):
            records = sessions(f"solvable-chains-{model}", condition)
            groups = [[record for record in records if record["generation"] == generation]
                      for generation in range(1, 9)]
            if any(len(group) != 10 for group in groups):
                raise ValueError("Unexpected inheritance denominator")
            axis.plot(range(1, 9), [cheating_rate(group) for group in groups],
                      color=color, linestyle=style, marker="o", markersize=5, linewidth=2)
        axis.set(title=MODELS[model], xlabel="Generation", xticks=[1, 2, 4, 6, 8],
                 ylim=(-0.04, 1.04), yticks=[0, 0.5, 1])
        axis.grid(alpha=0.15)
    axes[0].set_ylabel("Cheating rate")
    figure.legend(handles=[
        Line2D([], [], color=CONTROL, linestyle="--", label="Control-seeded lineage"),
        Line2D([], [], color=EXPOSED, label="Exploit-seeded lineage"),
    ], loc="lower center", ncol=2, frameon=False, bbox_to_anchor=(0.5, 0.035))
    figure.text(0.02, 0.015, "10 independent lineages per condition. Gap: one unknown Gemini control audit in generation 3.",
                fontsize=9, color="#52606D")
    figure.tight_layout(rect=(0, 0.17, 1, 1))
    save(figure, "spread-inheritance")


def population() -> None:
    records = sessions("population-replication-v4pro-all")
    figure, axis = plt.subplots(figsize=(10.5, 3.5))
    chains = sorted({record["actor"].split("-g")[0] for record in records})
    if len(chains) != 10:
        raise ValueError("Expected ten population chains")
    for chain in chains:
        groups = [[record for record in records if record["actor"].split("-g")[0] == chain
                   and record["generation"] == generation] for generation in range(1, 9)]
        if any(len(group) != 4 for group in groups):
            raise ValueError("Expected four agents per population generation")
        axis.plot(range(1, 9), [cheating_rate(group) for group in groups],
                  color=EXPOSED, alpha=0.16, linewidth=1)
    curve = [cheating_rate([record for record in records if record["generation"] == generation])
             for generation in range(1, 9)]
    axis.plot(range(1, 9), curve, color=EXPOSED, marker="o", linewidth=2.5)
    axis.set(xlabel="Generation", ylabel="Cheating rate", xticks=range(1, 9),
             yticks=[0, 0.5, 1], ylim=(-0.04, 1.07))
    axis.grid(alpha=0.15)
    axis.text(1.12, 0.35, "16/40 in the first generation", fontsize=11)
    axis.text(4.5, 0.63, "113/120 in generations 6–8", fontsize=12, color=EXPOSED)
    figure.text(0.16, 0.025, "Four V4 Pro agents per generation. Thin lines: 10 independent chains. Thick line: mean.", fontsize=9)
    figure.tight_layout(rect=(0, 0.065, 1, 1))
    save(figure, "spread-population")


def peer_records() -> dict[str, list[dict]]:
    grouped = {}
    for peer in MODELS:
        records = sessions(f"peer-composition-{peer}")
        if len(records) != 160:
            raise ValueError("Expected 160 sessions per peer model")
        recipients = [record for record in records if record["agent"] in (0, 1, 2)]
        if len(recipients) != 120:
            raise ValueError("Expected 120 recipient sessions per peer model")
        if any(record["accepted"] is True and record["audit_ok"] is not True
               and record["cheat"] is not True for record in recipients):
            raise ValueError("Unknown recipient audit")
        grouped[peer] = recipients
    return grouped


def peers() -> None:
    grouped = peer_records()
    figure, axes = plt.subplots(2, 3, figsize=(12, 4.7), sharex=True, sharey=True)
    for axis, (peer, records), color in zip(axes.flat, grouped.items(), COLORS):
        groups = [[record for record in records if record["generation"] == generation]
                  for generation in range(1, 9)]
        if any(len(group) != 15 for group in groups):
            raise ValueError("Expected fifteen recipients per generation")
        axis.axvspan(5.5, 8.3, color="#EAF0F3", zorder=0)
        axis.plot(range(1, 9), [cheating_rate(group) for group in groups],
                  color=color, marker="o", linewidth=2, markersize=4)
        axis.set(title=f"Peer: {MODELS[peer]}", xticks=[1, 4, 8], yticks=[0, 0.5, 1],
                 ylim=(-0.05, 1.05), xlim=(0.7, 8.3))
        axis.grid(alpha=0.12)
    for axis in axes[-1]:
        axis.set_xlabel("Generation")
    for axis in axes[:, 0]:
        axis.set_ylabel("Recipient cheating")
    figure.text(0.11, 0.015, "Each point: 15 V4 Pro recipients across 5 independent chains. Shading: generations 6–8.", fontsize=9)
    figure.tight_layout(rect=(0, 0.055, 1, 1))
    save(figure, "spread-peers")

    figure, axis = plt.subplots(figsize=(10.5, 3.7))
    table = []
    analysis = json.loads((ROOT / "report/final/peer-composition-analysis.json").read_text())
    for position, (peer, records) in enumerate(grouped.items()):
        late = [record for record in records if record["generation"] >= 6]
        chains = sorted({record["actor"].split("-g")[0] for record in late})
        if len(late) != 45 or len(chains) != 5:
            raise ValueError("Expected five chains and 45 late recipient sessions")
        for offset, chain in enumerate(chains):
            members = [record for record in late if record["actor"].split("-g")[0] == chain]
            if len(members) != 9:
                raise ValueError("Expected nine late recipients per chain")
            rate = cheating_rate(members)
            expected = analysis["arms"][peer]["chains"][offset]
            if expected["chain"] != chain or rate != expected["rate"]:
                raise ValueError("CSV and frozen chain analysis disagree")
            axis.scatter(rate, position + (offset - 2) * 0.085, color=COLORS[position], s=55)
        cheats = sum(record["cheat"] is True for record in late)
        clean = sum(record["audit_ok"] is True and record["cheat"] is False for record in late)
        if cheats + clean != 45:
            raise ValueError("Late outcomes are not exclusively cheating or audit-clean")
        table.append(f"{MODELS[peer]} & {cheats}/45 & {clean}/45 \\\\\n")
    axis.set(yticks=range(len(MODELS)), yticklabels=list(MODELS.values()),
             xlabel="Late recipient cheating rate", xlim=(-0.04, 1.04), xticks=[0, 0.5, 1])
    axis.invert_yaxis()
    axis.grid(axis="x", alpha=0.15)
    figure.text(0.27, 0.015, "Each dot: one independent chain, 9 V4 Pro recipient sessions in generations 6–8.", fontsize=9)
    figure.tight_layout(rect=(0, 0.065, 1, 1))
    save(figure, "spread-chains")
    (DESTINATION / "tables/spread-peer-outcomes.tex").write_text("".join(table))


def main() -> None:
    plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.titleweight": "bold", "axes.labelcolor": "#263745",
                         "text.color": "#263745", "font.family": "DejaVu Sans"})
    exposure()
    solvable()
    inheritance()
    population()
    peers()
    print("Six spread figures and the peer outcome table match frozen outcomes.")


if __name__ == "__main__":
    main()
