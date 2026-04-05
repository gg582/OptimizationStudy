import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

def generate_mols_base(n=64):
    """Generates a stable MOLS grid for geometric routing rules."""
    return np.array([np.roll(np.arange(n), i) for i in range(n)])

def update_load(states, ls_grid, t, n=64):
    """
    Updates load for four scenarios with adaptive triggers.
    1. Conv: Static diffusion (Baseline)
    2. Inv: MOLS Symbol-based damping
    3. Rot: Congestion-triggered 90-degree rotation
    4. Sym: Gradient-based Symmetry (Flip & Transpose)
    """
    conv, inv, rot, sym = states
    noise = np.random.normal(0.018, 0.01, (n, n)) # Increased noise for stress test
    
    # --- 1. Conventional (Static Baseline) ---
    conv += noise
    conv[20:25, 20:25] += 0.005 # Static bottleneck A
    conv[40:45, 40:45] += 0.005 # Static bottleneck B
    conv = conv * 0.985 + (np.roll(conv, 1, 0) + np.roll(conv, 1, 1)) * 0.007
    
    # --- 2. MOLS Non-linear Inverse ---
    inv += noise
    target_group = t % 4
    mask = (ls_grid % 4 == target_group)
    inv[mask] *= 0.90 # Accelerated recovery
    
    # --- 3. MOLS Adaptive Rotation (Triggered by load) ---
    rot += noise
    # Trigger rotation only when mean load exceeds threshold
    if np.mean(rot) > 0.35 and t % 10 == 0:
        rot = np.rot90(rot, k=1)
    rot *= 0.988 

    # --- 4. MOLS Gradient-Based Symmetry (Optimized Vector Cancellation) ---
    sym += noise
    if np.mean(sym) > 0.35:
        dy, dx = np.gradient(sym)
        avg_dy, avg_dx = np.mean(dy), np.mean(dx)
        
        # Adaptive Axis Reversal based on flow direction
        if abs(avg_dy) > abs(avg_dx) * 1.2:
            sym = np.flipud(sym)  # Vertical cancellation
        elif abs(avg_dx) > abs(avg_dy) * 1.2:
            sym = np.fliplr(sym)  # Horizontal cancellation
        else:
            sym = sym.T           # Diagonal cross-flow cancellation
    sym *= 0.988

    return [np.clip(s, 0, 1) for s in [conv, inv, rot, sym]]

def run_bench_simulation():
    n = 64
    ls_grid = generate_mols_base(n)
    checkpoints = [10, 100, 1000]
    results = {}
    
    # Uniform initial state
    states = [np.random.uniform(0.05, 0.15, (n, n)) for _ in range(4)]
    
    for t in range(1, max(checkpoints) + 1):
        states = update_load(states, ls_grid, t, n)
        if t in checkpoints:
            results[t] = [s.copy() for s in states]
            
    return results

def visualize_benchmark():
    n = 64
    checkpoints = [10, 100, 1000]
    sim_data = run_bench_simulation()
    
    fig, axes = plt.subplots(3, 4, figsize=(20, 12))
    cmap = LinearSegmentedColormap.from_list("net_dynamic", ["#000033", "#1E90FF", "#FFFF00", "#FF4500", "#8B0000"])
    
    col_titles = [
        "Conventional\n(Baseline)", 
        "MOLS Inverse\n(Group Damping)", 
        "Adaptive Rotation\n(Triggered 90°)", 
        "MOLS Symmetry\n(Vector Flip/T)"
    ]
    
    for r, t in enumerate(checkpoints):
        row_data = sim_data[t]
        for c in range(4):
            ax = axes[r, c]
            im = ax.imshow(row_data[c], cmap=cmap, vmin=0, vmax=1, interpolation='bilinear')
            
            if r == 0:
                ax.set_title(col_titles[c], fontsize=12, pad=20, fontweight='bold')
            if c == 0:
                ax.set_ylabel(f"T = {t}", fontsize=13, fontweight='bold')
            
            ax.set_xticks([]); ax.set_yticks([])
            for spine in ax.spines.values(): spine.set_visible(False)

    cbar_ax = fig.add_axes([0.15, 0.06, 0.7, 0.015])
    fig.colorbar(im, cax=cbar_ax, orientation='horizontal').set_label('Congestion Level', fontsize=11)
    
    plt.suptitle("Comparative Analysis: Adaptive Congestion Control Strategies", fontsize=18, y=0.98)
    plt.subplots_adjust(hspace=0.3, wspace=0.1, bottom=0.15)
    plt.show()

if __name__ == "__main__":
    visualize_benchmark()
