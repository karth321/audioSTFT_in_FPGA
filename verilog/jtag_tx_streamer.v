// Streams STFT Packets to JTAG UART
module jtag_tx_streamer (
    input  wire        clk,
    input  wire        rst_n,
    
    // Avalon-ST Sink from STFT TX FIFO
    input  wire [15:0] fifo_tx_data,
    input  wire        fifo_tx_valid,
    output wire        fifo_tx_ready,
    
    // Avalon-ST Source to Platform Designer JTAG UART
    output wire [15:0] jtag_uart_data,
    output wire        jtag_uart_valid,
    input  wire        jtag_uart_ready
);

    // Direct Avalon-Streaming passthrough
    assign jtag_uart_data  = fifo_tx_data;
    assign jtag_uart_valid = fifo_tx_valid;
    assign fifo_tx_ready   = jtag_uart_ready;

endmodule