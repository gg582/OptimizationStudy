import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

def generate_mols_base(n=64):
    return np.array([np.roll(np.arange(n), i) for i in range(n)])

def update_load_directional_bench(states, ls_grid, t, n=64):
    """
    Comparison: Standard Nonlinear vs. Directional Nonlinear
    1. Standard Nonlinear: MOLS Damping + Random Flip (No direction awareness)
    2. Directional Nonlinear: MOLS Damping + Gradient-based Optimal Flip/T
    """
    std_nl, dir_nl = states
    
    # Baseline Noise
    noise = np.random.normal(0.015, 0.008, (n, n))
    
    # --- 1. Standard Nonlinear (Blind Symmetry) ---
    std_nl += noise
    # MOLS Damping
    target_group = t % 4
    std_nl[ls_grid % 4 == target_group] *= 0.90
    
    # Blind Symmetry: Fixed or random structural change regardless of flow
    if np.mean(std_nl) > 0.35 and t % 15 == 0:
        # Just cycles through transformations without checking gradient
        modes = [lambda x: x.T, lambda x: np.flipud(x), lambda x: np.fliplr(x)]
        std_nl = modes[t % 3](std_nl)
    
    std_nl *= 0.988
    std_nl = np.clip(std_nl, 0, 1)
    
    # --- 2. Directional Nonlinear (Gradient-Aware Symmetry) ---
    dir_nl += noise
    # MOLS Damping
    dir_nl[ls_grid % 4 == target_group] *= 0.90
    
    # Directional Logic: Analyzes the spatial pressure before acting
    if np.mean(dir_nl) > 0.3:
        dy, dx = np.gradient(dir_nl)
        avg_dy, avg_dx = np.mean(dy), np.mean(dx)
        
        # Actively counteracts the dominant congestion vector
        if abs(avg_dx) > abs(avg_dy) * 1.2:
            dir_nl = np.fliplr(dir_nl) # Targeted horizontal reversal
        elif abs(avg_dy) > abs(avg_dx) * 1.2:
            dir_nl = np.flipud(dir_nl) # Targeted vertical reversal
        else:
            dir_nl = dir_nl.T           # Targeted diagonal cross-swap
            
    dir_nl *= 0.988
    dir_nl = np.clip(dir_nl, 0, 1)

    return [std_nl, dir_nl]

def run_comparison_sim():
    n = 64
    ls_grid = generate_mols_base(n)
    checkpoints = [100, 500, 1000, 2500, 5000, 10000]
    results = {}
    
    states = [np.random.uniform(0.05, 0.15, (n, n)) for _ in range(2)]
    
    for t in range(1, max(checkpoints) + 1):
        states = update_load_directional_bench(states, ls_grid, t, n)
        if t in checkpoints:
            results[t] = [s.copy() for s in states]
            
    return results, checkpoints

def visualize_comparison():
    sim_data, checkpoints = run_comparison_sim()
    num_rows = len(checkpoints)
    
    fig, axes = plt.subplots(num_rows, 2, figsize=(10, 3 * num_rows))
    cmap = LinearSegmentedColormap.from_list("net_dynamic", ["#000033", "#1E90FF", "#FFFF00", "#FF4500", "#8B0000"])
    
    col_titles = ["Standard Nonlinear\n(Blind Symmetry)", "Directional Nonlinear\n(Gradient-Aware)"]
    
    for r, t in enumerate(checkpoints):
        row_data = sim_data[t]
        for c in range(2):
            ax = axes[r, c]
            im = ax.imshow(row_data[c], cmap=cmap, vmin=0, vmax=1, interpolation='gaussian')
            
            if r == 0:
                ax.set_title(col_titles[c], fontsize=11, pad=15, fontweight='bold')
            if c == 0:
                ax.set_ylabel(f"T = {t}", fontsize=12, fontweight='bold', labelpad=15)
            
            ax.set_xticks([]); ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_visible(False)

    cbar_ax = fig.add_axes([0.3, 0.04, 0.4, 0.01])
    fig.colorbar(im, cax=cbar_ax, orientation='horizontal').set_label('Saturation Density')
    
    plt.subplots_adjust(hspace=0.3, wspace=0.1, bottom=0.08, top=0.94)
    plt.show()

if __name__ == "__main__":
    visualize_comparison()
