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
        # Convert binary data to hex representation
        binary scan $data H* hex_data
        
        puts "Received $num_bytes bytes over TCP:"
        # Print the first 24 hex characters (Header + First Few Samples)
        puts "  Hex Snippet: [string range $hex_data 0 23]..."
    }
}

# Create TCP Server listening on port 12345
set server_socket [socket -server accept_connection $PORT]
puts "System Console TCP Bridge running on 127.0.0.1:$PORT..."

# Keep System Console running in event loop
vwait forever