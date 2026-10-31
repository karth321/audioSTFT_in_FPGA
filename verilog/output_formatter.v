// Formats STFT Output Frame into Binary Packets
module output_formatter (
    input  wire        clk,
    input  wire        rst_n,
    
    // Sink from Signal Processing Magnitude Unit
    input  wire [15:0] mag_data,
    input  wire        mag_valid,
    output reg         mag_ready,
    
    // Source to STFT TX FIFO
    output reg  [15:0] tx_data,
    output reg         tx_valid,
    input  wire        tx_ready
);

    localparam S_HEADER_SYNC  = 3'd0;
    localparam S_HEADER_ID    = 3'd1;
    localparam S_HEADER_COUNT = 3'd2;
    localparam S_SEND_BINS    = 3'd3;
    localparam S_SEND_CHK     = 3'd4;

    reg [2:0]  state;
    reg [15:0] frame_id;
    reg [9:0]  bin_counter;
    reg [15:0] checksum;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state       <= S_HEADER_SYNC;
            frame_id    <= 16'd0;
            tx_valid <= 1'b0;   // Correct
            mag_ready   <= 1'b0;
            bin_counter <= 10'd0;
            checksum    <= 16'd0;
            tx_data     <= 16'd0;
        end else begin
            tx_valid  <= 1'b0;
            mag_ready <= 1'b0;
            
            case (state)
                S_HEADER_SYNC: begin
                    if (tx_ready && mag_valid) begin
                        tx_data  <= 16'hABCD; // Magic Output Header
                        tx_valid <= 1'b1;
                        checksum <= 16'h0;
                        state    <= S_HEADER_ID;
                    end
                end
                S_HEADER_ID: begin
                    if (tx_ready) begin
                        tx_data  <= frame_id;
                        tx_valid <= 1'b1;
                        state    <= S_HEADER_COUNT;
                    end
                end
                S_HEADER_COUNT: begin
                    if (tx_ready) begin
                        tx_data     <= 16'd513; // 513 Bins (N/2 + 1)
                        tx_valid    <= 1'b1;
                        bin_counter <= 10'd0;
                        mag_ready   <= 1'b1;
                        state       <= S_SEND_BINS;
                    end
                end
                S_SEND_BINS: begin
                    mag_ready <= tx_ready;
                    if (mag_valid && tx_ready) begin
                        tx_data     <= mag_data;
                        tx_valid    <= 1'b1;
                        checksum    <= checksum + mag_data;
                        bin_counter <= bin_counter + 10'd1;
                        
                        if (bin_counter == 10'd512) begin
                            state     <= S_SEND_CHK;
                            mag_ready <= 1'b0;
                        end
                    end
                end
                S_SEND_CHK: begin
                    if (tx_ready) begin
                        tx_data  <= checksum;
                        tx_valid <= 1'b1;
                        frame_id <= frame_id + 16'd1;
                        state    <= S_HEADER_SYNC;
                    end
                end
                default: state <= S_HEADER_SYNC;
            endcase
        end
    end
endmodule