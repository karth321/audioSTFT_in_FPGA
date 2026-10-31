// Top-Level STFT Audio Processing Module on DE10-Standard FPGA
module stft_top (
    input  wire CLOCK_50,  // Onboard 50 MHz Clock (PIN_AF14)
    input  wire [0:0] KEY  // Key[0] Pushbutton for Reset (PIN_AJ4)
);

    wire clk   = CLOCK_50;
    wire rst_n = KEY[0];

    // Interconnect wires
    wire [15:0] rx_audio_data;
    wire        rx_audio_valid;
    wire        rx_audio_ready;

    wire [15:0] mag_data;
    wire        mag_valid;
    wire        mag_ready;

    wire [15:0] tx_pkt_data;
    wire        tx_pkt_valid;
    wire        tx_pkt_ready;

    // 1. JTAG Receiver
    jtag_input_receiver u_rx (
        .clk(clk),
        .rst_n(rst_n),
        .asi_data(16'd0),        // Connected to JTAG UART in Qsys
        .asi_valid(1'b0),
        .asi_ready(),
        .aso_audio_data(rx_audio_data),
        .aso_audio_valid(rx_audio_valid),
        .aso_audio_ready(rx_audio_ready)
    );

    // 2. Signal Processing Pipeline
    signal_processing u_dsp (
        .clk(clk),
        .rst_n(rst_n),
        .rx_fifo_data(rx_audio_data),
        .rx_fifo_valid(rx_audio_valid),
        .rx_fifo_ready(rx_audio_ready),
        .mag_data(mag_data),
        .mag_valid(mag_valid),
        .mag_ready(mag_ready)
    );

    // 3. Packet Output Formatter
    output_formatter u_fmt (
        .clk(clk),
        .rst_n(rst_n),
        .mag_data(mag_data),
        .mag_valid(mag_valid),
        .mag_ready(mag_ready),
        .tx_data(tx_pkt_data),
        .tx_valid(tx_pkt_valid),
        .tx_ready(tx_pkt_ready)
    );

    // 4. JTAG Streamer
    jtag_tx_streamer u_tx (
        .clk(clk),
        .rst_n(rst_n),
        .fifo_tx_data(tx_pkt_data),
        .fifo_tx_valid(tx_pkt_valid),
        .fifo_tx_ready(tx_pkt_ready),
        .jtag_uart_data(),
        .jtag_uart_valid(),
        .jtag_uart_ready(1'b1)
    );

endmodule