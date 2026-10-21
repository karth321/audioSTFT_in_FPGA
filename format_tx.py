import os
import sys
import time
import socket
import struct
import subprocess
import shutil
import numpy as np
from scipy.io import wavfile

def transmit_audio_and_play(wav_file_path, host='127.0.0.1', port=12345):
    """
    Reads a WAV file, streams formatted 100 ms audio bursts over TCP to Intel 
    System Console for JTAG forwarding, and plays audio simultaneously using aplay.
    """
    abs_wav_path = os.path.abspath(wav_file_path)
    print(f"Loading audio file: {abs_wav_path}")
    
    # 1. Read WAV file
    sample_rate, audio_data = wavfile.read(abs_wav_path)
    
    # Convert stereo to mono if needed
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

    # 3. Launch Native Linux Audio Player (aplay)
    player_process = None
    if shutil.which('aplay'):
        print("Starting real-time audio playback via 'aplay'...")
        player_process = subprocess.Popen(
            ['aplay', abs_wav_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    else:
        print("Warning: 'aplay' not found. Transmitting audio without local playback.")

    # 4. Transmission Parameters
    samples_per_burst = 4410  # 100 ms burst at 44.1 kHz
    sync_header = 0x1234      # Incoming Audio Sync Header
    seq_id = 0
    total_samples = len(audio_data)

    print("\nTransmission started. Press 'Ctrl + C' at any time to stop playback, transmission, and exit.\n")

    try:
        for i in range(0, total_samples, samples_per_burst):
            chunk = audio_data[i : i + samples_per_burst]
            
            # Zero-pad final chunk if necessary
            if len(chunk) < samples_per_burst:
                chunk = np.pad(chunk, (0, samples_per_burst - len(chunk)), mode='constant')

            # Calculate 16-bit modular sum checksum
            checksum = np.sum(chunk, dtype=np.uint16)
            
            # Pack binary packet: Header (Sync, ID, Count) + Payload + Footer (Checksum)
            header = struct.pack('<HHH', sync_header, seq_id, samples_per_burst)
            payload = chunk.tobytes()
            footer = struct.pack('<H', checksum)
            packet = header + payload + footer
            
            # Send frame over socket
            sock.sendall(packet)
            print(f"Transmitted burst {seq_id:04d} | Payload: {len(packet)} bytes")
            
            seq_id = (seq_id + 1) % 65536
            time.sleep(0.3)  # 300 ms refresh cycle (100 ms burst + 200 ms idle gap)

    except KeyboardInterrupt:
        print("\n[STOP SIGNAL] Keyboard Interrupt detected! Stopping all processes...")

    finally:
        # Gracefully kill audio player process
        if player_process and player_process.poll() is None:
            player_process.terminate()
            player_process.wait()
            print("Audio player stopped.")
            
        # Close TCP connection to System Console
        sock.close()
        print("JTAG TCP Socket closed. Program terminated cleanly.")

if __name__ == "__main__":
    transmit_audio_and_play("savfk-the-travelling-symphony.wav")