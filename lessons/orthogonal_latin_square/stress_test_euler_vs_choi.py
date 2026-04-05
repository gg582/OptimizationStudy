"""
Stress test comparing:
1. Euler's historical cyclic orthogonal Latin square (using his blind shuffle).
2. Choi Seok-jung's magic orthogonal Latin square with reverse-Siamese pairing.
Runs to T=8000 with basic visualization for the recorded checkpoints.
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

from compare_choi_s_method_and_euler_s_method_in_contemporay_nonlinear import (
    FIELD_SIZE,
    build_magic_orthogonal_latin,
    generate_euler_baseline,
    update_blind as update_euler_cyclic,
)
from choi_s_original_algorithm_vs_reintepretation import derive_reverse_siamese


def compute_total_input(n, rng):
    """Shared deterministic forcing profile + noise."""
    gradient = np.tile(np.linspace(0.012, 0.07, n), (n, 1))
    noise = rng.normal(0.011, 0.0055, (n, n))
    return gradient + noise


def update_reverse_siamese(state, ls_grid, reverse_grid, total_input, t):
    """
    Reverse-Siamese update shared by both Euler and Choi variants.
    ls_grid configures the damping groups while reverse_grid sets pair masks.
    """
    updated = state + total_input
    updated[ls_grid % 4 == (t % 4)] *= 0.92

    if t % 7 == 0:
        partner_mask = (reverse_grid % 8) == (t % 8)
        updated[partner_mask] *= 0.94

    if np.mean(updated) > 0.33 and t % 12 == 0:
        updated = 1.0 - np.fliplr(updated)

    updated *= 0.985
    np.clip(updated, 0, 1, out=updated)
    return updated


def summarize_state(state):
    return {
        "mean": float(np.mean(state)),
        "std": float(np.std(state)),
        "min": float(np.min(state)),
        "max": float(np.max(state)),
    }


def run_euler_vs_choi(
    n=FIELD_SIZE,
    T=8000,
    checkpoints=(25, 150, 600, 2000, 4000, 6000, 8000),
    seed=2024,
):
    if n != FIELD_SIZE:
        raise ValueError("This stress test is calibrated for 64x64 grids.")

    rng = np.random.default_rng(seed)
    euler_grid = generate_euler_baseline(n)
    choi_grid = build_magic_orthogonal_latin(3, 5, n)
    choi_reverse = derive_reverse_siamese(choi_grid)

    seed_state = rng.uniform(0.05, 0.1, (n, n))
    states = {
        "Euler": seed_state.copy(),
        "Choi": seed_state.copy(),
    }
    grids = {"Euler": euler_grid, "Choi": (choi_grid, choi_reverse)}

    history_stats = []
    history_fields = {}

    for t in range(1, T + 1):
        total_input = compute_total_input(n, rng)
        states["Euler"] = update_euler_cyclic(states["Euler"], grids["Euler"], total_input, t)
        choi_ls, choi_rev = grids["Choi"]
        states["Choi"] = update_reverse_siamese(
            states["Choi"], choi_ls, choi_rev, total_input, t
        )

        if t in checkpoints:
            history_stats.append(
                {
                    "T": t,
                    "Euler": summarize_state(states["Euler"]),
                    "Choi": summarize_state(states["Choi"]),
                }
            )
            history_fields[t] = (states["Euler"].copy(), states["Choi"].copy())

    return history_stats, history_fields, checkpoints


def print_report(records):
    header = (
        f"{'T':>6} | "
        f"{'Euler mean':>11} {'Euler std':>10} {'Euler min':>10} {'Euler max':>10} | "
        f"{'Choi mean':>11} {'Choi std':>10} {'Choi min':>10} {'Choi max':>10}"
    )
    print(header)
    print("-" * len(header))
    for rec in records:
        e = rec["Euler"]
        c = rec["Choi"]
        print(
            f"{rec['T']:6d} | "
            f"{e['mean']:11.4f} {e['std']:10.4f} {e['min']:10.4f} {e['max']:10.4f} | "
            f"{c['mean']:11.4f} {c['std']:10.4f} {c['min']:10.4f} {c['max']:10.4f}"
        )


def visualize_history(field_history, checkpoints):
    rows = len(checkpoints)
    fig, axes = plt.subplots(rows, 2, figsize=(12, 3.2 * rows))
    cmap = LinearSegmentedColormap.from_list(
        "reverse_siamese",
        ["#03045E", "#0077B6", "#00B4D8", "#FFD166", "#EF476F"],
    )
    col_titles = [
        "Euler Orthogonal Latin\n(Blind Shuffle)",
        "Choi Magic Latin\n(Reverse Siamese)",
    ]

    for r, t in enumerate(checkpoints):
        euler_field, choi_field = field_history[t]
        for c, data in enumerate([euler_field, choi_field]):
            ax = axes[r, c]
            im = ax.imshow(data, cmap=cmap, vmin=0, vmax=1, interpolation="gaussian")
            if r == 0:
                ax.set_title(col_titles[c], fontweight="bold", fontsize=11, pad=14)
            if c == 0:
                ax.set_ylabel(f"T = {t}", fontweight="bold", labelpad=16)
            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_visible(False)

    cbar_ax = fig.add_axes([0.28, 0.04, 0.44, 0.012])
    fig.colorbar(im, cax=cbar_ax, orientation="horizontal").set_label(
        "Congestion Level (0.0 to 1.0)"
    )
    plt.subplots_adjust(hspace=0.35, wspace=0.12, bottom=0.08, top=0.95)
    plt.show()


def test_reverse_siamese_outperforms_euler():
    """Regression: Choi's reverse Siamese keeps mean lower than Euler cyclic."""
    stats, _, _ = run_euler_vs_choi()
    assert stats[-1]["T"] == 8000
    final_euler = stats[-1]["Euler"]
    final_choi = stats[-1]["Choi"]

    assert final_choi["mean"] < 0.75
    assert final_euler["mean"] - final_choi["mean"] > 0.2


if __name__ == "__main__":
    print("=== Euler (original) vs. Choi (reverse Siamese) up to T=8000 ===")
    stats, field_history, checkpoints = run_euler_vs_choi()
    print_report(stats)
    visualize_history(field_history, checkpoints)
