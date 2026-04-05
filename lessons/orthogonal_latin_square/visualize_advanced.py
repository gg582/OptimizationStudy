import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

def generate_mols_base(n=64):
    """Generates a stable MOLS grid for geometric routing rules."""
    return np.array([np.roll(np.arange(n), i) for i in range(n)])

def update_load_exact_baseline(states, ls_grid, t, n=64):
    """
    Restored to EXACT first benchmark settings:
    Noise: 0.015 / 0.008
    Decay: 0.988 / 0.985
    """
    inv, rot, sym = states
    noise = np.random.normal(0.015, 0.008, (n, n))
    
    # --- 1. Adaptive MOLS Inverse (Enhanced) ---
    inv += noise
    group_loads = [np.mean(inv[ls_grid == g]) for g in range(n)]
    hottest_group = np.argmax(group_loads)
    inv[ls_grid == hottest_group] *= 0.92 
    
    if np.mean(inv) > 0.4 and t % 20 == 0:
        inv = inv.T
    inv *= 0.985 
    inv = np.clip(inv, 0, 1)
    
    # --- 2. Adaptive Rotation (Triggered) ---
    rot += noise
    if np.mean(rot) > 0.35 and t % 15 == 0:
        rot = np.rot90(rot, k=1)
    rot *= 0.988 
    rot = np.clip(rot, 0, 1)

    # --- 3. MOLS Symmetry (Vector Cancellation) ---
    sym += noise
    if np.mean(sym) > 0.3:
        dy, dx = np.gradient(sym)
        avg_dy, avg_dx = np.mean(dy), np.mean(dx)
        
        if abs(avg_dx) > abs(avg_dy) * 1.2:
            sym = np.fliplr(sym) 
        elif abs(avg_dy) > abs(avg_dx) * 1.2:
            sym = np.flipud(sym) 
        else:
            sym = sym.T           
            
    sym *= 0.988 
    sym = np.clip(sym, 0, 1)

    return [inv, rot, sym]

def run_extended_sim():
    n = 64
    ls_grid = generate_mols_base(n)
    # Requested checkpoints
    checkpoints = [10, 50, 100, 500, 1000, 1500]
    results = {}
    
    states = [np.random.uniform(0.05, 0.15, (n, n)) for _ in range(3)]
    
    for t in range(1, max(checkpoints) + 1):
        states = update_load_exact_baseline(states, ls_grid, t, n)
        if t in checkpoints:
            results[t] = [s.copy() for s in states]
            
    return results, checkpoints

def visualize():
    sim_data, checkpoints = run_extended_sim()
    num_rows = len(checkpoints)
    
    # Adjust figure size for 6x3 grid
    fig, axes = plt.subplots(num_rows, 3, figsize=(14, 4 * num_rows))
    cmap = LinearSegmentedColormap.from_list("net_dynamic", ["#000033", "#1E90FF", "#FFFF00", "#FF4500", "#8B0000"])
    
    col_titles = [
        "Adaptive Inverse\n(Symbol + Symmetry)", 
        "Adaptive Rotation\n(Triggered 90°)", 
        "MOLS Symmetry\n(Optimal Flip/T)"
    ]
    
    for r, t in enumerate(checkpoints):
        row_data = sim_data[t]
        for c in range(3):
            ax = axes[r, c]
            im = ax.imshow(row_data[c], cmap=cmap, vmin=0, vmax=1, interpolation='bilinear')
            
            # Titles only for the first row
            if r == 0:
                ax.set_title(col_titles[c], fontsize=11, pad=15, fontweight='bold')
            
            # Row labels (Time steps)
            if c == 0:
                ax.set_ylabel(f"T = {t}", fontsize=12, fontweight='bold', labelpad=15)
            
            ax.set_xticks([]); ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_visible(False)

    # Colorbar at the bottom
    cbar_ax = fig.add_axes([0.3, 0.05, 0.4, 0.01])
    fig.colorbar(im, cax=cbar_ax, orientation='horizontal').set_label('Congestion Level (Baseline Load)')
    
    plt.subplots_adjust(hspace=0.25, wspace=0.1, bottom=0.08, top=0.94)
    plt.show()

if __name__ == "__main__":
    visualize()
