import os
import sys
import time
import socket
import struct
import subprocess
import threading
import numpy as np

# System Parameters matching FPGA Hardware Logic
PORT = 12345
FRAME_SIZE = 1024
HOP_SIZE = 512
NUM_BINS = 513
AUDIO_PACKET_SIZE = 8828  # 2(Header) + 2(Seq) + 2(Count) + 8820(Payload) + 2(Checksum)
STFT_PACKET_SIZE = 1034   # 2(Header) + 2(Seq) + 2(Count) + 1026(Payload) + 2(Checksum)

# Pre-calculate 1024-entry Q1.15 Fixed-Point Hann Window (0 to 32767)
hann_float = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(FRAME_SIZE) / (FRAME_SIZE - 1))
hann_q15 = np.int32(np.round(hann_float * 32767))


def alpha_max_beta_min(i_comp, q_comp):
    """
    Alpha-Max Beta-Min Linear Magnitude Approximation in bit-shift math:
    |X[k]| ≈ max(|I|, |Q|) + (|min(|I|, |Q|)| >> 2) + (|min(|I|, |Q|)| >> 3)
    """
    # Cast float FFT components to integer for fixed-point bit shifts
    abs_i = np.abs(i_comp).astype(np.int64)
    abs_q = np.abs(q_comp).astype(np.int64)
    
    max_val = np.maximum(abs_i, abs_q)
    min_val = np.minimum(abs_i, abs_q)
    
    mag = max_val + (min_val >> 2) + (min_val >> 3)
    return mag


def process_audio_burst(audio_samples, frame_seq_start):
    """
    Extracts 7 overlapping 1024-sample frames from a 4,410-sample burst,
    applies Q1.15 Hann windowing, computes FFT, and applies Alpha-Max Beta-Min.
    """
    stft_packets = []
    frame_seq = frame_seq_start

    # 4410 audio samples fit 7 overlapping frames of 1024 samples with 512 hop
    for frame_idx in range(7):
        start_sample = frame_idx * HOP_SIZE
        frame = audio_samples[start_sample : start_sample + FRAME_SIZE]

        if len(frame) < FRAME_SIZE:
            frame = np.pad(frame, (0, FRAME_SIZE - len(frame)), mode='constant')

        # 1. Hann Window LUT Multiplication: Product = (PCM * LUT) >>> 15
        windowed = (frame.astype(np.int32) * hann_q15) >> 15

        # 2. 1024-Point Real FFT
        fft_out = np.fft.rfft(windowed, n=FRAME_SIZE)

        # 3. Alpha-Max Beta-Min Magnitude Unit
        mag_approx = alpha_max_beta_min(fft_out.real, fft_out.imag)

        # 4. Bit-shift scaling for uint16 magnitude bins
        mags_uint16 = np.clip(mag_approx // 16, 0, 65535).astype(np.uint16)

        # 5. Calculate 16-bit modular sum checksum
        checksum = np.sum(mags_uint16, dtype=np.uint16)

        # 6. Pack STFT Output Frame (0xABCD Header)
        header = struct.pack('<HHH', 0xABCD, frame_seq, NUM_BINS)
        payload = mags_uint16.tobytes()
        footer = struct.pack('<H', checksum)
        packet = header + payload + footer

        stft_packets.append(packet)
        frame_seq = (frame_seq + 1) % 65536

    return stft_packets, frame_seq


def run_fpga_server():
    """
    TCP Server simulating the Intel System Console & FPGA Hardware
    """
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(('127.0.0.1', PORT))
    server_sock.listen(1)

    print(f"[FPGA SIMULATOR] Server initialized. Listening on 127.0.0.1:{PORT}...")

    # Spawn interface.py in a separate thread once server is ready
    def launch_interface():
        time.sleep(0.5)
        print("[FPGA SIMULATOR] Launching host interface application (interface.py)...")
        subprocess.run([sys.executable, "interface.py"])

    threading.Thread(target=launch_interface, daemon=True).start()

    client_sock, addr = server_sock.accept()
    print(f"[FPGA SIMULATOR] Client connected from {addr[0]}:{addr[1]}")

    rx_buffer = bytearray()
    frame_sequence_id = 0
    tx_sync_bytes = b'\x34\x12'  # 0x1234 Little-Endian

    try:
        while True:
            data = client_sock.recv(4096)
            if not data:
                break
            rx_buffer.extend(data)

            # Search for incoming audio packets (0x1234)
            while len(rx_buffer) >= AUDIO_PACKET_SIZE:
                idx = rx_buffer.find(tx_sync_bytes)
                if idx == -1:
                    del rx_buffer[:-1]
                    break

                if len(rx_buffer) >= idx + AUDIO_PACKET_SIZE:
                    packet = rx_buffer[idx : idx + AUDIO_PACKET_SIZE]

                    # Parse Audio Payload
                    sync, burst_id, count = struct.unpack('<HHH', packet[0:6])
                    pcm_bytes = packet[6:8826]
                    rcv_chk, = struct.unpack('<H', packet[8826:8828])

                    audio_samples = np.frombuffer(pcm_bytes, dtype=np.int16)
                    calc_chk = np.sum(audio_samples, dtype=np.uint16)

                    if rcv_chk == calc_chk:
                        print(f"[FPGA SIMULATOR] RX Burst {burst_id:04d} Validated. Executing STFT Pipeline...")

                        # Compute Hardware STFT
                        stft_frames, frame_sequence_id = process_audio_burst(audio_samples, frame_sequence_id)

                        # Transmit 7 STFT packets back to interface.py over TCP
                        for stft_packet in stft_frames:
                            client_sock.sendall(stft_packet)
                            time.sleep(0.005)  # Emulate 5ms JTAG packet clocking
                    else:
                        print(f"[FPGA SIMULATOR] RX Burst {burst_id:04d} Checksum Mismatch! Dropping.")

                    del rx_buffer[: idx + AUDIO_PACKET_SIZE]
                else:
                    break

    except (KeyboardInterrupt, ConnectionResetError):
        print("\n[FPGA SIMULATOR] Stopping Simulation...")
    finally:
        client_sock.close()
        server_sock.close()
        print("[FPGA SIMULATOR] TCP Server Closed.")


if __name__ == "__main__":
    run_fpga_server()