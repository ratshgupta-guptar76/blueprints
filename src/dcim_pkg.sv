package dcim_pkg;

    localparam int DW         =  8;
    localparam int N_WEIGHTS  =  8;
    localparam int ROWS       =  64;
    localparam int COLS       =  N_WEIGHTS*DW;

    localparam bit W_SIGN = 1;
    localparam int W_BITS = DW;

    localparam bit A_SIGN      =  0;
    localparam int A_MAX_BITS  =  DW;

    localparam int ACC_WIDTH  = DW + A_MAX_BITS + $clog2(ROWS);


    // Latency depends on the FSM states and the rest of the architecture
    // Uncomment and fix the code below after that is implemented
    // localparam int LATENCY = A_PRECISION + OVERHEAD;


endpackage: dcim_pkg
