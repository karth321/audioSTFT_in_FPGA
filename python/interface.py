import os
import sys
import time
import socket
import struct
import subprocess
import shutil
import signal
import numpy as np
from scipy.io import wavfile
import pyqtgraph as pg
from PyQt5 import QtWidgets, QtCore

class JtagTransceiver(QtCore.QThread):
    """
    Background thread that handles sending audio bursts to the FPGA
    and reading back the STFT magnitude packets via the JTAG TCP socket.
    """
    new_stft_data = QtCore.pyqtSignal(np.ndarray)
    status_msg = QtCore.pyqtSignal(str)

    def __init__(self, wav_file_path, host='127.0.0.1', port=12345):
        super().__init__()
        self.wav_file_path = os.path.abspath(wav_file_path)
        self.host = host
        self.port = port
        self.running = True
        self.player_process = None
        self.sock = None

    def get_audio_player_cmd(self):
        if shutil.which('aplay'):
            return ['aplay', self.wav_file_path]
        elif shutil.which('vlc'):
            return ['vlc', '--play-and-exit', self.wav_file_path]
        elif shutil.which('flatpak'):
            return ['flatpak', 'run', 'org.videolan.VLC', '--play-and-exit', self.wav_file_path]
        return None

    def run(self):
        # 1. Load Audio
        self.status_msg.emit(f"Loading {os.path.basename(self.wav_file_path)}...")
        try:
            sample_rate, audio_data = wavfile.read(self.wav_file_path)
        except Exception as e:
            self.status_msg.emit(f"Failed to read WAV file: {e}")
            return
        
        if len(audio_data.shape) > 1:
            audio_data = audio_data.mean(axis=1)
        audio_data = audio_data.astype(np.int16)

        # 2. Connect to Socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(0.1) # Non-blocking socket for responsive reading
        try:
            self.sock.connect((self.host, self.port))
            self.status_msg.emit(f"Connected to JTAG Bridge at {self.host}:{self.port}")
        except Exception as e:
            self.status_msg.emit(f"Connection failed: {e}")
            return

        # 3. Start Audio Player
        player_cmd = self.get_audio_player_cmd()
        if player_cmd:
            self.player_process = subprocess.Popen(player_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # 4. Transmission Variables
        samples_per_burst = 4410
        tx_sync_header = 0x1234
        seq_id = 0
        total_samples = len(audio_data)
        
        rx_buffer = bytearray()
        packet_size = 1034 # 2(Sync) + 2(ID) + 2(Count) + 1026(Bins) + 2(Checksum)
        sync_bytes = b'\xcd\xab' # 0xABCD in little-endian

        # 5. Main Processing Loop
        for i in range(0, total_samples, samples_per_burst):
            if not self.running:
                break
            
            loop_start = time.time()

            # --- TRANSMIT ---
            chunk = audio_data[i : i + samples_per_burst]
            if len(chunk) < samples_per_burst:
                chunk = np.pad(chunk, (0, samples_per_burst - len(chunk)), mode='constant')

            checksum = np.sum(chunk, dtype=np.uint16)
            header = struct.pack('<HHH', tx_sync_header, seq_id, samples_per_burst)
            payload = chunk.tobytes()
            footer = struct.pack('<H', checksum)
            
            try:
                self.sock.sendall(header + payload + footer)
            except Exception as e:
                self.status_msg.emit(f"Socket error during TX: {e}")
                break
                
            seq_id = (seq_id + 1) % 65536

            # --- RECEIVE ---
            while time.time() - loop_start < 0.3:
                if not self.running:
                    break
                try:
                    data = self.sock.recv(4096)
                    rx_buffer.extend(data)
                    
                    while len(rx_buffer) >= packet_size:
                        idx = rx_buffer.find(sync_bytes)
                        if idx == -1:
                            del rx_buffer[:-1]
                            break
                            
                        if len(rx_buffer) >= idx + packet_size:
                            packet = rx_buffer[idx : idx + packet_size]
                            bins_bytes = packet[6:1032]
                            magnitudes = np.frombuffer(bins_bytes, dtype=np.uint16)
                            
                            rcv_checksum, = struct.unpack('<H', packet[1032:1034])
                            calc_checksum = np.sum(magnitudes, dtype=np.uint16)
                            
                            if rcv_checksum == calc_checksum:
                                self.new_stft_data.emit(magnitudes)
                            
                            del rx_buffer[:idx + packet_size]
                        else:
                            break
                            
                except socket.timeout:
                    continue
                except Exception as e:
                    self.status_msg.emit(f"Socket error during RX: {e}")
                    break

        self.cleanup()

    def stop(self):
        self.running = False

    def cleanup(self):
        if self.player_process and self.player_process.poll() is None:
            self.player_process.terminate()
            self.player_process.wait()
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        self.status_msg.emit("Transmission stopped. JTAG Socket closed.")


class STFTVisualizer(QtWidgets.QMainWindow):
    def __init__(self, wav_file_path):
        super().__init__()
        self.setWindowTitle("Live FPGA STFT Spectrum Analyzer")
        self.resize(1000, 600)

        # Main Layout
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        widget.setLayout(layout)
        self.setCentralWidget(widget)

        # Status Label
        self.status_label = QtWidgets.QLabel("Initializing...")
        self.status_label.setStyleSheet("font-weight: bold; color: #333;")
        layout.addWidget(self.status_label)

        # PyQtGraph Setup
        self.plot_widget = pg.PlotWidget(background='w')
        self.plot_widget.setLabel('left', 'Magnitude (Linear)', color='k')
        self.plot_widget.setLabel('bottom', 'Frequency (Hz)', color='k')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setYRange(0, 10000)
        self.plot_widget.setXRange(0, 22050) 
        
        pen = pg.mkPen(color=(0, 114, 178), width=2)
        
        self.freq_axis = np.array([k * (44100 / 1024) for k in range(513)])
        self.curve = self.plot_widget.plot(self.freq_axis, np.zeros(513), pen=pen, fillLevel=0, brush=(0, 114, 178, 50))
        
        layout.addWidget(self.plot_widget)

        # Thread Setup
        self.transceiver_thread = JtagTransceiver(wav_file_path)
        self.transceiver_thread.new_stft_data.connect(self.update_plot)
        self.transceiver_thread.status_msg.connect(self.update_status)
        
        self.transceiver_thread.start()

    def update_plot(self, magnitudes):
        max_val = np.max(magnitudes)
        if max_val > self.plot_widget.getViewBox().viewRange()[1][1]:
            self.plot_widget.setYRange(0, max_val * 1.2)
            
        self.curve.setData(self.freq_axis, magnitudes)

    def update_status(self, msg):
        self.status_label.setText(msg)

    def closeEvent(self, event):
        self.status_label.setText("Shutting down... please wait.")
        self.transceiver_thread.stop()
        self.transceiver_thread.wait()
        event.accept()

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    
    # Target audio file
    audio_file = "../savfk-the-travelling-symphony.wav" 
    
    window = STFTVisualizer(audio_file)
    window.show()

    # Allow Ctrl+C (SIGINT) to terminate the PyQt Application cleanly
    signal.signal(signal.SIGINT, lambda *args: app.quit())

    # Periodically wake up Python interpreter to process POSIX signals (SIGINT)
    timer = QtCore.QTimer()
    timer.start(200)
    timer.timeout.connect(lambda: None)

    sys.exit(app.exec_())