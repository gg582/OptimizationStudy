import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

def generate_mols_base(n=64):
    return np.array([np.roll(np.arange(n), i) for i in range(n)])

def update_load_fair_stress(states, ls_grid, t, n=64):
    blind, directional = states
    
    # 1. Extreme Directional Flood (Equal Input for both)
    flood_wave = np.tile(np.linspace(0.015, 0.07, n), (n, 1)) 
    noise = np.random.normal(0.012, 0.006, (n, n))
    total_input = flood_wave + noise
    
    # --- Scenario A: Blind (Random Shuffling) ---
    blind += total_input
    blind[ls_grid % 4 == (t % 4)] *= 0.90
    if np.mean(blind) > 0.35 and t % 15 == 0:
        mode = t % 3
        if mode == 0: blind = blind.T
        elif mode == 1: blind = np.flipud(blind)
        else: blind = np.fliplr(blind)
    blind *= 0.985 # Standard decay
    blind = np.clip(blind, 0, 1)
    
    # --- Scenario B: Directional (Vector-Aware) ---
    directional += total_input
    directional[ls_grid % 4 == (t % 4)] *= 0.90
    if np.mean(directional) > 0.3:
        dy, dx = np.gradient(directional)
        avg_dx = np.mean(dx)
        # Strategic Reversal based on detected flow
        if avg_dx > 0.002:
            directional = np.fliplr(directional)
        elif abs(np.mean(dy)) > abs(avg_dx):
            directional = np.flipud(directional)
        else:
            directional = directional.T
            
    directional *= 0.985 # EQUAL DECAY (Fairness Applied)
    directional = np.clip(directional, 0, 1)

    return [blind, directional]

def visualize_fair_bench():
    n, checkpoints = 64, [10, 100, 500, 1000, 5000, 10000]
    sim_data = {}
    states = [np.random.uniform(0.05, 0.1, (n, n)) for _ in range(2)]
    ls_grid = generate_mols_base(n)

    for t in range(1, max(checkpoints) + 1):
        states = update_load_fair_stress(states, ls_grid, t, n)
        if t in checkpoints: sim_data[t] = [s.copy() for s in states]

    fig, axes = plt.subplots(len(checkpoints), 2, figsize=(10, 20))
    cmap = LinearSegmentedColormap.from_list("net_dynamic", ["#000033", "#1E90FF", "#FFFF00", "#FF4500", "#8B0000"])
    
    titles = ["Blind (Equal Decay 0.985)", "Directional (Equal Decay 0.985)"]
    
    for r, t in enumerate(checkpoints):
        for c in range(2):
            ax = axes[r, c]
            im = ax.imshow(sim_data[t][c], cmap=cmap, vmin=0, vmax=1, interpolation='gaussian')
            if r == 0: ax.set_title(titles[c], fontweight='bold', pad=15)
            if c == 0: ax.set_ylabel(f"Step {t}", fontweight='bold', labelpad=20)
            ax.set_xticks([]); ax.set_yticks([])

    cbar_ax = fig.add_axes([0.2, 0.05, 0.6, 0.01])
    fig.colorbar(im, cax=cbar_ax, orientation='horizontal').set_label('Congestion Level (0.0 to 1.0)')
    
    plt.suptitle("STRESS TEST: Identical Environments (T=10,000)", fontsize=16, y=0.98, fontweight='bold')
    plt.subplots_adjust(hspace=0.3, wspace=0.1, bottom=0.08)
    plt.show()

if __name__ == "__main__":
    visualize_fair_bench()
