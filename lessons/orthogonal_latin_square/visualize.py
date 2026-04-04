import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

def generate_mols_base(n=64):
    """Generates a stable MOLS grid for geometric routing rules."""
    return np.array([np.roll(np.arange(n), i) for i in range(n)])

def update_load(states, ls_grid, t, n=64):
    """Updates load for one time step for all three scenarios."""
    conv, inv, rot = states
    
    # New incoming traffic (Noise + System Load)
    noise = np.random.normal(0.015, 0.008, (n, n))
    
    # 1. Conventional: Accumulative drift with local diffusion
    # Simulates queues that don't clear and bleed into neighbors
    conv += noise
    conv[20:24, 20:24] += 0.004 # Static bottleneck 1
    conv[40:44, 40:44] += 0.004 # Static bottleneck 2
    # Diffusion effect: Congestion spreads to adjacent nodes
    conv = conv * 0.985 + (np.roll(conv, 1, 0) + np.roll(conv, 1, 1)) * 0.007
    
    # 2. MOLS Non-linear Inverse
    inv += noise
    # Apply non-linear damping based on Latin Square symbols
    # Dampen 1/4 of the node groups every step to prevent saturation
    target_group = t % 4
    mask = (ls_grid % 4 == target_group)
    inv[mask] *= 0.92 # Non-linear recovery
    
    # 3. MOLS Rotation
    rot += noise
    # Rotate the assignment logic every 100 steps to clear paths
    if t > 0 and t % 100 == 0:
        rot = np.rot90(rot, k=1)
    # Natural decay representing processed tasks
    rot *= 0.988 

    return [np.clip(conv, 0, 1), np.clip(inv, 0, 1), np.clip(rot, 0, 1)]

def run_full_simulation():
    n = 64
    ls_grid = generate_mols_base(n)
    checkpoints = [10, 100, 1000]
    results = {}
    
    # Initial state: Low load
    states = [np.random.uniform(0.05, 0.15, (n, n)) for _ in range(3)]
    
    for t in range(1, max(checkpoints) + 1):
        states = update_load(states, ls_grid, t, n)
        if t in checkpoints:
            results[t] = [s.copy() for s in states]
            
    return results

def visualize_comparison():
    n = 64
    checkpoints = [10, 100, 1000]
    sim_data = run_full_simulation()
    
    fig, axes = plt.subplots(3, 3, figsize=(15, 12))
    cmap = LinearSegmentedColormap.from_list("net_dynamic", ["#000033", "#1E90FF", "#FFFF00", "#FF4500", "#8B0000"])
    
    col_titles = ["Conventional (Hash/Random)", "MOLS Non-linear Inverse", "MOLS 90° Rotation"]
    
    for r, t in enumerate(checkpoints):
        row_data = sim_data[t]
        for c in range(3):
            ax = axes[r, c]
            im = ax.imshow(row_data[c], cmap=cmap, vmin=0, vmax=1, interpolation='bilinear')
            
            # Row/Col Labels
            if r == 0:
                ax.set_title(col_titles[c], fontsize=11, pad=15, fontweight='bold')
            if c == 0:
                ax.set_ylabel(f"T = {t}", fontsize=12, fontweight='bold', labelpad=20)
            
            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_visible(False)

    # Global Colorbar
    cbar_ax = fig.add_axes([0.15, 0.05, 0.7, 0.02])
    cbar = fig.colorbar(im, cax=cbar_ax, orientation='horizontal')
    cbar.set_label('Network Congestion Density (Deep Blue: Idle / Dark Red: Saturated)', fontsize=10)
    
    plt.suptitle("64x64 Distributed Node Congestion: Time-Series Evolution", fontsize=16, y=0.97)
    plt.subplots_adjust(hspace=0.2, wspace=0.1, bottom=0.12)
    plt.show()

if __name__ == "__main__":
    visualize_comparison()
