# STFT Audio Processing on DE10-Standard FPGA

## Technical Design & System Specification Document

---

## 1. System Architecture & Flow Overview

This document defines the complete technical specifications for implementing an **audio Short-Time Fourier Transform (STFT) spectrum analyzer** on the **Terasic DE10-Standard FPGA board** (Intel Cyclone V SoC `5CSXFC6D6F31C6N`) connected to an **Ubuntu 22.04 LTS Laptop**.

The system utilizes a single-cable **USB-Blaster II (JTAG Port)** interface operating in full-duplex burst mode. The laptop streams raw 16-bit PCM audio chunks to the FPGA, where the hardware logic executes windowing, 1024-point Fast Fourier Transform (FFT), and linear magnitude calculation. The computed frequency spectrum bins are then transmitted back over JTAG to an Ubuntu Python application for live visualization.

```
+---------------------------------------------------------------------------------------------------+
|                                      HOST LAPTOP (Ubuntu 22.04)                                   |
|  +-----------------------+     +------------------------+     +--------------------------------+  |
|  | Audio Wave / Mic Stream| --> | PyQtGraph GUI App      | --> | Intel System Console Server    |  |
|  | (44.1 kHz, 16-bit PCM)|     | (Live Plotter Engine)  |     | (Local TCP Socket Bridge)      |  |
|  +-----------------------+     +------------------------+     +--------------------------------+  |
+-------------------------------------------------------------------------------|-------------------+
                                                                                | USB Type-B Cable 
                                                                                | (Full-Duplex JTAG)
+-------------------------------------------------------------------------------v-------------------+
|                                      DE10-STANDARD FPGA FABRIC                                    |
|  +-----------------------+     +------------------------+     +--------------------------------+  |
|  | JTAG UART Core        | --> | Audio RX FIFO          | --> | Framing & Hann Windowing Unit  |  |
|  | (Avalon-ST Bridge)    |     | (Dual-Clock DCFIFO)    |     | (Q1.15 Fixed-Point LUT ROM)    |  |
|  +-----------------------+     +------------------------+     +--------------------------------+  |
|             ^                                                                  |                  |
|             |                                                                  v                  |
|  +-----------------------+     +------------------------+     +--------------------------------+  |
|  | STFT TX FIFO          | <-- | Alpha-Max Beta-Min     | <-- | 1024-Point Intel FFT Core      |  |
|  | (Dual-Clock DCFIFO)   |     | Magnitude Unit         |     | (Streaming Radix-2/4 Pipeline) |  |
|  +-----------------------+     +------------------------+     +--------------------------------+  |
+---------------------------------------------------------------------------------------------------+
```

---

## 2. System Specifications Summary

### 2.1 Hardware & Software Parameters
* **Target Board:** Terasic DE10-Standard Development Kit
* **FPGA Device:** Intel Cyclone V SE SoC (`5CSXFC6D6F31C6N`)
* **Board Configuration Mode:** Default Active Serial mode (`MSEL[4:0] = 10010`). Hardware JTAG programs FPGA SRAM directly without requiring an ARM HPS Linux boot.
* **Onboard System Clock:** $50\text{ MHz}$ Oscillator (`CLOCK_50`, Pin `AF14`).
* **Host Laptop Environment:** Ubuntu 22.04 LTS (x86_64).
* **Synthesis & Hardware Toolchain:** Quartus Prime Lite 25.1, Intel System Console.
* **Simulation Toolchain:** Icarus Verilog (`iverilog`), GTKWave.
* **Host Software Stack:** Python 3.10+, `pyqtgraph`, `numpy`.

### 2.2 Audio & STFT Parameters
* **Input Signal Format:** 16-bit Signed PCM (`int16_t` two's complement), Mono.
* **Sampling Rate ($F_s$):** $44.1\text{ kHz}$ ($44,100\text{ samples/second}$).
* **FFT Length ($N$):** $1024\text{ samples}$.
* **Frame Overlap:** $50\%$ overlap ($H = 512\text{ samples}$).
* **Window Function:** Hann (Hanning) Window.
* **Frequency Resolution:** $513\text{ unique bins}$ ($\frac{N}{2} + 1$).

---

## 3. Mathematical Foundations & Formulas

### 3.1 Frequency Bin Mapping
For a real-valued signal sampled at $F_s$, the $N$-point FFT produces symmetrical positive and negative frequencies. The unique positive spectrum spans from Bin $0$ ($0\text{ Hz}$) to Bin $512$ ($22,050\text{ Hz}$, Nyquist frequency).

* **Bin Resolution ($\Delta f$):**
  $$\Delta f = \frac{F_s}{N} = \frac{44100\text{ Hz}}{1024} \approx 43.0664\text{ Hz/bin}$$

* **Frequency Conversion Formula:**
  $$\text{Frequency of Bin } k = k \times \frac{F_s}{N} = k \times \frac{44100}{N} \text{ Hz}$$

* **Key Bin Mapping Examples:**
  * **Bin $0$:** $0 \times 43.0664\text{ Hz} = 0.0\text{ Hz}$ (DC Component)
  * **Bin $1$:** $1 \times 43.0664\text{ Hz} = 43.07\text{ Hz}$
  * **Bin $23$:** $23 \times 43.0664\text{ Hz} \approx 990.53\text{ Hz}$ ($\approx 1\text{ kHz}$ tone)
  * **Bin $256$:** $256 \times 43.0664\text{ Hz} = 11,025.0\text{ Hz}$
  * **Bin $512$:** $512 \times 43.0664\text{ Hz} = 22,050.0\text{ Hz}$ (Nyquist Limit)

### 3.2 Discrete Hann Window Function
Each 1024-sample audio frame $x[n]$ is multiplied element-wise by the discrete Hann window $w[n]$ to taper edge discontinuities:

$$w[n] = 0.5 - 0.5 \cos\left(\frac{2\pi n}{N - 1}\right), \quad n = 0, 1, \dots, N-1$$

For $N = 1024$:
$$w[n] = 0.5 - 0.5 \cos\left(\frac{2\pi n}{1023}\right)$$

### 3.3 Discrete Fourier Transform (DFT)
The windowed sequence $x_w[n] = x[n] \cdot w[n]$ is transformed into complex frequency coefficients $X[k]$:

$$X[k] = \sum_{n=0}^{N-1} (x[n] \cdot w[n]) \cdot e^{-j \frac{2\pi}{N} k n}, \quad k = 0, 1, \dots, N-1$$

### 3.4 Alpha-Max Beta-Min Magnitude Approximation
To calculate linear magnitude $|X[k]| = \sqrt{I_k^2 + Q_k^2}$ without square root or CORDIC IP cores, the FPGA logic uses the Alpha-Max Beta-Min algorithm:

$$|X[k]| \approx \max(|I_k|, |Q_k|) + 0.375 \times \min(|I_k|, |Q_k|)$$

Where $I_k = \text{Re}(X[k])$ and $Q_k = \text{Im}(X[k])$. The coefficient $0.375 = \frac{1}{4} + \frac{1}{8}$ is implemented using zero-cost arithmetic bit shifts:

$$\text{Term}_{\text{min}} = (\text{min\_val} \gg 2) + (\text{min\_val} \gg 3)$$

$$\text{Magnitude}[k] = \text{max\_val} + \text{Term}_{\text{min}}$$

---

## 4. Communication Protocol & Packet Structure

### 4.1 JTAG Burst Strategy
Full-duplex transmission takes place in periodic 300 ms cycles to maintain JTAG bus stability and prevent host buffer overruns:

| Parameter | Value | Description |
| :--- | :--- | :--- |
| **Audio Burst Size ($T_{\text{burst}}$)** | **$100\text{ ms}$** | $4,410$ audio samples at $44.1\text{ kHz}$ ($8,820\text{ bytes}$) |
| **Burst Idle Gap ($T_{\text{idle}}$)** | **$200\text{ ms}$** | Allows JTAG FIFOs to flush without packet drops |
| **Total Refresh Cycle ($T_{\text{cycle}}$)**| **$300\text{ ms}$** | Refreshes plot $\approx 3.33\text{ times/second}$ |

### 4.2 Laptop $\rightarrow$ FPGA Audio Packet Structure (JTAG TX)
Audio bursts are packaged into a binary structure sent from Python over the local TCP socket to System Console, which forwards it to the JTAG UART:

| Byte Offset | Field Name | Data Type | Value / Description |
| :--- | :--- | :--- | :--- |
| `0..1` | **Sync Header** | `uint16_t` | `0x1234` (Incoming Audio Sync Magic Bytes) |
| `2..3` | **Burst Sequence ID** | `uint16_t` | Incremental counter (`0, 1, 2, ...`) |
| `4..5` | **Sample Count** | `uint16_t` | `4410` |
| `6..8825` | **PCM Audio Samples** | `int16_t[4410]` | 16-bit signed raw PCM audio payload |
| `8826..8827`| **Checksum** | `uint16_t` | 16-bit modular sum of all 4,410 samples |

### 4.3 FPGA $\rightarrow$ Laptop STFT Packet Structure (JTAG RX)
A 100 ms audio burst ($4,410$ samples) yields $7$ overlapping FFT frames ($N=1024, H=512$). For each frame, the FPGA transmits a 1034-byte packet:

| Byte Offset | Field Name | Data Type | Value / Description |
| :--- | :--- | :--- | :--- |
| `0..1` | **Sync Header** | `uint16_t` | `0xABCD` (Outgoing STFT Spectrum Magic Bytes) |
| `2..3` | **Frame Sequence ID** | `uint16_t` | Incremental frame index counter |
| `4..5` | **Bin Count ($K$)** | `uint16_t` | `513` |
| `6..1031` | **Magnitude Bins** | `uint16_t[513]` | 513 magnitude values ($0\text{ Hz}$ to $22.05\text{ kHz}$) |
| `1032..1033`| **Checksum** | `uint16_t` | 16-bit modular sum of all 513 magnitude bins |

---

## 5. FPGA Hardware Architecture (Verilog & Qsys)

### 5.1 Datapath Modules
1. **JTAG UART IP Core (Platform Designer):** Connects the JTAG physical scan chain to internal Avalon Streaming (Avalon-ST) interfaces.
2. **Audio RX FIFO (Dual-Clock DCFIFO):**
   * **Depth:** $8,192\text{ words}$ ($16\text{-bit}$ width).
   * **Function:** Receives audio packets from the asynchronous JTAG clock domain and safely crosses into the `CLOCK_50` domain.
3. **Framing & Windowing Unit:**
   * Reads 1024-sample frames with a 512-sample hop step from the RX FIFO.
   * Multiplies samples by a 1024-entry single-port M10K ROM storing Hann coefficients in Q1.15 fixed-point format ($0 \text{ to } 32767$).
   * Performs scaling: `Product = (PCM_signed * LUT_unsigned) >>> 15`.
4. **Intel FFT IP Core:**
   * 1024-point streaming architecture, 16-bit input/output precision, Natural Order input/output.
5. **Alpha-Max Beta-Min Magnitude Unit:**
   * Computes $|I| = \text{abs}(I)$ and $|Q| = \text{abs}(Q)$.
   * Computes `Mag = max(I, Q) + (min(I, Q) >> 2) + (min(I, Q) >> 3)`.
6. **STFT TX FIFO (Dual-Clock DCFIFO):**
   * **Depth:** $4,096\text{ words}$ ($16\text{-bit}$ width).
   * **Function:** Buffers output STFT frames in the `CLOCK_50` domain until System Console polls the JTAG UART.

---

## 6. Simulation & Testing Methodologies

### 6.1 Laptop GUI Simulation (Python Mock TCP Server)
Before compiling hardware, verify the Python `pyqtgraph` GUI interface on Ubuntu:
* **Procedure:** Run a Python mock server script listening on `127.0.0.1:12345`.
* **Behavior:** Generates synthetic 513-bin magnitude packets containing moving Gaussian curves or sine wave spikes, formatted with header `0xABCD`, bin payload, and checksum.
* **Verification Criteria:** The PyQtGraph window renders smooth spectrum animation (>30 FPS) with correctly labeled frequency axes ($0 \text{ to } 22,050\text{ Hz}$) and zero socket drops.

### 6.2 FPGA Hardware RTL Simulation (Icarus Verilog & GTKWave)
In Quartus Prime Lite 25.1 on Linux, RTL functional simulation is executed directly from the terminal using **Icarus Verilog (`iverilog`)** and **GTKWave**.

#### A. Testbench Instrumentation (`tb_stft.v`)
Add the Value Change Dump (`.vcd`) generation block to your Verilog testbench:
```verilog
initial begin
    $dumpfile("waveform.vcd");
    $dumpvars(0, tb_stft);
end
```

#### B. Compiling & Executing Standalone Logic Modules
For custom RTL modules (e.g., Hann Window LUT Multiplier, Alpha-Max Beta-Min Unit):
1. **Compile:**
   ```bash
   iverilog -o sim_out tb_stft.v hann_multiplier.v alpha_max_beta_min.v
   ```
2. **Run Engine:**
   ```bash
   vvp sim_out
   ```
   * *Verification:* Confirm terminal displays `VCD info: dumpfile waveform.vcd opened for output.` without syntax or runtime errors.

#### C. Compiling with Intel FPGA Primitives / IP Cores (Quartus 25.1 Libraries)
When simulating top-level designs containing Intel IP cores (e.g., Dual-Clock FIFOs, Megafunctions), link Quartus's Verilog simulation model libraries:
1. **Compile with Quartus 25.1 Simulation Libraries:**
   ```bash
   iverilog -o sim_out \
     -g2012 \
     ~/intelFPGA_lite/25.1/quartus/eda/sim_lib/220model.v \
     ~/intelFPGA_lite/25.1/quartus/eda/sim_lib/altera_mf.v \
     ~/intelFPGA_lite/25.1/quartus/eda/sim_lib/sgate.v \
     tb_stft.v top_stft_module.v
   ```
2. **Execute Engine:**
   ```bash
   vvp sim_out
   ```
   * *Verification:* Confirm simulation executes to `$finish` and outputs expected `$display` assertions.

#### D. Waveform Analysis in GTKWave
1. **Launch GTKWave:**
   ```bash
   gtkwave waveform.vcd &
   ```
2. **Inspect Waveforms:** In the GTKWave GUI, expand the `tb_stft` hierarchy under **SST**, select signals (e.g., `clk`, `audio_in`, `ready`, `valid`, `magnitude_out`), and click **Append** to visually verify handshaking timing and calculation accuracy.

### 6.3 On-Chip JTAG Hardware Run
* Flash the synthesized `.sof` bitstream to the DE10-Standard board using Quartus Programmer.
* Execute the host Python program on Ubuntu. Sweeping an input audio frequency from $100\text{ Hz}$ to $10\text{ kHz}$ confirms real-time spectral tracking on the PyQtGraph UI.