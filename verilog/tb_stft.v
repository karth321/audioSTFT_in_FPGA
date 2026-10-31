`timescale 1ns / 1ps

module tb_stft;

    // --- System Signals ---
    reg clk;
    reg rst_n;

    // --- Avalon-ST Sink (Simulating Laptop JTAG TX to FPGA) ---
    reg  [15:0] jtag_rx_data;
    reg         jtag_rx_valid;
    wire        jtag_rx_ready;

    // --- Avalon-ST Source (Simulating FPGA JTAG RX back to Laptop) ---
    wire [15:0] jtag_tx_data;
    wire        jtag_tx_valid;
    reg         jtag_tx_ready;

    // --- Internal Datapath Interconnects ---
    wire [15:0] audio_data;
    wire        audio_valid;
    wire        audio_ready;

    wire [15:0] mag_data;
    wire        mag_valid;
    wire        mag_ready;

    // --- Module Instantiations ---
    
    // 1. Packet Parser
    jtag_input_receiver u_rx (
        .clk(clk),
        .rst_n(rst_n),
        .asi_data(jtag_rx_data),
        .asi_valid(jtag_rx_valid),
        .asi_ready(jtag_rx_ready),
        .aso_audio_data(audio_data),
        .aso_audio_valid(audio_valid),
        .aso_audio_ready(audio_ready)
    );

    // 2. Signal Processing (Windowing + FFT + Magnitude)
    signal_processing u_dsp (
        .clk(clk),
        .rst_n(rst_n),
        .rx_fifo_data(audio_data),
        .rx_fifo_valid(audio_valid),
        .rx_fifo_ready(audio_ready),
        .mag_data(mag_data),
        .mag_valid(mag_valid),
        .mag_ready(mag_ready)
    );

    // 3. STFT Packet Formatter
    output_formatter u_fmt (
        .clk(clk),
        .rst_n(rst_n),
        .mag_data(mag_data),
        .mag_valid(mag_valid),
        .mag_ready(mag_ready),
        .tx_data(jtag_tx_data),
        .tx_valid(jtag_tx_valid),
        .tx_ready(jtag_tx_ready)
    );

    // --- Clock Generation (50 MHz) ---
    always #10 clk = ~clk; 

    // --- Avalon-ST Task for Streaming Data ---
    task send_jtag_word(input [15:0] word);
        begin
            jtag_rx_data <= word;
            jtag_rx_valid <= 1'b1;
            @(posedge clk);
            while (!jtag_rx_ready) @(posedge clk); // Handle backpressure
        end
    endtask

    // --- Stimulus & Simulation Block ---
    integer i;
    reg [15:0] tx_checksum;

    initial begin
        // VCD Dump for GTKWave
        $dumpfile("waveform.vcd");
        $dumpvars(0, tb_stft);

        // Initialize
        clk = 0;
        rst_n = 0;
        jtag_rx_data = 16'd0;
        jtag_rx_valid = 1'b0;
        jtag_tx_ready = 1'b1; // Host is always ready to receive

        // Apply Reset
        #50;
        rst_n = 1;
        #50;

        $display("Time: %0t | Starting Simulated 100ms Audio Burst...", $time);

        // 1. Send Sync Header
        send_jtag_word(16'h1234);
        
        // 2. Send Sequence ID
        send_jtag_word(16'd0);
        
        // 3. Send Sample Count (4,410)
        send_jtag_word(16'd4410);
        
        // 4. Send Audio Payload (Simulating a simple digital ramp/sawtooth wave)
        tx_checksum = 16'd0;
        for (i = 0; i < 4410; i = i + 1) begin
            send_jtag_word(i * 5);       // Simulated ADC value
            tx_checksum = tx_checksum + (i * 5); // 16-bit modular sum
        end
        
        // 5. Send Checksum
        send_jtag_word(tx_checksum);
        
        // Drop Valid Signal
        jtag_rx_valid <= 1'b0;
        $display("Time: %0t | Burst Transmission Complete. Waiting for FFT Processing...", $time);

        // Wait enough time for the pipelined FFT and formatter to finish
        // (1024 points * multiple frames takes time to push through)
        #200000;
        
        $display("Time: %0t | Simulation Finished.", $time);
        $finish;
    end

    // --- Output Monitor (Simulating Python Receiver) ---
    always @(posedge clk) begin
        if (jtag_tx_valid && jtag_tx_ready) begin
            if (jtag_tx_data == 16'hABCD) begin
                $display("Time: %0t | --------------------------------------", $time);
                $display("Time: %0t | STFT OUTPUT PACKET SYNC (0xABCD) CAUGHT!", $time);
            end else begin
                // $display("Time: %0t | Output Word: %d", $time, jtag_tx_data);
            end
        end
    end

endmodule