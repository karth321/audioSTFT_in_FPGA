import sys
import time
import socket
import struct
import subprocess
import numpy as np
from scipy.io import wavfile

def transmit_audio_and_play_vlc(wav_file_path, host='127.0.0.1', port=12345):
    """
    Reads a WAV audio file, transmits formatted 100 ms audio bursts over JTAG TCP bridge,
    and plays audio simultaneously in VLC. Supports instant graceful shutdown on Ctrl+C.
    """
    print(f"Loading audio file: {wav_file_path}")
    
    # 1. Read WAV file
    sample_rate, audio_data = wavfile.read(wav_file_path)
    
    if len(audio_data.shape) > 1:
        print("Converting stereo audio to mono...")
        audio_data = audio_data.mean(axis=1)
        
    audio_data = audio_data.astype(np.int16)
    
    if sample_rate != 44100:
        print(f"Warning: Expected 44.1 kHz sampling rate, got {sample_rate} Hz.")

    # 2. Connect to Intel System Console JTAG TCP Server
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((host, port))
        print(f"Connected to Intel System Console at {host}:{port}")
    except ConnectionRefusedError:
        print(f"Error: Connection refused. Ensure System Console is running on {host}:{port}.")
        return

    # 3. Launch VLC Player Process
    vlc_process = None
    try:
        print("Starting VLC audio playback...")
        # Launch VLC headlessly/quietly; plays alongside transmission
        vlc_process = subprocess.Popen(
            ['vlc', '--play-and-exit', wav_file_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except FileNotFoundError:
        print("Error: VLC binary not found. Install via 'sudo apt install vlc'.")
        sock.close()
        return

    # 4. Transmission Setup (100 ms burst + 200 ms idle gap)
    samples_per_burst = 4410  # 100 ms burst at 44.1 kHz
    sync_header = 0x1234
    seq_id = 0
    total_samples = len(audio_data)

    print("\nTransmission started. Press 'Ctrl + C' at any time to stop VLC, transmission, and exit.\n")

    try:
        for i in range(0, total_samples, samples_per_burst):
            chunk = audio_data[i : i + samples_per_burst]
            
            # Zero-pad final chunk if necessary
            if len(chunk) < samples_per_burst:
                chunk = np.pad(chunk, (0, samples_per_burst - len(chunk)), mode='constant')

            # Calculate 16-bit modular sum checksum
            checksum = np.sum(chunk, dtype=np.uint16)
            
            # Construct binary packet header, payload, and footer
            header = struct.pack('<HHH', sync_header, seq_id, samples_per_burst)
            payload = chunk.tobytes()
            footer = struct.pack('<H', checksum)
            packet = header + payload + footer
            
            # Transmit frame over TCP socket
            sock.sendall(packet)
            print(f"Transmitted burst {seq_id:04d} | Payload: {len(packet)} bytes")
            
            seq_id = (seq_id + 1) % 65536
            time.sleep(0.3)  # 300 ms refresh cycle

    except KeyboardInterrupt:
        print("\n[STOP SIGNAL] Keyboard Interrupt detected! Stopping all processes...")

    finally:
        # Gracefully kill VLC player process
        if vlc_process and vlc_process.poll() is None:
            vlc_process.terminate()
            vlc_process.wait()
            print("VLC process stopped.")
            
        # Close TCP connection to System Console
        sock.close()
        print("JTAG TCP Socket closed. Program terminated cleanly.")

if __name__ == "__main__":
    # Specify your WAV file
    transmit_audio_and_play_vlc("savfk-the-travelling-symphony.wav")