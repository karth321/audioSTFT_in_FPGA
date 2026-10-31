import numpy as np

# Compute 1024 Q1.15 fixed-point Hann window coefficients (0 to 32767)
n = np.arange(1024)
hann = 0.5 - 0.5 * np.cos(2 * np.pi * n / 1023)
hann_q15 = np.round(hann * 32767).astype(int)

# Write to Quartus-compatible hexadecimal file
with open("../verilog/hann_1024_q15.hex", "w") as f:
    for val in hann_q15:
        f.write(f"{val:04X}\n")

print("hann_1024_q15.hex created successfully.")