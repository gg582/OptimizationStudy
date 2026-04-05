import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

# --- Finite-field helpers reused from earlier Choi constructions -------------
FIELD_DEGREE = 6
FIELD_SIZE = 1 << FIELD_DEGREE
FIELD_MASK = FIELD_SIZE - 1
PRIMITIVE_POLY = 0b1000011  # x^6 + x + 1


def gf_mul(a, b):
    res = 0
    while b:
        if b & 1:
            res ^= a
        b >>= 1
        a <<= 1
        if a & FIELD_SIZE:
            a ^= PRIMITIVE_POLY
        a &= FIELD_MASK
    return res & FIELD_MASK


def build_gf_latin(multiplier, n=FIELD_SIZE):
    if n != FIELD_SIZE:
        raise ValueError("GF-based generator currently supports only n = 64.")
    square = np.zeros((n, n), dtype=int)
    for i in range(n):
        for j in range(n):
            square[i, j] = i ^ gf_mul(multiplier, j)
    return square


def build_magic_orthogonal_latin(multiplier_a, multiplier_b, n=FIELD_SIZE):
    latin_a = build_gf_latin(multiplier_a, n)
    latin_b = build_gf_latin(multiplier_b, n)
    return latin_a * n + latin_b + 1  # shift to 1..n^2 for Siamese analysis


def derive_reverse_siamese(square):
    """Mirror horizontally and apply complement to mimic B_{i,j} = c - A_{i,n+1-j}."""
    complement_const = square.size + 1
    return complement_const - square[:, ::-1]


# --- Simulation rules -------------------------------------------------------
def compute_total_input(n, rng):
    flood_wave = np.tile(np.linspace(0.012, 0.068, n), (n, 1))
    noise = rng.normal(0.011, 0.0055, (n, n))
    return flood_wave + noise


def update_original(state, ls_grid, reverse_grid, total_input, t):
    """Choi's original reverse-Siamese: pairwise complement actions."""
    updated = state + total_input
    updated[ls_grid % 4 == (t % 4)] *= 0.92

    # Pairwise damping with the mirrored/complement partner
    if t % 7 == 0:
        partner_mask = reverse_grid % 8 == (t % 8)
        updated[partner_mask] *= 0.94

    if np.mean(updated) > 0.33 and t % 12 == 0:
        # Apply the reverse-Siamese action: horizontal reflection + complement
        updated = 1.0 - np.fliplr(updated)

    updated *= 0.986
    np.clip(updated, 0, 1, out=updated)
    return updated


def update_reinterpretation(state, ls_grid, total_input, t):
    """Reverse-Siamese reinterpretation with gradient-aware flipping."""
    updated = state + total_input
    updated[ls_grid % 4 == (t % 4)] *= 0.90

    if np.mean(updated) > 0.32:
        dy, dx = np.gradient(updated)
        avg_dx = np.mean(dx)
        avg_dy = np.mean(dy)
        if abs(avg_dx) > abs(avg_dy) * 1.15:
            updated = np.fliplr(updated)
        elif abs(avg_dy) > abs(avg_dx) * 1.15:
            updated = np.flipud(updated)
        else:
            updated = updated.T

    updated *= 0.986
    np.clip(updated, 0, 1, out=updated)
    return updated


def run_comparison():
    n = 64
    rng = np.random.default_rng(2024)
    checkpoints = [25, 150, 500, 1500, 4000, 8000]

    magic_grid = build_magic_orthogonal_latin(3, 5, n)
    reverse_grid = derive_reverse_siamese(magic_grid)

    state_original = rng.uniform(0.05, 0.11, (n, n))
    state_reinterpreted = state_original.copy()

    history = {}
    for t in range(1, max(checkpoints) + 1):
        total_input = compute_total_input(n, rng)
        state_original = update_original(
            state_original, magic_grid, reverse_grid, total_input, t
        )
        state_reinterpreted = update_reinterpretation(
            state_reinterpreted, magic_grid, total_input, t
        )
        if t in checkpoints:
            history[t] = [state_original.copy(), state_reinterpreted.copy()]

    col_titles = [
        "Choi Original\n(Reverse Siamese Pairing)",
        "Reinterpretation\n(Gradient-Aware)",
    ]
    return history, checkpoints, col_titles


def gather_complexity_records(n=FIELD_SIZE):
    cell_count = n * n
    per_step = f"O({cell_count}) ≈ O(n^2)"
    space = f"O({cell_count}) states + grids"
    return [
        {
            "Algorithm": "Reverse Siamese",
            "Siamese Direction": "Reverse (up-left, original)",
            "Dominant Ops": "Mirror pairs + complement damping",
            "Time Complexity": f"{per_step} + partner mask",
            "Space Complexity": f"{space} + reverse grid",
            "Notes": "Choi's original manuscript maintains mirrored pairs for relief.",
        },
        {
            "Algorithm": "Reinterpretation",
            "Siamese Direction": "Forward (interpreted)",
            "Dominant Ops": "Gradient sensing + adaptive flip",
            "Time Complexity": per_step,
            "Space Complexity": space,
            "Notes": "Modern view that uses directional cues from congestion flow.",
        },
    ]


def print_complexity_table(n=FIELD_SIZE):
    records = gather_complexity_records(n)
    columns = [
        "Algorithm",
        "Siamese Direction",
        "Dominant Ops",
        "Time Complexity",
        "Space Complexity",
        "Notes",
    ]
    widths = {col: len(col) for col in columns}
    for rec in records:
        for col in columns:
            widths[col] = max(widths[col], len(rec[col]))

    def _format_row(row):
        return " | ".join(f"{row[col]:<{widths[col]}}" for col in columns)

    separator = "-+-".join("-" * widths[col] for col in columns)
    print("\nComplexity Comparison (n = {} cells)".format(n))
    print(_format_row({col: col for col in columns}))
    print(separator)
    for rec in records:
        print(_format_row(rec))
    print()


def visualize_comparison():
    sim_data, checkpoints, col_titles = run_comparison()
    rows = len(checkpoints)
    fig, axes = plt.subplots(rows, 2, figsize=(11, 3.2 * rows))
    cmap = LinearSegmentedColormap.from_list(
        "net_dynamic",
        ["#000033", "#1E90FF", "#FFFF00", "#FF4500", "#8B0000"],
    )

    for r, t in enumerate(checkpoints):
        for c in range(2):
            ax = axes[r, c]
            im = ax.imshow(
                sim_data[t][c], cmap=cmap, vmin=0, vmax=1, interpolation="gaussian"
            )
            if r == 0:
                ax.set_title(col_titles[c], fontsize=11, fontweight="bold", pad=14)
            if c == 0:
                ax.set_ylabel(f"Step {t}", fontweight="bold", labelpad=16)
            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_visible(False)

    cbar_ax = fig.add_axes([0.28, 0.04, 0.44, 0.012])
    fig.colorbar(im, cax=cbar_ax, orientation="horizontal").set_label(
        "Congestion Level (0.0 to 1.0)"
    )
    plt.suptitle(
        "Choi Original vs. Reinterpretation (Order-64)",
        fontweight="bold",
        fontsize=7,
        y=0.998,
    )
    plt.subplots_adjust(hspace=0.35, wspace=0.15, bottom=0.08, top=0.94)
    plt.show()


if __name__ == "__main__":
    print_complexity_table()
    visualize_comparison()
