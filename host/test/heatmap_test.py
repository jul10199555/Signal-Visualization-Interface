#!/usr/bin/env python3
import random
import time
from datetime import datetime, timezone, timedelta

import matplotlib.pyplot as plt
import seaborn

from host.heatmap import Heatmap, s5x41_switcher
from host.payload import Payload

def main():
    extra_keys = (
        ["5001 <LOAD> (VDC)", "5021 <DISP> (VDC)"]
        + [f"{6001 + i} (OHM)" for i in range(40)]
    )

    p = Payload(
        window_size=1_000_000,
        num_rows_detach=1_000,
        out_file_name="output/10k_test.csv",
        channels=21,
        keys=extra_keys
    )
    fake_freq = 10  # Hz
    faketime = datetime.now(timezone.utc)

    for i in range(10_000):
        load_v = round(0.00030 + 1e-7 * i, 9)
        disp_v = round(0.00019 + 1e-7 * i, 9)
        resist = [round(11_000 + random.uniform(-500, 500), 4) for _ in range(40)]
        payload = ",".join([f"{load_v}", f"{disp_v}", *map(str, resist)])
        p.push(payload, time=faketime)
        faketime += timedelta(milliseconds=(1/fake_freq)*1000)

    # Compute the diagonal‐averaged heatmap matrix (5×43):
    hm  = Heatmap(p)
    mat = hm.calc_pts_diagonal(s5x41_switcher)

    # Quick sanity print
    print("matrix shape:", mat.shape)  # → (5, 43)

    # --- Plot with dual axes ticks ---
    fig, ax = plt.subplots(figsize=(12, 3))

    seaborn.heatmap(
        mat,
        cmap="jet",               # rainbow colormap
        cbar_kws={"label": "RRA"},
        ax=ax,
        xticklabels=False,
        yticklabels=False
    )

    # 1) Bottom x‐axis: primed columns at even indices
    evens = list(range(2, mat.shape[1], 2))           # [2,4,...,42]
    labels_prime = [f"{i}'" for i in range(1, len(evens)+1)]
    ax.set_xticks(evens)
    ax.set_xticklabels(labels_prime, rotation=0, fontsize=8)
    ax.set_xlabel("Columns")

    # 2) Left y‐axis: real rows 1…5
    rows = list(range(mat.shape[0]))                   # [0,1,2,3,4]
    labels_rows = [str(i) for i in range(1, mat.shape[0]+1)]
    ax.set_yticks(rows)
    ax.set_yticklabels(labels_rows, rotation=0, fontsize=8)
    ax.set_ylabel("Rows")

    # 3) Top x‐axis: real columns 1…21
    ax_top = ax.twiny()
    ax_top.set_xlim(ax.get_xlim())
    ax_top.set_xticks(evens)
    ax_top.set_xticklabels(range(1, len(evens)+1), rotation=0, fontsize=8)
    ax_top.xaxis.set_ticks_position('top')
    ax_top.xaxis.set_label_position('top')
    ax_top.set_xlabel("Columns")

    # 4) Right y‐axis: primed rows 1′…5′
    ax_right = ax.twinx()
    ax_right.set_ylim(ax.get_ylim())
    ax_right.set_yticks(rows)
    ax_right.set_yticklabels([f"{i}'" for i in range(1, mat.shape[0]+1)],
                             rotation=0, fontsize=8)
    ax_right.yaxis.set_ticks_position('right')
    ax_right.yaxis.set_label_position('right')

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
