# Comprehensive Project Documentation: STFT Audio Processing on DE10-Standard FPGA

## 1. System Overview & Architecture

This project implements a hardware-accelerated **Short-Time Fourier Transform (STFT)** spectrum analyzer on the **Terasic DE10-Standard FPGA board** (Intel Cyclone V SoC). 

The system uses a single-cable setup via the onboard **USB-Blaster II (JTAG Port)** in full-duplex chunked burst mode. A Python host application on an **Ubuntu 22.04 LTS Laptop** streams raw audio to the FPGA, where the hardware logic executes windowing, a 1024-point Fast Fourier Transform (FFT), and linear magnitude approximation. The computed frequency bins are streamed back over JTAG to the Python application for live GUI visualization.

### System Data Flow
```text
+---------------------------------------------------------------------------------------------------+
|                                      HOST LAPTOP (Ubuntu 22.04)                                   |
|  +-----------------------+     +------------------------+     +--------------------------------+  |
|  | Audio Wave / Mic      | --> | PyQtGraph GUI App      | <-> | Intel System Console Server    |  |
|  | (44.1 kHz, 16-bit PCM)|     | (interface.py)         |     | (server.tcl TCP Bridge)        |  |
|  +-----------------------+     +------------------------+     +--------------------------------+  |
+-------------------------------------------------------------------------------|-------------------+
                                                                                | USB Type-B Cable 
                                                                                | (Full-Duplex JTAG)
+-------------------------------------------------------------------------------v-------------------+
|                                      DE10-STANDARD FPGA FABRIC                                    |
|  +-----------------------+     +------------------------+     +--------------------------------+  |
|  | JTAG UART Core        | --> | Audio RX FIFO          | --> | Framing & Hann Windowing Unit  |  |
|  | (Avalon-ST Bridge)    |     | (DCFIFO, 8192 words)   |     | (Q1.15 Fixed-Point LUT ROM)    |  |
|  +-----------------------+     +------------------------+     +--------------------------------+  |
|             ^                                                                  |                  |
|             |                                                                  v                  |
|  +-----------------------+     +------------------------+     +--------------------------------+  |
|  | STFT TX FIFO          | <-- | Alpha-Max Beta-Min     | <-- | 1024-Point Intel FFT Core      |  |
|  | (DCFIFO, 4096 words)  |     | Magnitude Unit         |     | (Streaming Radix-2 Pipeline)   |  |
|  +-----------------------+     +------------------------+     +--------------------------------+  |
+---------------------------------------------------------------------------------------------------+
```

---

## 2. Finalized Specifications

| Category | Parameter | Specification Value |
| :--- | :--- | :--- |
| **Input Audio** | Sample Rate ($F_s$) | $44.1 \text{ kHz}$, 16-bit Signed PCM, Mono |
| **STFT Framing** | Frame Size ($N$) | $1024 \text{ samples}$ |
| **STFT Hop Size**| Overlap ($H$) | $50\% \text{ overlap}$ ($H = 512 \text{ samples}$) |
| **Windowing** | Type & Encoding | Hann Window, Q1.15 Fixed-Point LUT ($1024 \times 16\text{-bit}$) |
| **FFT Logic Core**| Architecture | Intel FPGA FFT Megafunction (Streaming, BFP) |
| **Magnitude Unit**| Algorithm | Alpha-Max Beta-Min Linear Magnitude Approximation |
| **Hardware Clock**| Clock Source | $50 \text{ MHz}$ Onboard System Clock (`CLOCK_50`) |
| **Interface** | Physical Port | USB-Blaster II JTAG Port |
| **Burst Strategy**| Timing Period | $100 \text{ ms Burst}$ ($4410$ samples) / $200 \text{ ms}$ Idle Interval |
| **Output Packet** | Bin Array Format | $513 \text{ Bins}$ (`uint16_t` Magnitudes, $1026 \text{ Bytes}$ Payload) |

---

## 3. Mathematical Formulations

### 3.1 Frequency Bin Mapping
The physical center frequency corresponding to bin index $k$ ($0 \le k \le 512$) is calculated as:
$$ \text{Frequency of Bin } k = k \times \frac{F_s}{N} = k \times \frac{44100}{N} \text{ Hz} $$
For $N = 1024$ and $F_s = 44.1\text{ kHz}$:
$$ \Delta f = \frac{44100}{1024} \approx 43.0664 \text{ Hz/bin} $$

### 3.2 Discrete Hann Window Function
$$ w[n] = 0.5 - 0.5 \cos\left(\frac{2\pi n}{N - 1}\right), \quad n = 0, 1, \dots, 1023 $$
Applied in hardware via Q1.15 fixed-point math: `Product = (Sample * LUT_val) >>> 15`.

### 3.3 Discrete Fourier Transform (DFT)
$$ X[k] = \sum_{n=0}^{N-1} (x[n] \cdot w[n]) \cdot e^{-j \frac{2\pi}{N} k n} $$

### 3.4 Alpha-Max Beta-Min Magnitude Approximation
Given complex FFT bin $X[k] = I_k + j Q_k$, linear magnitude is approximated using integer bit-shifts:
$$ |X[k]| \approx \max(|I_k|, |Q_k|) + \left(\min(|I_k|, |Q_k|) \gg 2\right) + \left(\min(|I_k|, |Q_k|) \gg 3\right) $$
*(This avoids DSP-heavy square root/CORDIC hardware with < 4% error).*

---

## 4. Communication Protocol & Packet Structures

### 4.1 Host $\rightarrow$ FPGA Audio Input Packet (JTAG TX)
Sent every $300\text{ ms}$ containing a $100\text{ ms}$ burst ($4410$ audio samples = $8820\text{ bytes}$):

| Byte Offset | Field Name | Data Type | Value / Description |
| :--- | :--- | :--- | :--- |
| `0..1` | **Sync Header** | `uint16_t` | `0x1234` |
| `2..3` | **Burst Index** | `uint16_t` | Incremental sequence number |
| `4..5` | **Sample Count** | `uint16_t` | `4410` |
| `6..8825` | **PCM Audio Samples** | `int16_t[4410]` | 16-bit signed audio stream |
| `8826..8827`| **Checksum** | `uint16_t` | 16-bit modular sum check |

### 4.2 FPGA $\rightarrow$ Host STFT Output Packet (JTAG RX)
For each processed 1024-sample FFT frame within the burst, the FPGA returns a 1034-byte packet:

| Byte Offset | Field Name | Data Type | Value / Description |
| :--- | :--- | :--- | :--- |
| `0..1` | **Sync Header** | `uint16_t` | `0xABCD` |
| `2..3` | **Frame Index** | `uint16_t` | Frame sequence counter |
| `4..5` | **Bin Count ($K$)** | `uint16_t` | `513` |
| `6..1031` | **Magnitude Bins** | `uint16_t[513]` | Linear magnitudes ($0\text{ Hz}$ to $22.05\text{ kHz}$) |
| `1032..1033`| **Checksum** | `uint16_t` | 16-bit modular sum check |

---

## 5. Software Stack Implementation

### 5.1 Intel System Console TCP Bridge (`server.tcl`)
A Tcl script executed by Quartus `system-console` to expose the JTAG UART as a local TCP socket server on `127.0.0.1:12345`. It uses `master_write_16` and `master_read_16` to bridge binary data to/from the FPGA fabric.

### 5.2 Python Host Visualizer (`interface.py`)
*   **Audio Handling:** Plays audio locally using native ALSA (`aplay`).
*   **Networking:** Background `QThread` manages socket TX/RX to prevent UI blocking. Slices audio into 100ms chunks with `0x1234` headers, and parses `0xABCD` packets.
*   **Visualization:** Uses `pyqtgraph` to render high-performance, real-time frequency-domain line plots.
*   **Signal Handling:** Enforces clean shutdown on `Ctrl+C` (SIGINT) by destroying the audio player and socket gracefully.

### 5.3 Hardware Emulator (`fpga_sim.py`)
A standalone Python TCP server that mocks the Intel System Console and FPGA hardware. It binds to port `12345`, receives `0x1234` audio packets, mathematically computes the Hann windowing, real FFT (`np.fft.rfft`), and fixed-point Alpha-Max Beta-Min approximations, and streams `0xABCD` packets back to the visualizer for fully un-tethered software testing.

---

## 6. Simulation & Testing Guide

### 6.1 Full-Stack Python Simulation
To verify the host UI and DSP math without an FPGA:
1. Activate virtual environment: `source .venv/bin/activate`
2. Run emulator: `python3 fpga_sim.py` *(This script automatically launches `interface.py` as a subprocess).*

### 6.2 ModelSim (Questa) RTL Simulation
ModelSim 20.1 Starter Edition on 64-bit Ubuntu 22.04 requires specific 32-bit library dependencies and path adjustments.

#### ModelSim Ubuntu 22.04 Fixes Applied:
1. **Directory symlink:** `ln -s linuxaloem linux` inside the ModelSim `bin` directory.
2. **32-bit Architecture & Libraries:** 
   ```bash
   sudo dpkg --add-architecture i386
   sudo apt install libc6:i386 libstdc++6:i386 libx11-6:i386 libxext6:i386 libxft2:i386 libncurses6:i386 libtinfo6:i386
   ```
3. **Legacy Symlinks:** Linked `libncurses.so.6` and `libtinfo.so.6` to their `.so.5` counterparts.

#### Standard ModelSim Execution Script (`msim_run.tcl`):
To correctly resolve VHDL submodules and Intel IP dependencies:
```tcl
# 1. Set IP simulation directory to avoid ENOENT errors
set QSYS_SIMDIR "fft_1024_core/simulation"

# 2. Source Intel IP setup script and compile IP submodules into 'fft_ii_0'
source fft_1024_core/simulation/mentor/msim_setup.tcl
dev_com
com

# 3. Compile custom project Verilog RTL modules into 'work'
vlog -work work hann_rom_lut.v jtag_input_receiver.v signal_processing.v output_formatter.v jtag_tx_streamer.v tb_stft.v

# 4. Elaborate top-level testbench linking 'work' and 'fft_ii_0' IP libraries
vsim -t 1ps -L fft_ii_0 -lib work tb_stft

# 5. Format waves and run
add wave -r /*
run -all
```
*(Note: To view audio/magnitudes as waves, change Radix to Decimal/Unsigned and Format to Analog).*

### 6.3 Icarus Verilog (`iverilog`) & GTKWave Setup
For fast, lightweight RTL simulation of custom modules without Quartus IP dependencies:
1. Add `$dumpfile("waveform.vcd"); $dumpvars(0, tb_stft);` to `tb_stft.v`.
2. Compile: `iverilog -o sim_out tb_stft.v [module_names].v`
3. Execute: `vvp sim_out`
4. Visualize: `gtkwave waveform.vcd &`

---

## 7. Physical Hardware Execution Guide

1. **Flash Bitstream:** Use Quartus Programmer to flash `stft_top.sof` to the DE10-Standard (MSEL switches left at default `10010` AS mode).
2. **Launch System Console Bridge:**
   ```bash
   /home/<user>/intelFPGA_lite/25.1/quartus/sopc_builder/bin/system-console --cli --script="$PWD/server.tcl"
   ```
   *(Keep this terminal running in the background).*
3. **Run Host Visualizer:**
   Open a second terminal, activate `.venv`, and run:
   ```bash
   python3 interface.py
   ```
   *(Press `Ctrl+C` to cleanly stop audio and TCP bridging at any time).*