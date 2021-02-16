# 
# This file is part of the S370BALEmulator distribution (https://github.com/xxxx or http://xxx.github.io).
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

#This program reads in and processes a SYSPRINT Listing and OBJECT file produced 
#by the MVS3.8J Assembler (IFOX00). Here is the JCL:
#
#//ASM      JOB  (001),'ASSEM PGM',                                 
#//             CLASS=A,MSGCLASS=H,MSGLEVEL=(1,1),REGION=756K
#//*--------------------------------------------------------------------
#//ASMF     EXEC PGM=IFOX00,PARM=(LIST,XREF,DECK),REGION=2048K
#//SYSLIB    DD DSN=SYS1.AMODGEN,DISP=SHR
#//          DD DSN=SYS1.AMACLIB,DISP=SHR
#//SYSUT1    DD DISP=(NEW,DELETE),SPACE=(1700,(900,100)),UNIT=SYSDA
#//SYSUT2    DD DISP=(NEW,DELETE),SPACE=(1700,(600,100)),UNIT=SYSDA
#//SYSUT3    DD DISP=(NEW,DELETE),SPACE=(1700,(600,100)),UNIT=SYSDA
#//SYSPRINT  DD DSN=HMVS01.LIST(EMUTEST),DISP=SHR
#//SYSPUNCH  DD DSN=HMVS01.OBJ(EMUTEST),DISP=SHR
#//SYSIN     DD *
# ** source code here **
#/*
#//*-------------------------------------------------------------------
#//

#Following a successful assembly 'HMVS01.LIST(EMUTEST)' and 'HMVS01.OBJ(EMUTEST)'
#are transferred to the PC using IND$FILE as EMUTEST.txt and EMUTEST.OBJ
#respectively.

#The processing involves creating a source code dictionary
#and a symbol dictionary of variable names from the listing file and a 
#main storage file (called instrdata) consisting of BAL instructions
#and data areas from the object file.

#The 3 data structures (source_code_dict, symdict, and instrdata)
#are pickeled and written out to the current working directory
#for later use by S370BALEmulator.py (the S/370 BAL Emulator).

import sys
import pickle

fname = sys.argv[1]

#read in the listing file and build the symbol and source code dictionaries  
symdict = {}
source_code_dict = {}

prnfile = open('C:\\MyPython\\' + fname + '.txt','r')
prnlines = prnfile.readlines()

#build the source code dictionary
for line in prnlines:
    try:
        t = int(line[1:7],16)   #are col 2-7 valid hex digits
        if line[8] in '0123456789ABCDEF' and ' DC ' not in line:
                source_code_dict[line[1:7]] = line[41:].rstrip('\n')
    except ValueError:
        pass
        
#build the symbol dictionary
got_xref_sw = False
for line in prnlines:
    if 'ASSEMBLER DIAGNOSTICS AND STATISTICS' in line:
        break
    if got_xref_sw:
        sym = line[1:9]
        symloc = line[16:24]
        symlen = line[10:15].rjust(8,'0')
        symdict[sym] = (symloc, symlen)
    if 'SYMBOL    LEN   VALUE   DEFN    REFERENCES' in line:
        got_xref_sw = True
            
#get rid of EQUs and LABELS from the symbol dictionary
symlist = list(symdict.keys())        
for line in prnlines:
    if line[41:49] in symlist:
        if ' DC ' in line or ' DS ' in line:
            continue
        else:
            del symdict[line[41:49]]

prnfile.close()

print(symdict)
print(' ')

pickle.dump( symdict, open( "symdict.p", "wb" ) )
#symdict = pickle.load( open( "symdict.p", "rb" ) )

print(source_code_dict)
print(' ')

pickle.dump( source_code_dict, open( "sourcecode.p", "wb" ) )
#source_code_dict = pickle.load( open( "sourcecode.p", "rb" ) )

#read in the OBJ code file
objfile = open('C:\\MyPython\\' + fname + '.OBJ','rb')
objbytes = objfile.read()
objfile.close()

#convert each byte in the obj code file to a 2 char hex string representation 
objstr = ''.join([hex(b).split('0x')[1].zfill(2).upper() for b in objbytes])

#split on '.TXT '
TXTlist = objstr.split('02E3E7E340')

#build the instruction/data array from the TXT records
address_int_prev = -1
txtlen_prev = 1
instrdata = []

for txt in TXTlist[1:]:
    address = '0x' + txt[0:6]
    address_int = eval('int(' + address + ')')
    txtlen = eval('int(0x' + txt[10:14] + ')')
    
    # pad instrdata where alignment on double, full, or half 
    # word boundary pushes address higher
    delta = address_int - (address_int_prev + txtlen_prev)
    if delta > 0:      
        for i in range(0,delta):
            instrdata.append('00')

    print(address + ':  ', end="")
    i = 0
    for t in range(22,txtlen*2+22,2):
        print(txt[t] + txt[t+1] + ' ', end="")
        # this code handles an ORG as used when building a lookup table
        if address_int > address_int_prev:
            instrdata.append(txt[t] + txt[t+1])
        else:
            instrdata[address_int + i] = txt[t] + txt[t+1]
            i = i + 1
    print(' ')
    address_int_prev = address_int
    txtlen_prev = txtlen
    
print(' ')

# print out the instrdata following load & cleanup
i = 0
print('0x' + hex(i)[2:].zfill(6).upper() + ': ', end="")

for b in instrdata:
    print(b + ' ', end="")
    i = i + 1
    if i % 16 == 0:
        print(' ')
        print('0x' + hex(i)[2:].zfill(6).upper() + ': ', end="")
        
print(' ')

pickle.dump( instrdata, open( "instrdata.p", "wb" ) )  
#instrdata = pickle.load( open( "instrdata.p", "rb" ) )
 
exit()