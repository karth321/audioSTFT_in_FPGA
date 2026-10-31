// 1024-Entry Q1.15 Fixed-Point Hann Window ROM Look-Up Table
module hann_rom_lut (
    input  wire        clk,
    input  wire [9:0]  addr, // 10-bit address for 1024 entries
    output reg  [15:0] q     // 16-bit unsigned Q1.15 coefficient
);

    // 1024 x 16-bit ROM Array
    reg [15:0] rom [0:1023];

    // Load initial coefficient hex file or infer in synthesized RAM
    initial begin
        $readmemh("hann_1024_q15.hex", rom);
    end

    always @(posedge clk) begin
        q <= rom[addr];
    end

endmodule