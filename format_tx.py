import time
import socket
import struct
import numpy as np
from scipy.io import wavfile

def transmit_audio_to_fpga(wav_file_path, host='127.0.0.1', port=12345):
    """
    Reads a .wav file, formats it, and transmits it via TCP socket 
    to the Intel System Console for JTAG forwarding.
    """
    print(f"Loading audio file: {wav_file_path}")
    
    # 1. Read the audio file
    sample_rate, audio_data = wavfile.read(wav_file_path)
    
    # Ensure audio is Mono
    if len(audio_data.shape) > 1:
        print("Converting stereo audio to mono...")
        audio_data = audio_data.mean(axis=1)
        
    # Ensure audio is 16-bit signed PCM
    audio_data = audio_data.astype(np.int16)
    
    # Verify sampling rate
    if sample_rate != 44100:
        print(f"Warning: Expected 44.1 kHz sampling rate, got {sample_rate} Hz.")
        # Note: In a production environment, you would use scipy.signal.resample here.

    # 2. Connect to the Intel System Console (TCP Bridge)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        print(f"Connected to Intel System Console at {host}:{port}")
    except ConnectionRefusedError:
        print(f"Connection failed. Ensure System Console is running a server on {host}:{port}.")
        return

    # 3. Transmission Parameters
    samples_per_burst = 4410  # 100 ms burst at 44.1 kHz
    sync_header = 0x1234      # Incoming Audio Sync Magic Bytes
    seq_id = 0
    total_samples = len(audio_data)

    print("Starting audio transmission over JTAG...")
    
    # 4. Transmit loop
    for i in range(0, total_samples, samples_per_burst):
        chunk = audio_data[i : i + samples_per_burst]
        
        # Pad with zeros if it's the final chunk and smaller than 4,410 samples
        if len(chunk) < samples_per_burst:
            chunk = np.pad(chunk, (0, samples_per_burst - len(chunk)), mode='constant')

        # Calculate 16-bit modular sum checksum
        # Using uint16 automatically applies modulo 65536 arithmetic
        checksum = np.sum(chunk, dtype=np.uint16)
        
        # Construct the binary packet
        # Using '<' for little-endian encoding (standard for Intel/FPGA logic)
        # H = uint16_t (2 bytes)
        header = struct.pack('<HHH', sync_header, seq_id, samples_per_burst)
        payload = chunk.tobytes()
        footer = struct.pack('<H', checksum)
        
        packet = header + payload + footer
        
        # Send the packet over TCP
        sock.sendall(packet)
        print(f"Transmitted burst {seq_id} | Payload Size: {len(packet)} bytes")
        
        # Increment sequence ID and wrap around at 65535
        seq_id = (seq_id + 1) % 65536 
        
        # 5. Timing Control: 300 ms total cycle
        # 100 ms burst processing + 200 ms idle gap to clear JTAG buffers
        time.sleep(0.3)
        
    sock.close()
    print("Audio transmission complete.")

if __name__ == "__main__":
    # Example usage: Replace 'input_audio.wav' with your audio file
    # transmit_audio_to_fpga("input_audio.wav")
    pass