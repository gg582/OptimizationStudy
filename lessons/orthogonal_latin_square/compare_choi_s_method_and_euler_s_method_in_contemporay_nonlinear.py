import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

# --- Euler's baseline orthogonal Latin square (non-magic) --------------------
def generate_euler_baseline(n=64):
    idx = np.arange(n)
    return (idx[:, None] + idx[None, :]) % n


# --- Choi's orthogonal Latin squares that also form magic squares ------------
FIELD_DEGREE = 6
FIELD_SIZE = 1 << FIELD_DEGREE
FIELD_MASK = FIELD_SIZE - 1
PRIMITIVE_POLY = 0b1000011  # x^6 + x + 1


def gf_mul(a, b):
    """Finite-field multiply in GF(2^6) using x^6 + x + 1."""
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
    return latin_a * n + latin_b


def generate_choi_magic_variants(n=64):
    if n != FIELD_SIZE:
        raise ValueError("Magic variants are aligned with the 64x64 study grid.")

    # Two Choi-style constructions built from distinct multiplier pairs.
    multiplier_pairs = [(3, 5), (7, 11)]
    grids, labels = [], []
    for a, b in multiplier_pairs:
        grids.append(build_magic_orthogonal_latin(a, b, n))
        labels.append(f"Choi Magic (mult={a},{b})")
    return grids, labels


# --- Shared simulation logic -------------------------------------------------
def compute_total_input(n, rng):
    flood_wave = np.tile(np.linspace(0.015, 0.07, n), (n, 1))
    noise = rng.normal(0.012, 0.006, (n, n))
    return flood_wave + noise


def update_blind(state, ls_grid, total_input, t):
    blind = state + total_input
    blind[ls_grid % 4 == (t % 4)] *= 0.90
    if np.mean(blind) > 0.35 and t % 15 == 0:
        mode = t % 3
        if mode == 0:
            blind = blind.T
        elif mode == 1:
            blind = np.flipud(blind)
        else:
            blind = np.fliplr(blind)
    blind *= 0.985
    np.clip(blind, 0, 1, out=blind)
    return blind


def update_directional(state, ls_grid, total_input, t):
    directional = state + total_input
    directional[ls_grid % 4 == (t % 4)] *= 0.90
    if np.mean(directional) > 0.3:
        dy, dx = np.gradient(directional)
        avg_dx = np.mean(dx)
        avg_dy = np.mean(dy)
        if abs(avg_dx) > abs(avg_dy) * 1.2:
            directional = np.fliplr(directional)
        elif abs(avg_dy) > abs(avg_dx) * 1.2:
            directional = np.flipud(directional)
        else:
            directional = directional.T
    directional *= 0.985
    np.clip(directional, 0, 1, out=directional)
    return directional


def run_comparison():
    n = 64
    checkpoints = [10, 100, 500, 1000, 5000, 10000]
    rng = np.random.default_rng(2024)

    euler_grid = generate_euler_baseline(n)
    choi_grids, choi_labels = generate_choi_magic_variants(n)
    ls_refs = [euler_grid, euler_grid, *choi_grids]
    col_titles = [
        "Euler – Blind Shuffle\n(Orthogonal Latin Only)",
        "Euler – Directional Flow\n(Orthogonal Latin Only)",
        f"{choi_labels[0]}\n(Orthogonal Latin ∩ Magic)",
        f"{choi_labels[1]}\n(Orthogonal Latin ∩ Magic)",
    ]

    seed_state = rng.uniform(0.05, 0.1, (n, n))
    states = [seed_state.copy() for _ in range(4)]
    history = {}

    for t in range(1, max(checkpoints) + 1):
        total_input = compute_total_input(n, rng)
        states[0] = update_blind(states[0], ls_refs[0], total_input, t)
        states[1] = update_directional(states[1], ls_refs[1], total_input, t)
        states[2] = update_blind(states[2], ls_refs[2], total_input, t)
        states[3] = update_directional(states[3], ls_refs[3], total_input, t)
        if t in checkpoints:
            history[t] = [s.copy() for s in states]

    return history, checkpoints, col_titles


def visualize_comparison():
    sim_data, checkpoints, col_titles = run_comparison()
    rows = len(checkpoints)
    fig, axes = plt.subplots(rows, 4, figsize=(16, 20))
    cmap = LinearSegmentedColormap.from_list(
        "net_dynamic",
        ["#000033", "#1E90FF", "#FFFF00", "#FF4500", "#8B0000"],
    )

    for r, t in enumerate(checkpoints):
        for c in range(4):
            ax = axes[r, c]
            im = ax.imshow(
                sim_data[t][c], cmap=cmap, vmin=0, vmax=1, interpolation="gaussian"
            )
            if r == 0:
                ax.set_title(col_titles[c], fontweight="bold", fontsize=11, pad=14)
            if c == 0:
                ax.set_ylabel(f"Step {t}", fontweight="bold", labelpad=18)
            ax.set_xticks([])
            ax.set_yticks([])

    cbar_ax = fig.add_axes([0.15, 0.04, 0.7, 0.012])
    fig.colorbar(im, cax=cbar_ax, orientation="horizontal").set_label(
        "Congestion Level (0.0 to 1.0)"
    )

    plt.subplots_adjust(hspace=0.3, wspace=0.1, bottom=0.08, top=0.95)
    plt.show()


if __name__ == "__main__":
    visualize_comparison()
