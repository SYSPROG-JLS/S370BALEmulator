# 
# This file is part of the S370BALEmulator distribution.
# Copyright (c) 2021 James Salvino.
# 
# This program is free software: you can redistribute it and/or modify  
# it under the terms of the GNU General Public License as published by  
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful, but 
# WITHOUT ANY WARRANTY; without even the implied warranty of 
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU 
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License 
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#

S370BALEmulator README
07/09/2021

- purpose: to emulate the 94 problem-state IBM S/370 Basic Assembly Language (BAL) instructions
           to teach IBM S/370 Basic Assembly Language (BAL) programming
           to provide an interactive debugging environment for the IBM S/370 Basic Assembly Language (BAL)
           to run programs written in IBM S/370 Basic Assembly Language (BAL) on your PC

- you need to have an IBM S/370 Basic Assembly Language (BAL) assembler 
    + you can use IFOX00 in MVS3.8J running under Hercules 
    + or you can use the Z390 Portable Mainframe Assembler and Emulator from Automated Software Tools Corporation (Copyright 
    2011-13 Automated Software Tools Corporation)
    + or you can use S370BALAsm (my assembler) found at https://github.com/SYSPROG-JLS/S370BALAsm

- written for Python V3+
    See https://www.python.org/downloads/ for instructions for downloading
    and installing Python on your PC or Mac
    
    The curses package is required by the S370BALEmulator.
    This package comes with the Python standard library. 
    In Linux and Mac, the curses dependencies should already be 
    installed so there is no extra steps needed.
 
    On Windows, you need to install one special Python 
    package, windows-curses available on PyPI to add support.

    # Needed in Windows only
    python -m pip install windows-curses

    You can verify everything works by running a Python interpreter 
    and attempting to import curses. If you do not get any errors, you 
    are in good shape.

    >>> import curses
    >>>

- how to run:
    python S370BALEmulator            -  run the emulator in non-interative mode
    python S370BALEmulator -debug     -  run the emulator in interactive debug mode
    
    Running in interactive debug mode brings up the terminal user interface to
    display reqisters, memory, and allow you to set breakpoints, etc.

- S370BALEmulator.py requires 3 Python data structures in your current
    working directory:
     . instrdata.p
     . sourcecode.p
     . symdict.p 

  The pre-processing involves creating the source code dictionary (sourcecode.p),
  the symbol dictionary of variable names from the listing file (symdict.p) and 
  the main storage file (instrdata.p) consisting of BAL instructions
  and data areas from the object file.

  The 3 data structures (source_code_dict, symdict, and instrdata)
  are pickeled and written out to the current working directory
  for later use by S370BALEmulator.py (the S/370 BAL Emulator).

- The following Python pre-processor programs are included to
  create the required data structures:

  . Z390-ProcessPRN_OBJ.py
     This program reads in and processes a .PRN and .OBJ file produced 
     by the Z390 Portable Mainframe Assembler and Emulator (Copyright 
     2011-13 Automated Software Tools Corporation). The following lines 
     of code need to be changed for your path: 
              prnfile = open('C:\\MyZ390\\' + fname + '.PRN','r')
              objfile = open('C:\\MyZ390\\' + fname + '.OBJ','rb')

  . MVS38J-ProcessPRN_OBJ.py
     This program reads in and processes a SYSPRINT Listing and OBJECT file produced 
     by the MVS3.8J Assembler (IFOX00). The following lines of code need to be 
     changed for your path: 
              prnfile = open('C:\\MyPython\\' + fname + '.txt','r')
              objfile = open('C:\\MyPython\\' + fname + '.OBJ','rb')

     Here is the sample JCL:

     //ASM      JOB  (001),'ASSEM PGM',                                 
     //             CLASS=A,MSGCLASS=H,MSGLEVEL=(1,1),REGION=756K
     //*--------------------------------------------------------------------
     //ASMF     EXEC PGM=IFOX00,PARM=(LIST,XREF,DECK),REGION=2048K
     //SYSLIB    DD DSN=SYS1.AMODGEN,DISP=SHR
     //          DD DSN=SYS1.AMACLIB,DISP=SHR
     //SYSUT1    DD DISP=(NEW,DELETE),SPACE=(1700,(900,100)),UNIT=SYSDA
     //SYSUT2    DD DISP=(NEW,DELETE),SPACE=(1700,(600,100)),UNIT=SYSDA
     //SYSUT3    DD DISP=(NEW,DELETE),SPACE=(1700,(600,100)),UNIT=SYSDA
     //SYSPRINT  DD DSN=HMVS01.LIST(EMUTEST),DISP=SHR
     //SYSPUNCH  DD DSN=HMVS01.OBJ(EMUTEST),DISP=SHR
     //SYSIN     DD *
      ** source code here **
     /*
     //*-------------------------------------------------------------------
     //

     Following a successful assembly 'HMVS01.LIST(EMUTEST)' and 'HMVS01.OBJ(EMUTEST)'
     are transferred to the PC using IND$FILE as EMUTEST.txt and EMUTEST.OBJ
     respectively.

  . If you are using another Assembler, please refer to 'Z390-ProcessPRN_OBJ.py'
    and 'MVS38J-ProcessPRN_OBJ.py' for example code to aid you in writing your
    own pre-processor.
    
  . If you are using my assembler (S370BALAsm), the 3 required data structures 
    (source_code_dict, symdict, and instrdata) are created in the current working directory
    during the assembly and no further pre-processing is required. Again
    my assembler can be found at https://github.com/SYSPROG-JLS/S370BALAsm

-------------------------------------------------------------------------------

Interactive Debugger Commands:

Note:
Any address below is in form of a string of 1-6 hex digits.
Addresses are taken directly from the assembler listing. 
If a certain instruction that you want to trace is assembled at
address 00000C, then that is the address you use -there is no 
need to add a load point.

. single step (s) command - format:  s
. go (g) command - format:  g
. set execution delay (sd) command - format:  sd delay_in_ms
. set breakpoint (sb) command - format:  sb breakpoint_address_to_stop_at
. clear breakpoint (cb) command - format:  cb breakpoint_address_to_clear -or- cb ALL
. display breakpoints (db) command - format:  db
. display memory (dm) command - format:  dm start_address_to_display num_of_bytes(dec)
. display field (df) command - format:  df valid_field_name (valid_field_name is a data area defined by a DS or DC 
                                                           and is a key in the symbol_dict dictionary)
Note:
the go (g) command is normally used after setting 1 or more breakpoints 

-------------------------------------------------------------------------------
Notes on my user written Supervisor Call (SVC) numbers:

Note: S370BALEmulator ONLY recognizes the following user-defined SVC numbers. None of the 
usual IBM SVC numbers are emulated. 

 255:   print alphanumeric data to terminal (register 0 points to data; register 1 is the data length)

 254:   print contents of register 0 to terminal as signed integer
 
 253:   print contents of register 0 to terminal as 4 byte hex string

 252:   print contents of the cond_code python list

 251:   print the contents of the regs python list

 250:   sleep for x ms  (register 0 is loaded with the number of ms to sleep)

 249:   open PC file (in theory up to 100 files can be open at once)
          . register 0 points to file name to open
          . register 1 byte 0 = file handle number; byte 1 = r/w indicator; bytes 2-3 = file name length
          . 00 - 99 file handle number (decimal only)
          . 00 = open for read; 01 = open for write 

 248:   close PC file
          . register 1 byte 0 = file handle number
          . 00 - 99 file handle number (decimal only)

 247:   get record from PC file
          . register 1 byte 0 = file handle number
          . 00 - 99 file handle number (decimal only)
          . at exit, register 15 is loaded with the length of the record read 
          . a record length of 0 indicates an EOF condition
          . register 0 points to data area

 246:   put record to PC file
          . register 0 points to data
          . register 1 byte 0 = file handle number; bytes 2-3 = the data length
          . 00 - 99 file handle number (decimal only)


Important Notes: 1) It is easy to add your own SVC routines to do anything you like. 
                 2) SVCs 254 - 251 do not display their output immediately in interactive
                    debug mode (it is queued up due to ncurses). If you are running
                    under Windows, only after the program ends will you see the output.
                    If you are running under Linux, the output gets lost (need to research).

------------------------------------------------------------------------------
