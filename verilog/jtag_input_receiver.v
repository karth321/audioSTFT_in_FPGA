// JTAG Audio Input Packet Receiver & Parser
module jtag_input_receiver (
    input  wire        clk,
    input  wire        rst_n,
    
    // Avalon-ST Sink (Interface from JTAG UART Bridge)
    input  wire [15:0] asi_data,
    input  wire        asi_valid,
    output reg         asi_ready,
    
    // Avalon-ST Source (Output raw 16-bit PCM to Audio RX FIFO)
    output reg  [15:0] aso_audio_data,
    output reg         aso_audio_valid,
    input  wire        aso_audio_ready
);

    // Packet state machine
    localparam STATE_SYNC     = 3'd0;
    localparam STATE_SEQ_ID   = 3'd1;
    localparam STATE_COUNT    = 3'd2;
    localparam STATE_PAYLOAD  = 3'd3;
    localparam STATE_CHECKSUM = 3'd4;

    reg [2:0]  state;
    reg [15:0] sample_count;
    reg [15:0] payload_counter;
    reg [15:0] calc_checksum;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state           <= STATE_SYNC;
            asi_ready       <= 1'b1;
            aso_audio_valid <= 1'b0;
            calc_checksum   <= 16'd0;
            payload_counter <= 16'd0;
            sample_count    <= 16'd0;
            aso_audio_data  <= 16'd0;
        end else begin
            asi_ready       <= aso_audio_ready;
            aso_audio_valid <= 1'b0;
            
            if (asi_valid && asi_ready) begin
                case (state)
                    STATE_SYNC: begin
                        if (asi_data == 16'h1234) begin // Match magic header 0x1234
                            state         <= STATE_SEQ_ID;
                            calc_checksum <= 16'd0;
                        end
                    end
                    STATE_SEQ_ID: begin
                        state <= STATE_COUNT;
                    end
                    STATE_COUNT: begin
                        sample_count    <= asi_data; // Expected: 4410
                        payload_counter <= 16'd0;
                        state           <= STATE_PAYLOAD;
                    end
                    STATE_PAYLOAD: begin
                        aso_audio_data  <= asi_data;
                        aso_audio_valid <= 1'b1;
                        calc_checksum   <= calc_checksum + asi_data;
                        payload_counter <= payload_counter + 16'd1;
                        
                        if (payload_counter == sample_count - 16'd1) begin
                            state <= STATE_CHECKSUM;
                        end
                    end
                    STATE_CHECKSUM: begin
                        // Packet completed, return to waiting for next burst header
                        state <= STATE_SYNC;
                    end
                    default: state <= STATE_SYNC;
                endcase
            end
        end
    end
endmodule