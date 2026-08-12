package dcim_pkg;

    localparam int DW         =  8;     // shouldn't be changed when using hardened dcim sram macro
    localparam int N_WEIGHTS  =  1;
    localparam int ROWS       =  32;
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
