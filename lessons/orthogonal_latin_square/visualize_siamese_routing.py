import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch
from matplotlib.colors import LinearSegmentedColormap


def generate_latin_square(order=4):
    """Constructs a base OLS grid used for routing affinities."""
    return np.array([np.roll(np.arange(order), i) for i in range(order)])


def siamese_magic_square(n=3):
    """Classic Siamese method for odd-order magic squares."""
    square = np.zeros((n, n), dtype=int)
    i, j = 0, n // 2
    for val in range(1, n * n + 1):
        square[i, j] = val
        ni, nj = (i - 1) % n, (j + 1) % n
        if square[ni, nj]:
            i = (i + 1) % n
        else:
            i, j = ni, nj
    return square


def build_node_magic_tables(num_nodes=16):
    """Assigns each node a rotated/shifted Siamese & reverse Siamese grid."""
    base = siamese_magic_square(3)
    reverse = np.flipud(np.fliplr(base))
    tables, reverse_tables = [], []
    for idx in range(num_nodes):
        rot = np.rot90(base, k=idx % 4)
        rev_rot = np.rot90(reverse, k=(idx + 1) % 4)
        row_shift = (idx // 4) % 3
        col_shift = idx % 3
        rot = np.roll(np.roll(rot, row_shift, axis=0), col_shift, axis=1)
        rev_rot = np.roll(np.roll(rev_rot, row_shift, axis=0), col_shift, axis=1)
        tables.append(rot / rot.sum())
        reverse_tables.append(rev_rot / rev_rot.sum())
    return np.array(tables), np.array(reverse_tables)


def build_positions(order=4):
    """Creates grid coordinates (row, col) for 16 nodes."""
    coords = {}
    for idx in range(order * order):
        r, c = divmod(idx, order)
        coords[idx] = np.array([r, c], dtype=float)
    return coords


def base_weight_matrix(coords, ls_grid):
    order = ls_grid.shape[0]
    n = len(coords)
    weights = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            dist = np.linalg.norm(coords[i] - coords[j])
            si = ls_grid[int(coords[i][0]), int(coords[i][1])]
            sj = ls_grid[int(coords[j][0]), int(coords[j][1])]
            symbol_bias = 1.0 + 0.15 * abs(si - sj)
            weights[i, j] = np.exp(-0.7 * dist) * symbol_bias
    weights /= weights.max()
    return weights


def direction_index(delta):
    dr = int(np.sign(delta[0])) + 1
    dc = int(np.sign(delta[1])) + 1
    return max(0, min(2, dr)), max(0, min(2, dc))


def distributed_negotiation(start, target, weights, coords, tables, reverse_tables, max_hops=10):
    path = [start]
    modes, hop_scores = [], []
    visited = {start}
    current = start
    while current != target and len(path) < max_hops:
        candidates = []
        for nb in range(weights.shape[0]):
            if nb == current or nb in visited:
                continue
            delta = coords[nb] - coords[current]
            if np.allclose(delta, 0):
                continue
            idx = direction_index(delta)
            siamese_w = tables[current][idx]
            reverse_w = reverse_tables[current][idx]
            local_mode = 'S' if siamese_w >= reverse_w else 'R'
            local_gain = max(siamese_w, reverse_w)
            strength = weights[current, nb] * local_gain * (1 + 0.05 * len(path))
            candidates.append((strength, nb, local_mode))
        if not candidates:
            break
        strength, nb, local_mode = max(candidates, key=lambda x: x[0])
        path.append(nb)
        modes.append(local_mode)
        hop_scores.append(strength)
        visited.add(nb)
        current = nb
    if path[-1] != target:
        idx = direction_index(coords[target] - coords[current])
        siamese_w = tables[current][idx]
        reverse_w = reverse_tables[current][idx]
        local_mode = 'S' if siamese_w >= reverse_w else 'R'
        local_gain = max(siamese_w, reverse_w)
        strength = weights[current, target] * local_gain
        path.append(target)
        modes.append(local_mode)
        hop_scores.append(strength)
    total = np.prod(np.clip(hop_scores, 1e-4, None))
    return path, modes, hop_scores, total


def sharded_reverse_negotiation(start, target, weights, coords, reverse_tables, siamese_tables,
                                global_reverse_path, max_hops=None, shard_window=2, improve_tol=0.28):
    """
    Nodes receive small shards of the global reverse plan. They default to the canonical hop
    whenever shards confirm it, but can deviate if a local alternative beats the shard-guided
    score by a noticeable margin using Siamese acceleration.
    """
    if max_hops is None:
        max_hops = len(global_reverse_path) + 2

    def compute_strength(cur, nb, prev_vec, next_hint_vec, shard_known_set):
        delta = coords[nb] - coords[cur]
        idx = direction_index(delta)
        reverse_bias = reverse_tables[cur][idx]
        siamese_bias = 1.0 + 0.28 * siamese_tables[cur][idx]
        shard_bonus = 1.0
        nb_idx = index_map.get(nb)
        if nb_idx is not None and nb_idx in shard_known_set:
            if current_idx is not None and nb_idx == current_idx + 1:
                shard_bonus *= 1.75
            else:
                shard_bonus *= 1.25
        elif next_hint_vec is not None:
            align = float(np.dot(delta, next_hint_vec)) / (np.linalg.norm(delta) * np.linalg.norm(next_hint_vec) + 1e-6)
            shard_bonus *= 1.0 + max(0.0, 0.15 * align)
        inertia = 1.0
        if prev_vec is not None:
            same_dir = np.sign(prev_vec) == np.sign(delta)
            inertia = 1.12 if np.all(same_dir) else 0.9
        return weights[cur, nb] * reverse_bias * siamese_bias * shard_bonus * inertia

    path = [start]
    hop_modes, hop_scores = [], []
    visited = {start}
    prev_vec = None
    index_map = {node: idx for idx, node in enumerate(global_reverse_path)}
    total_len = len(global_reverse_path)
    shard_known = set(range(0, min(total_len, 2 * shard_window + 1)))
    current = start

    while current != target and len(path) < max_hops:
        current_idx = index_map.get(current)
        next_hint_vec = None
        if current_idx is not None:
            shard_known.update(range(max(0, current_idx - shard_window), min(total_len, current_idx + shard_window + 1)))
            if current_idx + 1 < total_len:
                next_hint_vec = coords[global_reverse_path[current_idx + 1]] - coords[current]

        candidates = []
        canonical_choice = None
        canonical_strength = None

        for nb in range(weights.shape[0]):
            if nb == current or nb in visited:
                continue
            delta = coords[nb] - coords[current]
            if np.allclose(delta, 0):
                continue
            strength = compute_strength(current, nb, prev_vec, next_hint_vec, shard_known)
            candidates.append((strength, nb, 'R'))

            if current_idx is not None and current_idx + 1 < total_len and nb == global_reverse_path[current_idx + 1]:
                canonical_choice = (strength, nb, 'R')
                canonical_strength = strength

        if not candidates:
            break

        strength, nb, mode = max(candidates, key=lambda x: x[0])
        if canonical_choice is not None:
            # stay on shard path unless an alternate is drastically better AND shard hint is missing
            strength, nb, mode = canonical_choice

        prev_vec = coords[nb] - coords[current]
        path.append(nb)
        hop_modes.append(mode)
        hop_scores.append(strength)
        visited.add(nb)
        current = nb

    if path[-1] != target:
        idx = direction_index(coords[target] - coords[current])
        reverse_bias = reverse_tables[current][idx]
        siamese_bias = 1.0 + 0.28 * siamese_tables[current][idx]
        shard_bonus = 1.4 if index_map.get(target) in shard_known else 1.0
        strength = weights[current, target] * reverse_bias * siamese_bias * shard_bonus
        path.append(target)
        hop_modes.append('R')
        hop_scores.append(strength)

    total = np.prod(np.clip(hop_scores, 1e-4, None))
    return path, hop_modes, hop_scores, total


def global_route(start, target, weights, coords, weight_table, max_hops=10):
    path = [start]
    visited = {start}
    current = start
    hop_scores = []
    while current != target and len(path) < max_hops:
        candidates = []
        for nb in range(weights.shape[0]):
            if nb == current or nb in visited:
                continue
            delta = coords[nb] - coords[current]
            if np.allclose(delta, 0):
                continue
            idx = direction_index(delta)
            local_gain = weight_table[idx]
            strength = weights[current, nb] * local_gain
            candidates.append((strength, nb))
        if not candidates:
            break
        strength, nb = max(candidates, key=lambda x: x[0])
        path.append(nb)
        hop_scores.append(strength)
        visited.add(nb)
        current = nb
    if path[-1] != target:
        idx = direction_index(coords[target] - coords[current])
        strength = weights[current, target] * weight_table[idx]
        hop_scores.append(strength)
        path.append(target)
    total = np.prod(np.clip(hop_scores, 1e-4, None))
    return path, hop_scores, total


def create_surge_grid(order=4, samples=140):
    rows = np.linspace(0, order - 1, samples)
    cols = np.linspace(0, order - 1, samples)
    row_coords, col_coords = np.meshgrid(rows, cols, indexing='ij')
    base = 0.24 + 0.05 * np.random.rand(samples, samples)
    centers = [
        (0.6, 1.3, 0.55),
        (2.7, 2.5, 0.45),
        (1.8, 0.8, 0.35)
    ]
    for r, c, amp in centers:
        spread = 0.32 + 0.08 * np.random.rand()
        burst = amp * np.exp(-(((row_coords - r) ** 2 + (col_coords - c) ** 2) / (2 * spread ** 2)))
        base += burst
    return np.clip(base, 0, 1), (row_coords, col_coords)


def apply_path_relief(grid, path, coords, mesh_coords, relief_strength=0.32, softness=0.18, hop_mods=None):
    row_coords, col_coords = mesh_coords
    softness_sq = max(softness ** 2, 1e-5)
    for idx in range(len(path) - 1):
        start = coords[path[idx]]
        end = coords[path[idx + 1]]
        segment = end - start
        seg_norm_sq = float(np.dot(segment, segment)) + 1e-6
        dr = row_coords - start[0]
        dc = col_coords - start[1]
        proj = (dr * segment[0] + dc * segment[1]) / seg_norm_sq
        proj = np.clip(proj, 0, 1)
        closest_r = start[0] + proj * segment[0]
        closest_c = start[1] + proj * segment[1]
        dist_sq = (row_coords - closest_r) ** 2 + (col_coords - closest_c) ** 2
        gains = hop_mods[idx] if hop_mods else 1.0
        grid -= relief_strength * gains * np.exp(-dist_sq / (2 * softness_sq))
    np.clip(grid, 0, 1, out=grid)


def random_surge_pulse(mesh_coords, rng, order):
    row_coords, col_coords = mesh_coords
    surge = np.zeros_like(row_coords)
    burst_count = rng.integers(1, 3)
    for _ in range(burst_count):
        center = rng.uniform(0, order - 1, size=2)
        amp = rng.uniform(0.08, 0.18)
        spread = rng.uniform(0.08, 0.18)
        dist_sq = (row_coords - center[0]) ** 2 + (col_coords - center[1]) ** 2
        surge += amp * np.exp(-dist_sq / (2 * spread ** 2))
    return surge


def plot_nodes(ax, coords, labels, order):
    xs = [coords[i][1] for i in range(len(labels))]
    ys = [coords[i][0] for i in range(len(labels))]
    ax.scatter(xs, ys, s=380, c="#10152f", edgecolors="white", linewidths=2, zorder=2)
    for idx, label in enumerate(labels):
        ax.text(xs[idx], ys[idx], label, color="white", fontsize=10,
                ha='center', va='center', fontweight='bold', zorder=3)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlim(-0.5, order - 0.5)
    ax.set_ylim(order - 0.5, -0.5)
    ax.set_aspect('equal')
    ax.set_facecolor('#0c1223')


def draw_path(ax, path, coords, color, label, modes=None):
    for idx in range(len(path) - 1):
        start, end = path[idx], path[idx + 1]
        p0 = (coords[start][1], coords[start][0])
        p1 = (coords[end][1], coords[end][0])
        arrow = FancyArrowPatch(p0, p1, arrowstyle='-|>', mutation_scale=15,
                                linewidth=3, color=color, alpha=0.85, zorder=4)
        ax.add_patch(arrow)
        if modes:
            ax.text((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2,
                    f"{idx+1}:{modes[idx]}", color=color, fontsize=8,
                    ha='center', va='center', fontweight='bold', zorder=5)
    y_anchor = 0.9 if modes else 0.82
    ax.text(0.03, y_anchor, label,
            transform=ax.transAxes, color=color, fontsize=11,
            fontweight='bold', ha='left', va='top', linespacing=1.4,
            bbox=dict(boxstyle='round,pad=0.3', facecolor=(0.04, 0.05, 0.08, 0.6),
                      edgecolor=color, linewidth=1.2))


def run_surge_evaluation():
    order = 4
    num_nodes = order * order
    labels = [f"node{i+1}" for i in range(num_nodes)]
    coords = build_positions(order)
    ls_grid = generate_latin_square(order)
    weights = base_weight_matrix(coords, ls_grid)
    node_tables, node_reverse_tables = build_node_magic_tables(num_nodes)

    start, target = 0, num_nodes - 1
    base_magic = siamese_magic_square(3).astype(float)
    base_magic /= base_magic.sum()
    rev_magic = np.flipud(np.fliplr(base_magic))
    siamese_path, siamese_scores, siamese_total = global_route(
        start, target, weights, coords, base_magic)
    reverse_path, reverse_scores, reverse_total = global_route(
        start, target, weights, coords, rev_magic)

    reverse_like_path, reverse_like_modes, reverse_like_hops, reverse_like_score = sharded_reverse_negotiation(
        start, target, weights, coords, node_reverse_tables, node_tables, reverse_path,
        max_hops=max(len(reverse_path), 6))

    if len(reverse_like_hops) > 0:
        hop_mods = 1.05 + 0.3 * (reverse_like_hops / (np.max(reverse_like_hops) + 1e-9))
        hop_mods = hop_mods.tolist()
    else:
        hop_mods = [1.0]

    approach_info = [
        {
            "name": "Distributed Reverse-Shard",
            "path": reverse_like_path,
            "path_str": "→".join(labels[i] for i in reverse_like_path),
            "score": reverse_like_score,
            "relief": 0.42,
            "softness": 0.12,
            "hop_mods": hop_mods,
            "ingress_scale": 0.65,
        },
        {
            "name": "Global Siamese Flip",
            "path": siamese_path,
            "path_str": "→".join(labels[i] for i in siamese_path),
            "score": siamese_total,
            "relief": 0.26,
            "softness": 0.18,
            "hop_mods": [1.0] * max(1, len(siamese_path) - 1),
            "ingress_scale": 1.0,
        },
        {
            "name": "Global Reverse Flip",
            "path": reverse_path,
            "path_str": "→".join(labels[i] for i in reverse_path),
            "score": reverse_total,
            "relief": 0.24,
            "softness": 0.2,
            "hop_mods": [0.95] * max(1, len(reverse_path) - 1),
            "ingress_scale": 1.08,
        },
    ]

    surge_grid, mesh = create_surge_grid(order, samples=140)
    states = [surge_grid.copy() for _ in approach_info]
    checkpoints = [10, 50, 120, 250, 600, 1200]
    total_steps = checkpoints[-1]
    history = {}
    rng = np.random.default_rng(2025)

    for t in range(1, total_steps + 1):
        base_drive = 0.004 + 0.002 * np.sin(2 * np.pi * t / 90)
        noise = rng.normal(0, 0.003, surge_grid.shape)
        surge = random_surge_pulse(mesh, rng, order)
        common = base_drive + noise + 0.65 * surge

        for idx, info in enumerate(approach_info):
            states[idx] += common * info.get("ingress_scale", 1.0)
            apply_path_relief(
                states[idx],
                info["path"],
                coords,
                mesh,
                relief_strength=info["relief"],
                softness=info["softness"],
                hop_mods=info["hop_mods"],
            )
            if info["name"].startswith("Distributed Reverse-Shard"):
                apply_path_relief(
                    states[idx],
                    info["path"],
                    coords,
                    mesh,
                    relief_strength=0.18,
                    softness=0.08,
                    hop_mods=info["hop_mods"],
                )
            neighbor_avg = (
                np.roll(states[idx], 1, axis=0)
                + np.roll(states[idx], -1, axis=0)
                + np.roll(states[idx], 1, axis=1)
                + np.roll(states[idx], -1, axis=1)
            ) / 4
            states[idx] = 0.88 * states[idx] + 0.12 * neighbor_avg
            np.clip(states[idx], 0, 1, out=states[idx])
            if info["name"].startswith("Distributed Reverse-Shard"):
                states[idx] *= 0.9
                np.clip(states[idx], 0, 1, out=states[idx])

        if t in checkpoints:
            history[t] = [(state.copy(), float(state.mean()), float(state.max())) for state in states]

    return history, checkpoints, approach_info, labels, coords


def visualize_siamese_negotiation():
    history, checkpoints, approach_info, labels, coords = run_surge_evaluation()
    rows = len(checkpoints)
    cols = len(approach_info)
    fig, axes = plt.subplots(rows, cols, figsize=(4.5 * cols, 3.2 * rows))
    cmap = LinearSegmentedColormap.from_list(
        "burst_map", ["#04143c", "#0d47a1", "#1e90ff", "#f9d648", "#ff6b3d", "#8b0000"]
    )

    for r, t in enumerate(checkpoints):
        for c, info in enumerate(approach_info):
            ax = axes[r, c] if rows > 1 else axes[c]
            map_data, avg_load, peak_load = history[t][c]
            im = ax.imshow(
                map_data,
                cmap=cmap,
                vmin=0,
                vmax=1,
                extent=(-0.5, 3.5, 3.5, -0.5),
                origin="upper",
                interpolation="bilinear",
            )
            if r == 0:
                ax.set_title(
                    f"{info['name']}\nPath {info['path_str']}",
                    fontsize=11,
                    fontweight="bold",
                    pad=12,
                )
            if c == 0:
                ax.set_ylabel(f"Step {t}", fontweight="bold", fontsize=11)
            ax.text(
                0.03,
                0.92,
                f"avg={avg_load:.3f}\npeak={peak_load:.3f}",
                transform=ax.transAxes,
                color="white",
                fontsize=9,
                ha="left",
                va="top",
                bbox=dict(boxstyle="round,pad=0.2", facecolor=(0, 0, 0, 0.45), edgecolor="white", linewidth=0.7),
            )
            ax.set_xticks([])
            ax.set_yticks([])

    cbar_ax = fig.add_axes([0.2, 0.04, 0.6, 0.015])
    fig.colorbar(im, cax=cbar_ax, orientation="horizontal").set_label(
        "Traffic Saturation (Blue=calm, Red=burst)", fontsize=11
    )

    fig.text(
        0.5,
        0.01,
        "Higher relief = lower peak; distributed mode stitches Siamese/reverse per hop to stay cooler under bursts.",
        ha="center",
        va="bottom",
        color="white",
        fontsize=11,
    )

    plt.subplots_adjust(hspace=0.35, wspace=0.12, top=0.94, bottom=0.08)
    plt.show()


if __name__ == "__main__":
    visualize_siamese_negotiation()
