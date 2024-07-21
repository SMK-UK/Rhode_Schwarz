"""
Python driver for the Rohde & Schwarz oscilliscope in 
the RE Quantum memory lab.

@author Finley Giles-Book - fdg2@hw.ac.uk

Updated 05/2024

@author Sean Keenan - sk88@hw.ac.uk

"""
import csv
from numpy import linspace
import logging
import sys
from Function_files import Init_Directories
import os
from RsInstrument import *
from time import sleep, time

# set up directories to save data to
dir = Init_Directories()

class RS_Scopes(RsInstrument):
    """
    Python driver for the Rohde & Schwarz oscilliscope in the RE Quantum memory lab.

    """
    def __init__(self, 
                 address: str = dir.scope, 
                 mode: str = 'LAN',
                 verbose: bool = True
                 ):
        """
        Fuction used to connect to an instrument via LAN or USB.

        Parameters
        ----------

        self: obj
            Instrment object
        address: str
            IP adress or USB port address
        mode: str
            Connection format, 'USB', 'LAN', 'hiLAN', default is LAN

        """
        # ensures RsInstruments meets the minimum version number
        RsInstrument.assert_minimum_version('1.50.0')     

        if mode == 'hiLAN':
            resource_str = 'TCPIP::' + address + '::hislip0'
        elif mode == 'LAN':
            resource_str = 'TCPIP::' + address + '::INSTR'
        elif mode == 'USB':
            resource_str = 'USB::' + address + '::INSTR'

        else:
            print(f"Invalid mode\n Please enter either: 'hiLAN', 'LAN' or 'USB'\n ")
     
        try:
            super().__init__(resource_str)
            self.visa_timeout = 6000                                    # timeout for visa read operations
            self.opc_timeout = 3000                                     # timeout for opc-sync operations
            self.opc_timeout = 15                                       # timeout for opc_check()
            self.acquisition_timeout = 10                               # timeout for acquisition
            self.instrument_status_checking = True                      # error checking after each command            

            if verbose:
                print(f'Connection to instrument {self.query_str("SYST:NAME?")} successful')

        except Exception as ex:
            print('Error initializing the instrument session:\n' + ex.args[0])
 
        self.clear_status()
        self.reset()
        # default to all channels on
        self.write_str('CHAN:AON')
        self.channels = [1,2,3,4]
        # default internal path for screenshot data
        self.instr_path = '/INT/SCREEN/'
        self.path = dir.dropbox
        self.folder = None
        self.fname = 'file'
        self.file_format = 'csv'
        self.screenshot_format = 'png'
        self.verbose = verbose
        self.save = False

    def acquire(self,
            mode: str = "SINGle",
            N: str = 1,
            auto = True,
            length = 5E6
            ):
        """
        Start acquisition of data on available channels

        mode: str
            Acquisition type to perform:
            - SINGle: Single shot trace
            - NSINGle: N single traces saved using segmented memory
            - AVERage: Average trace using the scope average function
        N: int
            Number of traces to take (used for NSINGle and AVERage)
        save: bool
            Choose to save the waveform(s) immediately (only saves 
            the trace on screen). To save history please use the 
            'save_hist()' function
        auto: bool
            Set acquisiton length to auto or manual
        length: int
            Set the record length (samples).
        
        """
        hist = False                                            # flag for history save (used with NSING)
        try:
            self.channel_select()                               # set correct channels on
            self.write_str(f"ACQ:SEGM:STAT ON")                 # set fast segmentation on
            if auto:
                self.write_str(f"ACQ:POIN:AUT ON")              # automatically selects record length
            else:
                self.write_str(f"ACQ:POIN:AUT OFF")
                self.write_str(f"ACQ:MEM DMEM")
                if length > 40E6:
                    print(f'Maximum record length exceeded.\
                          Setting to maximum: 40MSa')
                    length = 40E6
                elif length < 5E3:
                    print(f'Minimum record length exceeded.\
                          Setting to minimum: 5kSa')
                    length = 5E3
                self.write_str(f"ACQ:POIN {length}")

            if "AVER" in mode:
                self.average(N)                                 # perform average and stop
            else:
                _, max_segments = self.check_hist_values()
                if N > int(max_segments):
                    N = int(max_segments)                       # make sure averages is less than max segments
                    if self.verbose:
                        print(f"Number of segments exceeds max segments. \
                              Setting samples (N) to {N}")
                self.write_str(f"ACQ:TYPE REFR")                # sets acquisition mode to sample
                if "NSING" in mode:
                    self.write_str(f"ACQ:NSIN:COUN {N}")        # take N single acquisitions
                    hist = True
                else:
                    self.write_str(f"ACQ:NSIN:COUN {1}")        # take a single shot trace
                self.write_str(f'RUNS')                         # run acquisition and stop
                while self.query(f"ACQ:STAT?") != 'COMP':       # check when acquisition complete
                    sleep(1)
                    if self.verbose:
                        print("Acquiring...")
            
            if self.save == True:
                if hist:
                    self.save_history()
                else:
                    self.save_channels()

        except Exception as ex:
            print('Error while acquiring data' + ex.args[0])
            return False
        
        return True

    def average(self, N):
        """
        Start an averaging sequence
        
        Parameters
        ----------
        
        N: int
            Number of averages to take
            
        """
        start_time = time()
        try:
            self.write_str(f"ACQ:TYPE AVER")                # sets acquisition mode to average
            self.write_str(f"ACQ:AVER:RES")                 # resets the averaged waveform
            self.write_str(f"ACQ:NSIN:COUN {1}")            # reset single trace count
            self.write_str(f"ACQ:AVER:COUN {N}")            # set number of waveforms to average
            self.write_str('RUN')                           # start continuous acquisition
            while self.query(f'ACQ:AVER:COMP?') != '1':
                if time() - start_time > self.acquisition_timeout:
                    print('Average acquisition timeout.')
                    break
                if self.verbose:
                    print('Acquiring...')
                sleep(1)
            self.write_str('STOP')                          # stop when averaged complete

            return True
        
        except Exception as ex:
            print(f'An error occured while acquiring \
                  the data \n' + ex.args[0])
            return False
        
    def calibration(self):
        """
        Perform a self-alignment. The self-alignment aligns the data from
        several input channels vertically and horizontally to synchronize the
        timebases, amplitudes and positions. 
        
        Recommendation for performing a self-alignment:
        
        - After a firmware update
        - Once a week
        - When major temperature changes occur (> 5 deg C)
        
        """

        try:
            # start device self calibration
            self.write_str('CAL')                                      
            # query status of self calibration
            while self.query_str('CAL:STAT?') == 'RUN':                         
                # print status and wait before re-check
                print('Instrument calibration in progress - please wait...')
                sleep(10)
            
            if self.query('CAL:SAT?') == 'OK':
                print('Self-alignment succesful!')
            elif self.query_str('CAL:STAT?') == 'ERR':                         
                print('An error occured while calibrating.')
            elif self.query_str('CAL:STAT?') == 'ABOR':                         
                print('Calibration aborted.')

        except Exception as ex:
            # print error code if fail
            print(f'Error with instrument \
                  self-alignment\n' + ex.args[0])
        
    def check_file_exists(self, format):
        """
        Check if a file path exists already and create a copy to avoid 
        not saving data or error

        Parameters
        ----------

        format: str
            file format that you wish to save the file with
        
        """
        check = True
        if self.folder:
            save_file = f'{self.path}{self.folder}{self.fname}'
        else:
            save_file = f'{self.path}{self.fname}'
        while check:
            if os.path.isfile(f'{save_file}.{format}'):
                save_file = f'{save_file}-(copy)'
            else:
                save_file = f'{save_file}.{format}'
                if self.verbose:
                    print(f"Saving file as {save_file}")
                check = False
        
        return save_file

    def check_hist_values(self):
        """
        Extract the current history settings:
            - Record length
            - Maximum segments
        
        """
        record_length = self.query(f"ACQ:POIN?")
        max_segments = self.query(f"ACQ:COUN?")

        return record_length, max_segments
        
    def channel_select(self):
        """
        Switch on desired channels and switch off others

        """
        self.write_str('CHAN:AOFF')

        # place channel numbers in a list
        if not isinstance(self.channels, list):
            self.channels = [self.channels]
        # switch desired channels on
        for channel in self.channels:
            self.write_str(f'CHAN{channel}:STAT ON')
            self.opc_check()

    def opc_check(self):
        """
        Check the OPC output of the scope and sleep if False
        
        """
        start_time = time()
        while not self.query_opc():
                if time() - start_time > self.opc_timeout:
                    print('OPC timeout.')
                    break
                sleep(0.1)

    def query_data(self, channel):
        """
        Query the selected channel data and return values if available 
        or boolean False if not

        Parameters
        ----------
        channel: int
            Channel number on scope to extract time data from

        Returns
        ---------
        chan_data: array
            Array of scope y data for the specified channel

        """
        # attempt to extract data from channel
        try:
            chan_data = self.query_bin_or_ascii_float_list(f'CHAN{str(channel)}:DATA?')
            self.opc_check()

        # flag that channel is off or unavailable    
        except Exception as ex:
            chan_data = False
            print(f"Channel {channel} unavailable. Please check connection\n")
            print('Exception raised: ' + ex.args[0])

        return chan_data
    
    def query_time(self, channel):
        """
        Query channel timebase and return array of time values or boolean False if not

        Parameters
        ----------
        channel: int
            Channel number on scope to extract time data from

        Returns
        ----------
        time_data: array
            Array of scope time data for the specified channel

        """
        # attempt to extract time data from desired channel and create array of time data
        try:
            chan_data = self.query_bin_or_ascii_float_list(f'CHAN{channel}:DATA:HEAD?')
            self.opc_check()
            time_data = linspace(chan_data[0], 
                                 chan_data[1], 
                                 int(chan_data[2]))
        
        # flag that channel is off or unavailable    
        except Exception as ex:
            time_data = False
            print(f"Channel {channel} unavailable! \
                  Please check connection\n")
            print('Exception raised: ' + ex)

        return time_data
    
    def save_channels(self):
        """
        Save given channel(s) data to file

        """
        start = time()
        time_data = self.query_time(self.channels[0])           # get time data                   
        headers = ['time (s)']
        cols = []
        for channel in self.channels:
            headers.append(f'C_{channel} (V)')                  # create headers for channels 
            data = self.query_data(channel)     
            while not self.query_opc():                         # ensure data is collected
                sleep(0.1)
            if data:
                cols.append(data)
        zipped = zip(time_data, *cols)                      
        self.write_file(zipped, field_headers=headers)          # save zipped data to file
        if self.verbose:
            print(f'file save in {time() - start}s')

    def save_history(self):
        """
        Save history data from the scope to file
        
        """
        try:
            for i in range(int(self.query_str(f'ACQ:AVA?'))):   # get total number of segments
                self.write_str(f'CHAN{self.channels[0]}:HIST:CURR {i+1}')   # bring next segement to screen
                self.opc_check()
                self.fname = f'{self.fname}{i+1}'               # create new file name for each segment
                self.save_channels()                            # save channels to file

        except Exception as ex:
            print('An error occured!' + ex.args[0])

    def screenshot(self):
        """
        Take and save screenshots on the scope
        
        """
        # ensure correct format for screenshot
        if self.screenshot_format not in ['png', 'bmp']:
             print(f"screenshot_format must be either \
                   'png' or 'bmp'\n Defaulting to 'png'")
             self.screenshot_format = 'png'
        try:
            # set internal path to save screenshot
            self.write_str(f'MMEM:CDIR "{self.instr_path}"')
            self.write_str(f'HCOP:FORM {self.screenshot_format}')   # set format for save file
            self.write_str(f'MMEM:NAME "{self.fname}"')             # set screenshot filename
            self.write_str('HCOP:IMM')                              # take the screenshot
            while not self.query_opc():                             # check for completion
                sleep(0.1)

            # transfer screenshot to pc at desired path
            save_file = self.check_file_exists(self.screenshot_format)
            self.read_file_from_instrument_to_pc(f'{self.instr_path}{self.fname}.{self.screenshot_format}',
                                                    f'{save_file}')
            if self.verbose:
                print(f'Screenshot successful! File {self.fname}.{self.file_format} \
                      saved.')
            # remove screenshot from the scope to save memory
            self.write_str(f'MMEM:DEL "{self.fname}.{self.screenshot_format}"')

        except Exception as ex:
            print('Error occured while taking the screenshot' + ex.args[0])
            return False
            
        return True

    def write_file(self,
                   channel_data,
                   field_headers=None,
                   ):
        """
        Save given channel data to csv

        Parameters
        ----------

        channel_data: zip
            Zipped data from each channel you wish to save
        field_headers: list
            optional - list of column names

        """
        # check if file already exists
        save_file = self.check_file_exists(self.file_format)
        # write to file using csv.writer method from CSV package
        with open(save_file, 'w', newline='') as f:
            write = csv.writer(f, delimiter=',')
            
            if field_headers:                                   # save headers if available
                write.writerow(field_headers)
            write.writerows(channel_data)                       # write column data to file
        
        if self.verbose:
            print(f'Save successful! File \
                  {self.fname}.{self.file_format} \
                    saved in {self.path}.')