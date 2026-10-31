// Signal Processing: Hann Window -> FFT Core -> Alpha-Max Beta-Min Magnitude
module signal_processing (
    input  wire        clk,
    input  wire        rst_n,
    
    // Sink from Audio RX FIFO
    input  wire [15:0] rx_fifo_data,   // 16-bit signed PCM audio
    input  wire        rx_fifo_valid,
    output wire        rx_fifo_ready,
    
    // Source to Output Formatter
    output wire [15:0] mag_data,       // 16-bit unsigned linear magnitude
    output wire        mag_valid,
    input  wire        mag_ready
);

    // --- 1. HANN WINDOW MULTIPLIER ---
    reg  [9:0]  sample_idx;
    wire [15:0] hann_coeff;
    
    // Instantiate Hann ROM LUT
    hann_rom_lut u_hann_lut (
        .clk(clk),
        .addr(sample_idx),
        .q(hann_coeff)
    );

    // Track frame sample position (0 to 1023)
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sample_idx <= 10'd0;
        end else if (rx_fifo_valid && rx_fifo_ready) begin
            sample_idx <= sample_idx + 10'd1;
        end
    end

    // Signed PCM (16-bit) x Unsigned Hann (16-bit Q1.15) -> 32-bit Product
    wire signed [31:0] windowed_full = $signed(rx_fifo_data) * $signed({1'b0, hann_coeff});
    wire signed [15:0] windowed_pcm  = windowed_full[30:15]; // Shift right 15 bits

    // --- 2. INTEL 1024-POINT FFT CORE INSTANTIATION ---
    wire [15:0] fft_real;
    wire [15:0] fft_imag;
    wire        fft_valid;
    
    // Intel FFT Megafunction (Generated via Quartus IP Catalog)
    // Intel 1024-Point FFT Core (Block Floating Point, Streaming)
    fft_1024_core u_fft_ip (
        .clk          (clk),
        .reset_n      (rst_n),
        .sink_valid   (rx_fifo_valid),
        .sink_ready   (rx_fifo_ready),
        .sink_real    (windowed_pcm),
        .sink_imag    (16'd0),        // Pure real input audio
        .inverse      (1'b0),         // 1'b0 = Forward FFT, 1'b1 = Inverse FFT
        .source_valid (fft_valid),
        .source_ready (mag_ready),
        .source_real  (fft_real),
        .source_imag  (fft_imag),
        .source_exp   ()              // Block exponent output (unconnected)
    );

    // --- 3. ALPHA-MAX BETA-MIN MAGNITUDE CALCULATOR ---
    wire [15:0] abs_i = (fft_real[15]) ? (~fft_real + 1'b1) : fft_real;
    wire [15:0] abs_q = (fft_imag[15]) ? (~fft_imag + 1'b1) : fft_imag;
    
    wire [15:0] max_val = (abs_i > abs_q) ? abs_i : abs_q;
    wire [15:0] min_val = (abs_i > abs_q) ? abs_q : abs_i;
    
    // Mag = max + (min >> 2) + (min >> 3)
    assign mag_data  = max_val + (min_val >> 2) + (min_val >> 3);
    assign mag_valid = fft_valid;

endmodule