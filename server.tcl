# server.tcl - Intel System Console TCP Bridge Server

set PORT 12345

# Callback when Python client connects
proc accept_connection {channel addr port} {
    puts "Accepted TCP connection from $addr:$port"
    fconfigure $channel -translation binary -blocking 0
    fileevent $channel readable [list process_data $channel]
}

# Callback when audio packet data arrives
proc process_data {channel} {
    if {[eof $channel]} {
        puts "Python client disconnected."
        close $channel
        return
    }
    set data [read $channel]
    set num_bytes [string length $data]
    if {$num_bytes > 0} {
        puts "Received $num_bytes bytes from Python Host."
        # Note: When the FPGA is flashed, JTAG master_write commands forward $data to the FPGA RX FIFO
    }
}

# Create TCP Server listening on port 12345
set server_socket [socket -server accept_connection $PORT]
puts "System Console TCP Bridge running on 127.0.0.1:$PORT..."

# Keep System Console running in event loop
vwait forever