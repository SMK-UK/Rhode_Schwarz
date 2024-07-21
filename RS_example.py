import RS_Scope

# Initialise Scope
IP = 000.000.00.00                  # Scope IP address
instr = RS_Scope(IP,'LAN')         # Connect to scope through ethernet

instr = RS_Scope(IP, 'LAN')        # connet via LAN
instr.calibration()                 # calibrate the instrument (will take a few minutes)

instr.channels = [1, 2]             # set visible channels
instr.acquire(mode='AVER',          # perform average measurement
               N=50)                # number of traces in the average
instr.save_channels()               # save all visible channels

instr.fname = 'test_single'         # set new file name
instr.acquire(mode='SING',          # take single trace
              auto=False,           # set auto resolution false
              length=1E6,           # define the record length (resolution)
              save=True)            # auto-save visible channels

instr.fname = 'test_Nx'             # set new file name
instr.acquire(mode='NSING',         # take single trace
              auto=False,           # set auto resolution false
              N = 10,               # number of single shots to record
              length=1E6,           # define the record length (resolution)
              save=True)            # auto-save visible channels from history

instr.screenshot()                  # take screenshot off the scope screen
