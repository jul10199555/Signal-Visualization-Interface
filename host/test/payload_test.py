import random
import time
from datetime import datetime, timezone, timedelta

from host.multi_display import WaveformApp
from host.payload import Payload

if __name__ == "__main__":

    extra_keys = (
            ["5001 <LOAD> (VDC)", "5021 <DISP> (VDC)"]
            + [f"{6001 + i} (OHM)" for i in range(21)]  # 6001 … 6040
    )

    p = Payload(
        window_size=1000000,
        num_rows_detach=1000,
        out_file_name="output/10k_test.csv",
        channels=21,
        keys=extra_keys
    )
    fake_freq = 10  # hz

    faketime = datetime.now(timezone.utc)

    for i in range(10000):
        load_v = round(0.00030 + 1e-7 * i, 9)
        disp_v = round(0.00019 + 1e-7 * i, 9)

        resist = [round(11_000 + random.uniform(-500, 500), 4) for _ in range(21)]

        payload = ",".join([f"{load_v}", f"{disp_v}", *map(str, resist)])

        start_time = time.time()

        p.push(payload, time=faketime)
        end_time = time.time()
        print(f"Push {i}: {end_time - start_time:.7f} s")
        faketime += timedelta(milliseconds=(1/fake_freq)*1000)

    # p.detach_rows(3, "output/detached_test.csv")
    p.to_csv("output/detached_test_p.csv")
    print()

    print(p.get_channels())

    WaveformApp(p, 10).mainloop()

    # import seaborn as sns
    # import matplotlib.pyplot as plt
    #
    # # Wide DF: Time index, columns = channels
    # heat_df = p.to_dataframe().set_index("Time")[extra_keys[2:]]
    #
    # plt.figure(figsize=(12, 6))
    # sns.heatmap(
    #     heat_df.T,  # transpose so channels on Y
    #     cmap="viridis", cbar_kws={"label": "Ohms"}
    # )
    # plt.xlabel("Time")
    # plt.ylabel("Channel")
    # plt.title("Resistance heat-map")
    # plt.tight_layout()
    # plt.show()
