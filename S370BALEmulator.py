# 
# This file is part of the XXX distribution (https://github.com/xxxx or http://xxx.github.io).
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

import sys
import pickle
import curses

#unpickle the source code dictionary 
source_code_dict = pickle.load( open( "sourcecode.p", "rb" ) )

#unpickle the symbol dictionary 
symbol_dict = pickle.load( open( "symdict.p", "rb" ) )

#unpickle the instructions and data list 
instrdata_list = pickle.load( open( "instrdata.p", "rb" ) )


# Here is a sample program to emulate / debug: 
#
# source_code_dict = {'000000': '         BALR  R12,0', 
#                     '000002': '         LA    R3,AREA1', 
#                     '000006': '         LA    R4,4', 
#                     '00000A': "LOOP     MVI   0(R3),C'0'", 
#                     '00000E': '         LA    R3,1(R3)', 
#                     '000012': '         BCT   R4,LOOP', 
#                     '000016': '         LA    R15,0', 
#                     '00001A': '         BR    R14'}
#
# symbol_dict = {'AREA1   ': ('0000001C', '00000004')}
#
# instrdata_list =
# 000000 ['05', 'C0',             |          BALR  R12,0 
# 000002                          |          USING *,R12
# 000002  '41', '30', 'C0', '1A', |          LA    R3,AREA1
# 000006  '41', '40', '00', '04', |          LA    R4,4
# 00000A  '92', 'F0', '30', '00', | LOOP     MVI   0(R3),C'0'
# 00000E  '41', '33', '00', '01', |          LA    R3,1(R3)
# 000012  '46', '40', 'C0', '08', |          BCT   R4,LOOP
# 000016  '41', 'F0', '00', '00', |          LA    R15,0
# 00001A  '07', 'FE',             |          BR    R14
# 00001C  'FF', 'FF', 'FF', 'FF'] | AREA1    DC    XL4'FFFFFFFF'
#
# The 3 data structures: source_code_dict, symbol_dict and instrdata_list
# are created in Z390-ProcessPRN_OBJ.py or MVS38J-ProcessPRN_OBJ.py.
# They are created from the TXT object deck and its assembler listing PRN file 
# produced from the Z390 Portable Mainframe Assembler and Emulator 
# (Copyright 2011-13 Automated Software Tools Corporation) or the MVS 3.8J assembler.
#
# Notes:
#
# addresses are represented as positive integers in a register
# all other values in registers are represented as 4 byte hex strings or signed integers
# depending on what instruction last operated on the register

#
# 31 bit signed integers represented as follows:
# 80 00 00 00 (-2,147,483,648) ---> 00 00 00 00 (zero) ---> 7F FF FF FF (+2,147,483,647)
# negative numbers are represented in two's complement form
# if the sum/difference/product > ABS(2,147,483,647) then overflow
#

regs = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, '000EEEEE', 15]

# Important:
#R14 is set initially to 0x0EEEEE' (978,670 dec) as the return address. 
#If you plan to use R14, then you must save R14 and restore it before a 
#'BR     14' is performed to exit this program and return control to the OS 

cond_code = ['0','0','0','0']
 
program_counter = 0 

save_program_counter = 0

Execute_list = []

Debug = False

term_output = ''

# Process Command Line parameters
#  -debug  enables the interactive Curses-based debugger
if len(sys.argv)-1 > 0:
    if '-debug' in sys.argv:
        Debug = True

# Important:
# A zero in any of the X2, B1, or B2 fields indicates
# the absence of the corresponding address component.
# For the absent component, a zero is used in
# forming the address, regardless of the contents of
# general register 0. A displacement of zero has no
# special significance.

#Calculate an integer address - D(X,B) or D(B) 
def calc_address(B, D, X=0):
    addr = D
    
    if X != 0:
        addr = addr + cast_to_type(regs[X],int)
            
    if B != 0:
        addr = addr + cast_to_type(regs[B],int)
            
    return addr


#Convert 8, 4 or 2 byte hex string in two's complement format to a negative signed integer
def cvt2scomp(x):
    #x in format: 'FFFFFFFFFFFFFFFD' (doubleword) or 'FFFFFFFD' (fullword) or 'FFFD' (halfword)
    #convert x to binary string
    b = bin(int(x,16))[2:]
    if len(b) == 16:
        b = b[0]*16 + b   #expand halfword by propagating the leftmost (sign) bit 16 positions to the left.
    #flip the bits in b creating num1 
    num1 = ''
    for bit in b:
        if bit == '0':
            num1 = num1 + '1'
        else:
            num1 = num1 + '0'
    return (int(num1,2) + int('0001',2)) * -1   #note: the 2 indicates base 2


#Convert a 8, 4 or 2 byte hex string to a signed integer
def cvthex2int(x):
    #interogate 1st byte to see if string represents a two's complement neg integer
    if x[0] in '8ABCDEF':
        return cvt2scomp(x)
    else:
        return int(x,16)    #note: the 16 indicates base 16


#Convert a negative signed integer to a 4 or 8 byte hex string in two's complement format
def cvtint2scomp(x, numb=32):
    t = bin(x)[3:]
    b = '0'*(numb-len(t)) + t   #expand by propagating a '0' out to 32 or 64 bits
    #flip the bits in b creating num1 
    num1 = ''
    for bit in b:
        if bit == '0':
            num1 = num1 + '1'
        else:
            num1 = num1 + '0'
    return hex(int(num1,2) + int('0001',2))[2:].upper()


#Convert a signed integer to a 4 byte hex string 
def cvtint2hex(x):
    if x < 0:
        return cvtint2scomp(x)
    else:
        return hex(x).lstrip('0x').rjust(8,'0').upper()

        
#Convert integer to packed decimal
def cvtint2pdec(i, pdlen):
    str_i = str(i)    
    if str_i[0] == '-':
        sign = 'D'
        str_i = str_i[1:]
    else:
        sign = 'C'
    return str_i.rjust(pdlen-1,'0') + sign
    
    
#Convert packed decimal to integer
def cvtpdec2int(pd):
    pd_len = len(pd)
    if pd.endswith(('A','C','E','F')):
        sign = '+'
    elif pd.endswith(('B','D')):
        sign = '-'
    else:
        print('cvtpdec2int: Invalid Sign')
    digits = pd[0:pd_len-1]
    return int(sign + digits)


#Convert from 8, 4 or 2 byte hex string to a signed integer
#or convert a signed integer to a 4 byte hex string 
#depending on the desired type
def cast_to_type(x, desired_type):
    if isinstance(x, desired_type):
        return x
    else:
        if desired_type == int:
            return cvthex2int(x)
        elif desired_type == str:
            return cvtint2hex(x)
        else:
            print('Invalid desired_type')


#Add / Add Halfword / Add Register code
#Subtract / Subtract Halfword / Subtract Register code
def Add_Sub_code(numb, AorS):
    global regs, cond_code
    
    cond_code = ['0','0','0','0']   #clear condition code

    op1 = cast_to_type(regs[_R1],int)
        
    if numb != 0: 
        addr = calc_address(_B2, _D2, _X2)
        op2 = cvthex2int(''.join(instrdata_list[addr:addr+numb]))
    else:
        op2 = cast_to_type(regs[_R2],int)
            
    if AorS == '+':
        op1 = op1 + op2
    elif AorS == '-':
        op1 = op1 - op2
    
    if abs(op1) > 2147483647:
        cond_code[3] = '1'
    elif op1 == 0:
        cond_code[0] = '1'
    elif op1 < 0:
        cond_code[1] = '1'
    elif op1 > 0:
        cond_code[2] = '1'
        
    regs[_R1] = cvtint2hex(op1)
    
    return


#Add Logical / Add Logical Register code
#Subtract Logical / Subtract Logical Register code
def Add_Sub_Logical_code(numb, AorS):
    global regs, cond_code
    
    cond_code = ['0','0','0','0']   #clear condition code

    op1 = cast_to_type(regs[_R1],int)
        
    if numb != 0: 
        addr = calc_address(_B2, _D2, _X2)
        op2 = cvthex2int(''.join(instrdata_list[addr:addr+numb]))
    else:
        op2 = cast_to_type(regs[_R2],int)
            
    if AorS == '+':
        with_carry = False
        if op2 < 0:
            with_carry = True
    else:        
        with_carry = True
        if op2 < 0:
            with_carry = False
            
    if AorS == '+':
        op1 = op1 + op2
    elif AorS == '-':
        op1 = op1 - op2
        
    result_is_zero = False
    if op1 == 0:
        result_is_zero = True

    if AorS == '+':
        if (not result_is_zero) and with_carry:
            cond_code = ['0','0','0','1']
        elif result_is_zero and with_carry:
            cond_code = ['0','0','1','0']
        elif (not result_is_zero) and (not with_carry):
            cond_code = ['0','1','0','0']
        elif result_is_zero and (not with_carry):
            cond_code = ['1','0','0','0']

    if AorS == '-':
        if (not result_is_zero) and with_carry:
            cond_code = ['0','0','0','1']
        elif result_is_zero and with_carry:
            cond_code = ['0','0','1','0']
        elif (not result_is_zero) and (not with_carry):
            cond_code = ['0','1','0','0']
            
    regs[_R1] = cvtint2hex(op1)
    
    return


#Compare / Compare Halfword / Compare Register
def Compare_code(numb):
    global cond_code
    
    cond_code = ['0','0','0','0']   #clear condition code

    op1 = cast_to_type(regs[_R1],int)
        
    if numb != 0:
        addr = calc_address(_B2, _D2, _X2)
        op2 = cvthex2int(''.join(instrdata_list[addr:addr+numb]))
    else:
        op2 = cast_to_type(regs[_R2],int)

    if op1 == op2:
        cond_code[0] = '1'
    elif op1 < op2:
        cond_code[1] = '1'
    elif op1 > op2:
        cond_code[2] = '1'
    
    return


#Compare Logical / Compare Logical Immediate / Compare Logical Characters / Compare Logical Register
def Compare_Logical_code(fmt):
    global cond_code
    
    cond_code = ['1','0','0','0']   #assume equal until proven otherwise
    
    numb = 4
    
    if fmt.startswith('R'):
        op1 = cast_to_type(regs[_R1],str)
    if fmt == 'RR':
        op2 = cast_to_type(regs[_R2],str)
    elif fmt == 'RX':
        addr = calc_address(_B2, _D2, _X2)
        op2 = ''.join(instrdata_list[addr:addr+numb])
    elif fmt == 'SI':
        op1 = instrdata_list[calc_address(_B1, _D1)]
        op2 = _I2
        numb = 1
    elif fmt == 'SS':
        addr1 = calc_address(_B1, _D1)
        addr2 = calc_address(_B3, _D3)
        numb = _LL + 1
        op1 = ''.join(instrdata_list[addr1:addr1+numb])
        op2 = ''.join(instrdata_list[addr2:addr2+numb])
        
    for i in range(0,numb*2,2):
        field1 = int(op1[i:i+2],16)
        field2 = int(op2[i:i+2],16)
            
        if field1 == field2:
            continue
        elif field1 < field2:
            cond_code[0] = '0'
            cond_code[1] = '1'
            break
        elif field1 > field2:
            cond_code[0] = '0'
            cond_code[2] = '1'
            break
            
    return

    
#Store / Store Character / Store Halfword    
def Store_code(numb):
    global instrdata_list
    
    dest = calc_address(_B2, _D2, _X2)

    op1 = cast_to_type(regs[_R1],str)
    
    if numb == 4 or numb == 2:
        if numb == 4:
            j = 0
        else:
            j = 4
        for i in range(0,numb):
            instrdata_list[dest + i] = op1[j:j+2]
            j = j + 2
    elif numb == 1:
        instrdata_list[dest] = op1[6:8]

    return


#AND / AND Character / AND Immediate / AND Register
#OR / OR Character / OR Immediate / OR Register
#XOR / XOR Character / XOR Immediate / XOR Register    
def And_Or_Xor_code(fmt, op):
    global cond_code
    
    cond_code = ['1','0','0','0']   #assume result is zero until proven otherwise
    
    numb = 4
    
    if fmt.startswith('R'):
        op1 = cast_to_type(regs[_R1],str)
    if fmt == 'RR':
        op2 = cast_to_type(regs[_R2],str)
    elif fmt == 'RX':
        addr = calc_address(_B2, _D2, _X2)
        op2 = ''.join(instrdata_list[addr:addr+numb])
    elif fmt == 'SI':
        op1 = instrdata_list[calc_address(_B1, _D1)]
        op2 = _I2
        numb = 1
    elif fmt == 'SS':
        addr1 = calc_address(_B1, _D1)
        addr2 = calc_address(_B3, _D3)
        numb = _LL + 1
        op1 = ''.join(instrdata_list[addr1:addr1+numb])
        op2 = ''.join(instrdata_list[addr2:addr2+numb])

    result = ''
    not_zero = False
    for i in range(0,numb*2,2):
        t = hex(eval('0x' + op1[i:i+2] + op + '0x' + op2[i:i+2]))[2:].zfill(2).upper()
        if t != '00':
            not_zero = True
        result = result + t

    if not_zero:
        cond_code[0] = '0'
        cond_code[1] = '1'

    if fmt.startswith('R'):
        regs[_R1] = result
    elif fmt == 'SI':
        instrdata_list[calc_address(_B1, _D1)] = result
    elif fmt == 'SS':
        z = 0
        for i in range(0,numb*2,2):
            instrdata_list[addr1+z] = result[i:i+2]
            z = z + 1

    return
    
    
#AP / SP / MP / ZAP
def Add_Sub_Mul_Packed_code(op):
    global instrdata_list, cond_code

    addr1 = calc_address(_B1, _D1)
    numb1 = _L1 + 1
    if op != 'z':
        op1 = ''.join(instrdata_list[addr1:addr1+numb1])
        op1_int = cvtpdec2int(op1)

    addr2 = calc_address(_B3, _D3)
    numb2 = _L2 + 1
    op2 = ''.join(instrdata_list[addr2:addr2+numb2])    
    op2_int = cvtpdec2int(op2)

    if op == '+':
        op1_int = op1_int + op2_int
    elif op == '-':
        op1_int = op1_int - op2_int
    elif op == '*':
        op1_int = op1_int * op2_int    
    elif op == 'z':
        op1_int = 0 + op2_int
        
    #Set cond_code only for Add and Sub   
    #Note: Overflow is not detected    
    if op != '*':
        if op1_int == 0:
            cond_code = ['1','0','0','0']
        elif op1_int < 0:
            cond_code = ['0','1','0','0']
        elif op1_int > 0:
            cond_code = ['0','0','1','0']

    str_op1 = cvtint2pdec(op1_int,numb1*2)
    
    for i in range(0,numb1*2,2):
        instrdata_list[addr1] = str_op1[i:i+2]
        addr1 = addr1 + 1    
    
    return 


#D / DR
def Divide_code(fmt):
    global regs
    
    even_reg = _R1
    odd_reg = _R1 + 1

    op1_e = cast_to_type(regs[even_reg],str)
    op1_o = cast_to_type(regs[odd_reg],str)    
        
    dividend_is_positive = True
    divisor_is_positive = True
    
    if op1_e[0] in '8ABCDEF':
        #Handle a negative dividend
        dividend = cvt2scomp(op1_e + op1_o)
        dividend_is_positive = False
    else:
        #Handle a positve dividend
        dividend = int(op1_e + op1_o,16)
            
    if fmt == 'RR':
        divisor = cast_to_type(regs[_R2],int)
    elif fmt == 'RX':
        addr = calc_address(_B2, _D2, _X2)
        divisor = cvthex2int(''.join(instrdata_list[addr:addr+4]))

    if divisor < 0:
        divisor_is_positive = False
        
    quotient = abs(dividend) // abs(divisor)
    remainder = abs(dividend) % abs(divisor)
    
    if (dividend_is_positive and (not divisor_is_positive)) or ((not dividend_is_positive) and divisor_is_positive):
        quotient = quotient * -1
        
    if not dividend_is_positive:
        remainder = remainder * -1
            
    regs[even_reg] = cvtint2hex(remainder)
    regs[odd_reg] = cvtint2hex(quotient)
    
    return


#M / MR
def Multiply_code(fmt, numb):
    global regs
    
    even_reg = _R1
    odd_reg = _R1 + 1
    
    multiplicand = cast_to_type(regs[odd_reg],int)   
            
    if fmt == 'RR':
        multiplier = cast_to_type(regs[_R2],int)
    elif fmt == 'RX':
        addr = calc_address(_B2, _D2, _X2)
        multiplier = cvthex2int(''.join(instrdata_list[addr:addr+numb]))
        
    product = multiplicand * multiplier
    
    if product >= 0:
        #Handle a positve product
        p64 = hex(product).lstrip('0x').rjust(16,'0').upper()
    elif product < 0:
        #Handle a negative product
        p64 = cvtint2scomp(product, numb=64)

    regs[even_reg] = p64[0:8]
    regs[odd_reg] = p64[8:16]
    
    return

    
#BXH / BXLE    
def Branch_on_Index_code(HorLE):
    global regs
    
    op1 = cast_to_type(regs[_R1],int)
    
    #if op3 (R2) is even, then a register pair are used as the increment and the compare value
    if (_R2 % 2) == 0:
        op3_increment_reg = _R2
        op3_compare_reg = _R2 + 1
    #if op3 (R2) is odd, then a single register is used as both the increment and the compare value
    else:
        op3_increment_reg = _R2
        op3_compare_reg = _R2

    op3_increment_val = cast_to_type(regs[op3_increment_reg],int)

    op3_compare_val = cast_to_type(regs[op3_compare_reg],int)

    sum = op1 + op3_increment_val
    regs[_R1] = sum
    
    if HorLE == 'H':
        if (sum - op3_compare_val) <= 0:
            return program_counter + i_field_num_bytes
        else:
            return calc_address(_B2, _D2)
    elif HorLE == 'LE':
        if (sum - op3_compare_val) <= 0:
            return calc_address(_B2, _D2)
        else:
            return program_counter + i_field_num_bytes    


#ED / EDMK
def ED_EDMK_code(EDorEDMK):
    global regs, instrdata_list, cond_code

    pattern_addr = calc_address(_B1, _D1)
    pattern_len = _LL + 1
    pattern = instrdata_list[pattern_addr:pattern_addr+pattern_len]
    
    source_addr = calc_address(_B3, _D3)
    
    digit_selector = '20'
    sig_starter = '21'
    field_sep = '22'
    msg_char = "not in ['20','21','22']"
    sig_indicator = 'OFF'
    fill_char = pattern[0]
    last_field_digits = ''
    only_once_sw = True
    sav_pp = 0
    
    pp = 0    #pattern pointer
    si = 0    #source index
    sdp = 2   #source digit pointer

    while True:
        pp = pp + 1
        if pp == pattern_len:
            break
            
        if sdp == 2:
            source_byte = instrdata_list[source_addr+si]
            si = si + 1
            if source_byte[1] in 'ABCDEF':
                last_field_digits = last_field_digits + source_byte[0]
            else:
                last_field_digits = last_field_digits + source_byte
            sdp = 0
            if source_byte[1] in 'ACEF':
                plus_sign_in_low_order_sd = True
            else:
                plus_sign_in_low_order_sd = False
                
        source_digit = source_byte[sdp]
             
        if pattern[pp] == digit_selector and sig_indicator == 'OFF' and source_digit == '0':
            pattern[pp] = fill_char
            sig_indicator = 'OFF'
            sdp = sdp + 1
            
        elif pattern[pp] == digit_selector and sig_indicator == 'OFF' and source_digit > '0' and plus_sign_in_low_order_sd == False:
            pattern[pp] = 'F' + source_digit
            sig_indicator = 'ON'
            sdp = sdp + 1
            if only_once_sw:
                sav_pp = pp
                only_once_sw = False
            
        elif pattern[pp] == digit_selector and sig_indicator == 'OFF' and source_digit > '0' and plus_sign_in_low_order_sd == True:
            pattern[pp] = 'F' + source_digit
            sig_indicator = 'OFF'
            sdp = sdp + 1            
            
        elif pattern[pp] == digit_selector and sig_indicator == 'ON' and source_digit >= '0' and plus_sign_in_low_order_sd == False:
            pattern[pp] = 'F' + source_digit
            sig_indicator = 'ON'
            sdp = sdp + 1                        

        elif pattern[pp] == digit_selector and sig_indicator == 'ON' and source_digit >= '0' and plus_sign_in_low_order_sd == True:
            pattern[pp] = 'F' + source_digit
            sig_indicator = 'OFF'
            sdp = sdp + 1         

        elif pattern[pp] == sig_starter and sig_indicator == 'OFF' and source_digit == '0' and plus_sign_in_low_order_sd == False:
            pattern[pp] = fill_char
            sig_indicator = 'ON'
            sdp = sdp + 1         

        elif pattern[pp] == sig_starter and sig_indicator == 'OFF' and source_digit == '0' and plus_sign_in_low_order_sd == True:
            pattern[pp] = fill_char
            sig_indicator = 'OFF'
            sdp = sdp + 1         

        elif pattern[pp] == sig_starter and sig_indicator == 'OFF' and source_digit > '0' and plus_sign_in_low_order_sd == False:
            pattern[pp] = 'F' + source_digit
            sig_indicator = 'ON'
            sdp = sdp + 1         

        elif pattern[pp] == sig_starter and sig_indicator == 'OFF' and source_digit > '0' and plus_sign_in_low_order_sd == True:
            pattern[pp] = 'F' + source_digit
            sig_indicator = 'OFF'
            sdp = sdp + 1         

        elif pattern[pp] == sig_starter and sig_indicator == 'ON' and source_digit >= '0' and plus_sign_in_low_order_sd == False:
            pattern[pp] = 'F' + source_digit
            sig_indicator = 'ON'
            sdp = sdp + 1    

        elif pattern[pp] == sig_starter and sig_indicator == 'ON' and source_digit >= '0' and plus_sign_in_low_order_sd == True:
            pattern[pp] = 'F' + source_digit
            sig_indicator = 'OFF'
            sdp = sdp + 1    

        elif pattern[pp] == field_sep:
            pattern[pp] = fill_char
            sig_indicator = 'OFF'
            last_field_digits = ''

        elif pattern[pp] not in ['20','21','22']  and sig_indicator == 'OFF':
            pattern[pp] = fill_char
            sig_indicator = 'OFF'

        elif pattern[pp] not in ['20','21','22']  and sig_indicator == 'ON':
            #result char is the message char at pattern[pp]
            sig_indicator = 'ON'

    for i in range(0,pattern_len):
        instrdata_list[pattern_addr+i] = pattern[i]
        
    if last_field_digits.count('0') == len(last_field_digits):
        cond_code = ['1','0','0','0']
    elif plus_sign_in_low_order_sd:
        cond_code = ['0','0','1','0']
    else:
        cond_code = ['0','1','0','0']
        
    if EDorEDMK == 'EDMK':
        #for EDMK instruction - address of each first significant result 
        #character is recorded in general register 1    
        regs[1] = pattern_addr + sav_pp
        
    return

# -------------------------------------------------- #

#Add
def A():
    #OC,R1,X2,B2,D2
    Add_Sub_code(4, '+')
    
    return program_counter + i_field_num_bytes

    
#Add Halfword
def AH():
    #OC,R1,X2,B2,D2
    Add_Sub_code(2, '+')
    
    return program_counter + i_field_num_bytes


#Add Logical
def AL():
    #OC,R1,X2,B2,D2
    Add_Sub_Logical_code(4, '+')
    
    return program_counter + i_field_num_bytes


#Add Logical Register
def ALR():
    #OC,R1,R2
    Add_Sub_Logical_code(0, '+')
    
    return program_counter + i_field_num_bytes

        
#Add Register
def AR():
    #OC,R1,R2
    Add_Sub_code(0, '+')
    
    return program_counter + i_field_num_bytes
    

#Add Packed
def AP():
    #OC,L1,L2,B1,D1,B3,D3
    Add_Sub_Mul_Packed_code('+')
    
    return program_counter + i_field_num_bytes

    
#Branch and Link
def BAL():
    global regs
    #OC,R1,X2,B2,D2
    regs[_R1] = program_counter + i_field_num_bytes
    
    return calc_address(_B2, _D2, _X2)

    
#Branch and Link (Register)
def BALR():
    global regs
    #OC,R1,R2
    regs[_R1] = program_counter + i_field_num_bytes
    if _R2 == 0:
        return regs[_R1]
    else:
        return cast_to_type(regs[_R2],int)


#Branch on Condition
def BC():
    #OC,R1,X2,B2,D2
    _M1 = _R1   # _M1 = mask1
        
    if _M1 == 0xF:
        return calc_address(_B2, _D2, _X2)
    elif _M1 == 0x0:
        return program_counter + i_field_num_bytes
    else:
        mask = list(bin(_M1).lstrip('0b').rjust(4, '0'))
        for i in range(0,4):
            if mask[i] == '1' and (cond_code[i] == mask[i]):
                return calc_address(_B2, _D2, _X2)
                
    return program_counter + i_field_num_bytes

    
#Branch on Condition (Register)
def BCR():
    #OC,R1,R2   
    _M1 = _R1   # _M1 = mask1
    
    R2_int = cast_to_type(regs[_R2],int)
        
    if _M1 == 0xF:
        return R2_int
    elif _M1 == 0x0:
        return program_counter + i_field_num_bytes
    else:
        mask = list(bin(_M1).lstrip('0b').rjust(4,'0'))
        for i in range(0,4):
            if mask[i] == '1' and cond_code[i] == mask[i]:
                return R2_int
                
    return program_counter + i_field_num_bytes


#Branch on Count  
def BCT():
    global regs
    #OC,R1,X2,B2,D2
    regs[_R1] = cast_to_type(regs[_R1],int) - 1

    if regs[_R1] == 0:
        return program_counter + i_field_num_bytes
    else:
        return calc_address(_B2, _D2, _X2)
        
        
#Branch on Count Register
def BCTR():
    global regs
    #OC,R1,R2
    regs[_R1] = cast_to_type(regs[_R1],int) - 1

    if regs[_R1] == 0:
        return program_counter + i_field_num_bytes
    else:
        if _R2 == 0:
            return program_counter + i_field_num_bytes
        else:
            return cast_to_type(regs[_R2],int)


#Branch on Index High
def BXH():
    #OC,R1,R2,B2,D2
    
    return Branch_on_Index_code('H')
    
    
#Branch on Index Low or Equal
def BXLE():
    #OC,R1,R2,B2,D2
    
    return Branch_on_Index_code('LE')


#Compare
def C():
    #OC,R1,X2,B2,D2
    Compare_code(4)
    
    return program_counter + i_field_num_bytes


#Compare Halfword
def CH():
    #OC,R1,X2,B2,D2
    Compare_code(2)
    
    return program_counter + i_field_num_bytes


#Compare Logical
def CL():
    #OC,R1,X2,B2,D2
    Compare_Logical_code(i_format)
    
    return program_counter + i_field_num_bytes


#Compare Logical Characters
def CLC():
    #OC,LL,B1,D1,B3,D3
    Compare_Logical_code(i_format)
    
    return program_counter + i_field_num_bytes 


#Compare Logical Characters Long
def CLCL():
    global cond_code
    #OC,R1,R2
    
    if isinstance(regs[_R1],int):
        first_op_addr = int(cvtint2hex(regs[_R1])[2:],16)
    else:
        first_op_addr = int(regs[_R1][2:],16)

    if isinstance(regs[_R1+1],int):
        first_op_len = int(cvtint2hex(regs[_R1+1])[2:],16)
    else:
        first_op_len = int(regs[_R1+1][2:],16) 
        
    if isinstance(regs[_R2],int):
        secnd_op_addr = int(cvtint2hex(regs[_R2])[2:],16)
    else:
        secnd_op_addr = int(regs[_R2][2:],16) 
        
    t = cast_to_type(regs[_R2+1],str)
    pad_char = t[0:2]
    secnd_op_len = int(t[2:],16)     
    
    if first_op_len >= secnd_op_len:
        comp_len = first_op_len
    else:
        comp_len = secnd_op_len
        
    cond_code = ['1','0','0','0']    
    if first_op_len == 0 and secnd_op_len == 0:
        pass
    else:    
        op1 = instrdata_list[first_op_addr:first_op_addr+first_op_len]
        op2 = instrdata_list[secnd_op_addr:secnd_op_addr+secnd_op_len]

        while len(op1) > len(op2):
            op2.append(pad_char)
        while len(op2) > len(op1):
            op1.append(pad_char)

        for i in range(0,comp_len):
            if op1[i] != op2[i]:
                op1_int = int(op1[i],16)
                op2_int = int(op2[i],16)
                if op1_int < op2_int:
                    cond_code = ['0','1','0','0']
                else:
                    cond_code = ['0','0','1','0']
                break
 
    return program_counter + i_field_num_bytes 


#Compare Logical Immediate
def CLI():
    #OC,I2,B1,D1
    Compare_Logical_code(i_format)
    
    return program_counter + i_field_num_bytes
    
    
#Compare Logical under Mask
def CLM():
    #OC,R1,R2,B2,D2
    global cond_code

    cond_code = ['1','0','0','0']   #assume equal until proven otherwise

    _M3 = _R2
    
    mask = list(bin(_M3).lstrip('0b').rjust(4,'0'))
    numb = mask.count('1')
    
    if numb == 0:
        return program_counter + i_field_num_bytes 

    op1 = cast_to_type(regs[_R1],str)
   
    op1_list = [op1[i:i+2] for i in range(0,8,2)]   #make list of _R1 bytes
    
    addr = calc_address(_B2, _D2)    
    op2_list = instrdata_list[addr:addr+numb]   #make list storage bytes

    j = 0
    for i in range(0,4):
        if mask[i] == '1':
            field1 = int(op1_list[i],16)
            field2 = int(op2_list[j],16)
            j = j + 1            
            if field1 == field2:
                continue
            elif field1 < field2:
                cond_code[0] = '0'
                cond_code[1] = '1'
                break
            elif field1 > field2:
                cond_code[0] = '0'
                cond_code[2] = '1'
                break

    return program_counter + i_field_num_bytes 


#Compare Logical Register
def CLR():
    #OC,R1,R2
    Compare_Logical_code(i_format)
    
    return program_counter + i_field_num_bytes  


#Compared Packed
def CP():
    global cond_code
    #OC,L1,L2,B1,D1,B3,D3
    
    addr1 = calc_address(_B1, _D1)
    numb1 = _L1 + 1
    op1 = ''.join(instrdata_list[addr1:addr1+numb1])
    op1_int = cvtpdec2int(op1)

    addr2 = calc_address(_B3, _D3)
    numb2 = _L2 + 1
    op2 = ''.join(instrdata_list[addr2:addr2+numb2])    
    op2_int = cvtpdec2int(op2)

    if op1_int == op2_int:
        cond_code = ['1','0','0','0']
    elif op1_int < op2_int:
        cond_code = ['0','1','0','0']
    elif op1_int > op2_int:
        cond_code = ['0','0','1','0']

    return program_counter + i_field_num_bytes


#Compare Register
def CR():
    #OC,R1,R2
    Compare_code(0)
    
    return program_counter + i_field_num_bytes


#Compare and Swap
def CS():
    global regs, instrdata_list, cond_code
    #OC,R1,R2,B2,D2

    op1 = cast_to_type(regs[_R1],str)

    addr = calc_address(_B2, _D2)
    op2 = ''.join(instrdata_list[addr:addr+4])

    if op1 == op2:
        op3 = cast_to_type(regs[_R2],str)
        j = 0
        for i in range(0,4):
            instrdata_list[addr + i] = op3[j:j+2]
            j = j + 2
        cond_code = ['1','0','0','0']
    else:
        regs[_R1] = op2
        cond_code = ['0','1','0','0']
        
    return program_counter + i_field_num_bytes


#Compare Double and Swap
def CDS():
    global regs, instrdata_list, cond_code
    #OC,R1,R2,B2,D2

    op1_e = cast_to_type(regs[_R1],str)
    op1_o = cast_to_type(regs[_R1+1],str)

    op1 = op1_e + op1_o
    
    addr = calc_address(_B2, _D2)
    op2 = ''.join(instrdata_list[addr:addr+8])

    if op1 == op2:
        op3_e = cast_to_type(regs[_R2],str)
        op3_o = cast_to_type(regs[_R2+1],str)        

        op3 = op3_e + op3_o
        
        j = 0
        for i in range(0,8):
            instrdata_list[addr + i] = op3[j:j+2]
            j = j + 2
        cond_code = ['1','0','0','0']
    else:
        regs[_R1] = op2[0:8]
        regs[_R1+1] = op2[8:16]
        cond_code = ['0','1','0','0']
        
    return program_counter + i_field_num_bytes


#Convert to Binary
def CVB():
    #OC,R1,X2,B2,D2
    global regs
    
    addr = calc_address(_B2, _D2, _X2)
    op2 = ''.join(instrdata_list[addr:addr+8])

    op2_int = cvtpdec2int(op2)
    
    regs[_R1] = cvtint2hex(op2_int)
    
    return program_counter + i_field_num_bytes


#Convert to Decimal
def CVD():
    #OC,R1,X2,B2,D2
    global instrdata_list
    
    op1 = cast_to_type(regs[_R1],int)
    
    str_op1 = cvtint2pdec(op1, 16)

    addr = calc_address(_B2, _D2, _X2)

    for i in range(0,16,2):
        instrdata_list[addr] = str_op1[i:i+2]
        addr = addr + 1

    return program_counter + i_field_num_bytes


#Divide
def D():
    #OC,R1,X2,B2,D2
    Divide_code(i_format)
    
    return program_counter + i_field_num_bytes


#Divide Packed
def DP():
    global instrdata_list
    #OC,L1,L2,B1,D1,B3,D3
    
    addr1 = calc_address(_B1, _D1)
    numb1 = _L1 + 1
    op1 = ''.join(instrdata_list[addr1:addr1+numb1])
    dividend = cvtpdec2int(op1)

    addr2 = calc_address(_B3, _D3)
    numb2 = _L2 + 1
    op2 = ''.join(instrdata_list[addr2:addr2+numb2])    
    divisor = cvtpdec2int(op2)

    quotient = dividend // divisor
    remainder = dividend % divisor
    
    str_remainder = cvtint2pdec(remainder,numb2*2)
    str_quotient = cvtint2pdec(quotient,(numb1-numb2)*2)
    
    str_op1 =  str_quotient + str_remainder
    
    for i in range(0,numb1*2,2):
        instrdata_list[addr1] = str_op1[i:i+2]
        addr1 = addr1 + 1    
    
    return program_counter + i_field_num_bytes

    
#Divide Register
def DR():
    #OC,R1,R2
    Divide_code(i_format)
    
    return program_counter + i_field_num_bytes

    
#Edit
def ED():   
    #OC,LL,B1,D1,B3,D3
    ED_EDMK_code('ED')
    
    return program_counter + i_field_num_bytes

    
#Edit and Mark
def EDMK():   
    #OC,LL,B1,D1,B3,D3
    ED_EDMK_code('EDMK')
    
    return program_counter + i_field_num_bytes

    
#Insert Character
def IC():
    global regs
    #OC,R1,X2,B2,D2
    
    op1 = cast_to_type(regs[_R1],str)
    
    addr = calc_address(_B2, _D2, _X2)
    op2 = instrdata_list[addr]
    
    regs[_R1] = op1[0:6] + op2
    
    return program_counter + i_field_num_bytes


#Insert Character under Mask
def ICM():
    global regs, cond_code
        #OC,R1,R2,B2,D2
        
    cond_code = ['1','0','0','0']   #force cc to - All inserted bits are zeros, or mask is zero
    
# Note: NOT implementing cond_code setting at this time -    
#  "The resulting condition code is based on the mask
#  and on the value of the bits inserted. When the mask
#  is zero or when all inserted bits are zero, the condition
#  code is made O. When all inserted bits are not
#  zero, the code is set according to the leftmost bit of
#  the storage operand: if this bit is one, the code is
#  made 1 to indicate a negative algebraic value; if this
#  bit is zero, the code is made 2, reflecting a positive
#  algebraic value."    

    _M3 = _R2
    
    mask = list(bin(_M3).lstrip('0b').rjust(4,'0'))
    numb = mask.count('1')
    
    if numb == 0:
        return program_counter + i_field_num_bytes 
        
    op1 = cast_to_type(regs[_R1],str)    
        
    op1_list = [op1[i:i+2] for i in range(0,8,2)]  #make list of _R1 bytes

    addr = calc_address(_B2, _D2)    
    op2_list = instrdata_list[addr:addr+numb]   #make list storage bytes
    
    j = 0
    for i in range(0,4):
        if mask[i] == '1':
            op1_list[i] = op2_list[j]
            j = j + 1

    regs[_R1] = ''.join(op1_list)
    
    return program_counter + i_field_num_bytes


#Load
def L():
    global regs
    #OC,R1,X2,B2,D2  
    addr = calc_address(_B2, _D2, _X2)
    regs[_R1] = ''.join(instrdata_list[addr:addr+4])
        
    return program_counter + i_field_num_bytes
    
    
#Load Address
def LA():
    global regs
    #OC,R1,X2,B2,D2  
    regs[_R1] = calc_address(_B2, _D2, _X2)
        
    return program_counter + i_field_num_bytes


#Load Complement
def LCR():
    global regs, cond_code
    #OC,R1,R2
    
    op2 = cast_to_type(regs[_R2],int) * -1
        
    if op2 == 0:
        cond_code = ['1','0','0','0']    #Result is zero
    elif op2 < 0:
        cond_code = ['0','1','0','0']    #Result is less than zero
        if op2 == -2147483648:
            cond_code = ['0','0','0','1']    #Overflow
    elif op2 > 0:
        cond_code = ['0','0','1','0']    #Result is greater than zero
            
    regs[_R1] = op2
        
    return program_counter + i_field_num_bytes
    
    
#Load Halfword
def LH():
    global regs
    #OC,R1,X2,B2,D2  
    addr = calc_address(_B2, _D2, _X2)
    t = ''.join(instrdata_list[addr:addr+2])
    #extend halfword to fullword by propagating sign bit 
    if t[0] in '8ABCDEF':
        regs[_R1] = 'FFFF' + t
    else:
        regs[_R1] = '0000' + t
        
    return program_counter + i_field_num_bytes


#Load Multiple
def LM():
    global instrdata_list
    #OC,R1,R2,B2,D2
    
    addr = calc_address(_B2, _D2)
    
    starting_reg = _R1
    ending_reg = _R2
    
    j = starting_reg

    while True:
        regs[j] = cvthex2int(''.join(instrdata_list[addr:addr+4]))
        addr = addr + 4
        j = j + 1
        if j > 15:
            j = 0
        if j == ending_reg+1:
            break

    return program_counter + i_field_num_bytes    


#Load Negative
def LNR():
    global regs, cond_code
    #OC,R1,R2
    
    op2 = cast_to_type(regs[_R2],int)
        
    if op2 == 0:
        regs[_R1] = op2
        cond_code = ['1','0','0','0']   #Result is zero
    elif op2 < 0:
        regs[_R1] = op2
        cond_code = ['0','1','0','0']   #Result is less than zero
    elif op2 > 0:
        regs[_R1] = op2 * -1
        
    return program_counter + i_field_num_bytes


#Load Positive
def LPR():
    global regs, cond_code
    #OC,R1,R2
    
    op2 = cast_to_type(regs[_R2],int)
        
    if op2 == 0:
        regs[_R1] = op2
        cond_code = ['1','0','0','0']   #Result is zero
    elif op2 > 0:
        regs[_R1] = op2
        cond_code = ['0','0','1','0']   #Result is greater than zero
    elif op2 < 0:
        if op2 == -2147483648:
            cond_code = ['0','0','0','1']    #Overflow
        regs[_R1] = op2 * -1
        
    return program_counter + i_field_num_bytes
    

#Load (Register)
def LR():
    global regs
    #OC,R1,R2
    regs[_R1] = regs[_R2]
        
    return program_counter + i_field_num_bytes


#Load and Test Register
def LTR():
    global regs, cond_code
    #OC,R1,R2
    if _R1 != _R2:
        regs[_R1] = regs[_R2]
        
    op1 = cast_to_type(regs[_R1],int)    
        
    if op1 == 0:
        cond_code = ['1','0','0','0']
    elif op1 < 0:
        cond_code = ['0','1','0','0']
    elif op1 > 0:
        cond_code = ['0','0','1','0'] 
        
    return program_counter + i_field_num_bytes


#Multiply
def M():
    #OC,R1,X2,B2,D2
    Multiply_code(i_format, 4)
    
    return program_counter + i_field_num_bytes

    
#Multiply halfword
def MH():
    global regs
    #OC,R1,X2,B2,D2
    
    multiplicand = cast_to_type(regs[_R1],int)
          
    addr = calc_address(_B2, _D2, _X2) 
    multiplier = cvthex2int(''.join(instrdata_list[addr:addr+2]))
        
    product = cvtint2hex(multiplicand * multiplier)
    
    regs[_R1] = product
    
    return program_counter + i_field_num_bytes

        
#Multiply Packed
def MP():
    #OC,L1,L2,B1,D1,B3,D3
    Add_Sub_Mul_Packed_code('*')
    
    return program_counter + i_field_num_bytes    

    
#Multiply Register
def MR():
    #OC,R1,R2
    Multiply_code(i_format, 4)
    
    return program_counter + i_field_num_bytes


#Move Characters
def MVC():
    global instrdata_list
    #OC,LL,B1,D1,B3,D3
    dest = calc_address(_B1, _D1)
    source = calc_address(_B3, _D3)
    for i in range(0,_LL+1):
        instrdata_list[dest+i] = instrdata_list[source+i]
    
    return program_counter + i_field_num_bytes   


#Move Long
def MVCL():
    global regs, instrdata_list, cond_code
    #OC,R1,R2
    
    if isinstance(regs[_R1],int):
        first_op_addr = int(cvtint2hex(regs[_R1])[2:],16)
    else:
        first_op_addr = int(regs[_R1][2:],16)

    if isinstance(regs[_R1+1],int):
        first_op_len = int(cvtint2hex(regs[_R1+1])[2:],16)
    else:
        first_op_len = int(regs[_R1+1][2:],16) 
        
    if isinstance(regs[_R2],int):
        secnd_op_addr = int(cvtint2hex(regs[_R2])[2:],16)
    else:
        secnd_op_addr = int(regs[_R2][2:],16) 
        
    t = cast_to_type(regs[_R2+1],str)
    pad_char = t[0:2]
    secnd_op_len = int(t[2:],16)
    
    if first_op_len == secnd_op_len:
        cond_code = ['1','0','0','0']
    elif first_op_len < secnd_op_len:
        cond_code = ['0','1','0','0']
    elif first_op_len > secnd_op_len:
        cond_code = ['0','0','1','0']
    #Note: No movement performed because of destructive overlap (cc = 3) not detected 

    i = 0
    j = first_op_len
    k = secnd_op_len
    while j > 0:
        if k < 1:
            instrdata_list[first_op_addr+i] = pad_char
        else:
            instrdata_list[first_op_addr+i] = instrdata_list[secnd_op_addr+i]
        i = i + 1
        j = j - 1
        k = k - 1
    
    regs[_R1] = first_op_addr + first_op_len
    regs[_R1+1] = 0
    regs[_R2] = secnd_op_addr + secnd_op_len
    regs[_R2+1] = 0

    return program_counter + i_field_num_bytes 

   
#Move Immediate
def MVI():
    global instrdata_list
    #OC,I2,B1,D1 
    instrdata_list[calc_address(_B1, _D1)] = _I2
    
    return program_counter + i_field_num_bytes


#Move Numerics
def MVN():
    global instrdata_list
    #OC,LL,B1,D1,B3,D3
    dest = calc_address(_B1, _D1)
    source = calc_address(_B3, _D3)
    for i in range(0,_LL+1):
        instrdata_list[dest+i] = instrdata_list[dest+i][0] + instrdata_list[source+i][1]
    
    return program_counter + i_field_num_bytes   


#Move Offset
def MVO():
    global instrdata_list
    #OC,L1,L2,B1,D1,B3,D3
    dest = calc_address(_B1, _D1)
    source = calc_address(_B3, _D3)
    sign_byte = instrdata_list[dest+_L1]
    t = ''.join(instrdata_list[source:source+_L2+1]) + sign_byte[1] 
    mvo_bytes = t.rjust((_L1+1)*2,'0')
    j = 0
    for i in range(0,_L1+1):
        instrdata_list[dest+i] = mvo_bytes[j:j+2]
        j = j + 2
    
    return program_counter + i_field_num_bytes   


#Move Zones
def MVZ():
    global instrdata_list
    #OC,LL,B1,D1,B3,D3
    dest = calc_address(_B1, _D1)
    source = calc_address(_B3, _D3)
    for i in range(0,_LL+1):
        instrdata_list[dest+i] =  instrdata_list[source+i][0] + instrdata_list[dest+i][1]
    
    return program_counter + i_field_num_bytes   
    
    
#AND
def N():
    #OC,R1,X2,B2,D2
    And_Or_Xor_code(i_format, ' & ')
    
    return program_counter + i_field_num_bytes


#AND Characters
def NC():
    #OC,LL,B1,D1,B3,D3
    And_Or_Xor_code(i_format, ' & ')
    
    return program_counter + i_field_num_bytes 


#AND Immediate
def NI():
    #OC,I2,B1,D1
    And_Or_Xor_code(i_format, ' & ')
    
    return program_counter + i_field_num_bytes


#AND Register
def NR():
    #OC,R1,R2
    And_Or_Xor_code(i_format, ' & ')
    
    return program_counter + i_field_num_bytes  


#OR
def O():
    #OC,R1,X2,B2,D2
    And_Or_Xor_code(i_format, ' | ')
    
    return program_counter + i_field_num_bytes


#OR Characters
def OC():
    #OC,LL,B1,D1,B3,D3
    And_Or_Xor_code(i_format, ' | ')
    
    return program_counter + i_field_num_bytes 


#OR Immediate
def OI():
    #OC,I2,B1,D1
    And_Or_Xor_code(i_format, ' | ')
    
    return program_counter + i_field_num_bytes


#OR Register
def OR():
    #OC,R1,R2
    And_Or_Xor_code(i_format, ' | ')
    
    return program_counter + i_field_num_bytes


#Pack
def PACK():
    global instrdata_list
    #OC,L1,L2,B1,D1,B3,D3
    
    addr1 = calc_address(_B1, _D1)
    numb1 = _L1 + 1

    addr2 = calc_address(_B3, _D3)
    numb2 = _L2 + 1
    
    op2 = ''.join(instrdata_list[addr2:addr2+numb2])    

    if op2[-2] == 'F' or op2[-2] == 'C':
        sign = 'C'  #positive number
    else:
        sign = 'D'  #negative number

    packed_result = (op2.replace('F','') + sign).rjust(numb1*2, '0')
    
    j = 0
    for i in range(0,numb1*2,2):
        instrdata_list[addr1+j] = packed_result[i:i+2]
        j = j + 1

    return program_counter + i_field_num_bytes    
    
    
#Subtract
def S():
    #OC,R1,X2,B2,D2
    Add_Sub_code(4, '-')
    
    return program_counter + i_field_num_bytes


#Subtract Halfword
def SH():
    #OC,R1,X2,B2,D2
    Add_Sub_code(2, '-')
    
    return program_counter + i_field_num_bytes


#Subtract Logical
def SL():
    #OC,R1,X2,B2,D2
    Add_Sub_Logical_code(4, '-')
    
    return program_counter + i_field_num_bytes


#Shift Left Single
def SLA():
    global regs, cond_code
    #OC,R1,X2,B2,D2
    
    op1 = cast_to_type(regs[_R1],str)
        
    b = bin(int(op1,16)).lstrip('0b').rjust(32,'0')
    
    sign_bit = b[0]
    numerics = b[1:]
   
    numerics_list = list(numerics)
    
    overflow = False
    
    for i in range(0,_D2):
        shifted_out_bit = numerics_list.pop(0)
        if shifted_out_bit != sign_bit:
            overflow = True
        numerics_list.append('0')
    
    numerics_list.insert(0, sign_bit)    #put the sign back
    
    regs[_R1] = hex(int(''.join(numerics_list),2)).lstrip('0x').rjust(8,'0').upper()
    result = cvthex2int(regs[_R1])
    
    if overflow:
        cond_code = ['0','0','0','1']
    elif result == 0:
        cond_code = ['1','0','0','0']
    elif result < 0:
        cond_code = ['0','1','0','0']
    elif result > 0:
        cond_code = ['0','0','1','0']
        
    return program_counter + i_field_num_bytes


#Shift Left Double
def SLDA():
    global regs, cond_code
    #OC,R1,X2,B2,D2

    even_reg = _R1
    odd_reg = _R1 + 1
    
    op1_e = cast_to_type(regs[even_reg],str)
    op1_o = cast_to_type(regs[odd_reg],str)    
        
    b = bin(int(op1_e + op1_o,16)).lstrip('0b').rjust(64,'0')
    
    sign_bit = b[0]
    numerics = b[1:]
   
    numerics_list = list(numerics)
    
    overflow = False
    
    for i in range(0,_D2):
        shifted_out_bit = numerics_list.pop(0)
        if shifted_out_bit != sign_bit:
            overflow = True
        numerics_list.append('0')
    
    numerics_list.insert(0, sign_bit)    #put the sign back
    
    r64 = hex(int(''.join(numerics_list),2)).lstrip('0x').rjust(16,'0').upper()
    
    regs[even_reg] = r64[0:8]
    regs[odd_reg] = r64[8:16]
    
    result = cvthex2int(r64)
    
    if overflow:
        cond_code = ['0','0','0','1']
    elif result == 0:
        cond_code = ['1','0','0','0']
    elif result < 0:
        cond_code = ['0','1','0','0']
    elif result > 0:
        cond_code = ['0','0','1','0']
        
    return program_counter + i_field_num_bytes


#Shift Left Double Logical
def SLDL():
    global regs
    #OC,R1,X2,B2,D2

    even_reg = _R1
    odd_reg = _R1 + 1
    
    op1_e = cast_to_type(regs[even_reg],str)
    op1_o = cast_to_type(regs[odd_reg],str) 
       
    op1_e_o_bin = bin(int(op1_e + op1_o,16)).lstrip('0b').rjust(64,'0')
    op1_e_o_list = list(op1_e_o_bin)
    
    for i in range(0,_D2):
        op1_e_o_list.pop(0)
        op1_e_o_list.append('0')
    
    r64 = hex(int(''.join(op1_e_o_list),2)).lstrip('0x').rjust(16,'0').upper()
    
    regs[even_reg] = r64[0:8]
    regs[odd_reg] = r64[8:16]
        
    return program_counter + i_field_num_bytes


#Shift Left Single Logical
def SLL():
    global regs
    #OC,R1,X2,B2,D2
    
    op1 = cast_to_type(regs[_R1],str)
        
    op1_bin = bin(int(op1,16)).lstrip('0b').rjust(32,'0')
    op1_list = list(op1_bin)
    
    for i in range(0,_D2):
        op1_list.pop(0)
        op1_list.append('0')
    
    regs[_R1] = hex(int(''.join(op1_list),2)).lstrip('0x').rjust(8,'0').upper()
        
    return program_counter + i_field_num_bytes


#Subtract Logical Register
def SLR():
    #OC,R1,R2
    Add_Sub_Logical_code(0, '-')
    
    return program_counter + i_field_num_bytes

    
#Subtract Packed
def SP():
    #OC,L1,L2,B1,D1,B3,D3
    Add_Sub_Mul_Packed_code('-')
    
    return program_counter + i_field_num_bytes


#Subtract Register
def SR():
    #OC,R1,R2
    Add_Sub_code(0, '-')
    
    return program_counter + i_field_num_bytes


#Shift Right Single
def SRA():
    global regs, cond_code
    #OC,R1,X2,B2,D2
    
    op1 = cast_to_type(regs[_R1],str)
        
    b = bin(int(op1,16)).lstrip('0b').rjust(32,'0')
    
    sign_bit = b[0]
    numerics = b[1:]
   
    numerics_list = list(numerics)
    
    for i in range(0,_D2):
        numerics_list.pop()
        numerics_list.insert(0, sign_bit)
        
    numerics_list.insert(0, sign_bit)    #put the sign back
    
    regs[_R1] = hex(int(''.join(numerics_list),2)).lstrip('0x').rjust(8,'0').upper()
    result = cvthex2int(regs[_R1])
    
    cond_code = ['0','0','0','0']
    if result == 0:
        cond_code = ['1','0','0','0']
    elif result < 0:
        cond_code = ['0','1','0','0']
    elif result > 0:
        cond_code = ['0','0','1','0']
        
    return program_counter + i_field_num_bytes


#Shift Right Double
def SRDA():
    global regs, cond_code
    #OC,R1,X2,B2,D2

    even_reg = _R1
    odd_reg = _R1 + 1
    
    op1_e = cast_to_type(regs[even_reg],str)
    op1_o = cast_to_type(regs[odd_reg],str)
     
    b = bin(int(op1_e + op1_o,16)).lstrip('0b').rjust(64,'0')
    
    sign_bit = b[0]
    numerics = b[1:]
   
    numerics_list = list(numerics)
    
    for i in range(0,_D2):
        numerics_list.pop()
        numerics_list.insert(0, sign_bit)
        
    numerics_list.insert(0, sign_bit)    #put the sign back
    
    r64 = hex(int(''.join(numerics_list),2)).lstrip('0x').rjust(16,'0').upper()
    regs[even_reg] = r64[0:8]
    regs[odd_reg] = r64[8:16]

    result = cvthex2int(r64)
    
    cond_code = ['0','0','0','0']
    if result == 0:
        cond_code = ['1','0','0','0']
    elif result < 0:
        cond_code = ['0','1','0','0']
    elif result > 0:
        cond_code = ['0','0','1','0']
        
    return program_counter + i_field_num_bytes


#Shift Right Double Logical
def SRDL():
    global regs
    #OC,R1,X2,B2,D2

    even_reg = _R1
    odd_reg = _R1 + 1
    
    op1_e = cast_to_type(regs[even_reg],str)
    op1_o = cast_to_type(regs[odd_reg],str) 
        
    op1_e_o_bin = bin(int(op1_e + op1_o,16)).lstrip('0b').rjust(64,'0')
    op1_e_o_list = list(op1_e_o_bin)
    
    for i in range(0,_D2):
        op1_e_o_list.pop()
        op1_e_o_list.insert(0, '0')
        
    r64 = hex(int(''.join(op1_e_o_list),2)).lstrip('0x').rjust(16,'0').upper()
    regs[even_reg] = r64[0:8]
    regs[odd_reg] = r64[8:16]
        
    return program_counter + i_field_num_bytes


#Shift Right Single Logical
def SRL():
    global regs, cond_code
    #OC,R1,X2,B2,D2
    
    op1 = cast_to_type(regs[_R1],str)
        
    op1_bin = bin(int(op1,16)).lstrip('0b').rjust(32,'0')
    op1_list = list(op1_bin)
    
    for i in range(0,_D2):
        op1_list.pop()
        op1_list.insert(0, '0')
        
    regs[_R1] = hex(int(''.join(op1_list),2)).lstrip('0x').rjust(8,'0').upper()
        
    return program_counter + i_field_num_bytes


#Shift and Round Decimal
def SRP():
    global instrdata_list, cond_code
    #OC,L1,L2,B1,D1,B3,D3
    
    addr = calc_address(_B1, _D1)
    op1 = ''.join(instrdata_list[addr:addr+_L1+1])
    
    sign = op1[-1]
    digits = list(op1[0:-1])
    
    rounding_digit = _L2
    num_to_shift = _D3

    if num_to_shift > 31:   #indicates a negative value, convert 2s comp to - signed integer
        t  = bin(num_to_shift).lstrip('0b').rjust(16,'1')
        num_to_shift = cvt2scomp(hex(int(t,2)).lstrip('0x').upper())
        
    overflow = False
    t = digits
    if num_to_shift > 0:
        #shift left
        for i in range(0,num_to_shift):
            d = digits.pop(0)
            if d != '0':
                overflow = True
            digits.append('0')
        t = ''.join(digits)    
    elif num_to_shift < 0:
        #shift right
        for i in range(0,abs(num_to_shift)):
            d = digits.pop()
            digits.insert(0,'0')
        t = ''.join(digits)
        #round if sum of last digit shifted + the rounding digit result in a carry 
        if int(d) + rounding_digit > 9:
            t = str(int(t) + 1).rjust((2*(_L1+1))-1,'0')
    
    if overflow:
        cond_code = ['0','0','0','1']
    elif int(t) == 0:
        cond_code = ['1','0','0','0']
    elif sign in 'BD':
        cond_code = ['0','1','0','0']    
    elif sign in 'ACEF':
        cond_code = ['0','0','1','0']

    op1 = t + sign
    
    z = 0
    for i in range(0,(_L1+1)*2,2):
        instrdata_list[addr+z] = op1[i:i+2]
        z = z + 1    
        
    return program_counter + i_field_num_bytes


#Store
def ST():
    #OC,R1,X2,B2,D2
    Store_code(4)
    
    return program_counter + i_field_num_bytes


#Store Character
def STC():
    #OC,R1,X2,B2,D2
    Store_code(1)
    
    return program_counter + i_field_num_bytes


#Store Halfword
def STH():
    #OC,R1,X2,B2,D2
    Store_code(2)
    
    return program_counter + i_field_num_bytes


#Store Characters under Mask
def STCM():
    global instrdata_list
    #OC,R1,R2,B2,D2
        
    _M3 = _R2
    
    mask = list(bin(_M3).lstrip('0b').rjust(4,'0'))
    numb = mask.count('1')
    
    if numb == 0:
        return program_counter + i_field_num_bytes
        
    op1 = cast_to_type(regs[_R1],str)    
        
    op1_list = [op1[i:i+2] for i in range(0,8,2)]  #make list of _R1 bytes

    addr = calc_address(_B2, _D2)    
    
    j = 0
    for i in range(0,4):
        if mask[i] == '1':
            instrdata_list[addr+j] = op1_list[i]
            j = j + 1

    return program_counter + i_field_num_bytes


#Store Multiple
def STM():
    global instrdata_list
    #OC,R1,R2,B2,D2
    
    addr = calc_address(_B2, _D2)
    
    starting_reg = _R1
    ending_reg = _R2
    
    j = starting_reg

    while True:
        reg_contents = cast_to_type(regs[j],str)
        reg_contents_list = [reg_contents[i:i+2] for i in range(0,8,2)]
        for k in range(0,4):
            instrdata_list[addr+k] = reg_contents_list[k]
        addr = addr + 4
        j = j + 1
        if j > 15:
            j = 0
        if j == ending_reg+1:
            break

    return program_counter + i_field_num_bytes    

    
#Test under Mask
def TM():
    global cond_code
    #OC,I2,B1,D1
    
    cond_code = ['1','0','0','0']   #assume Selected bits all zeros, or the mask is all zeros  
    
    _M1 = int(_I2,16)
    
    mask = list(bin(_M1).lstrip('0b').rjust(8,'0'))
    numb = mask.count('1')
    
    if numb == 0:
        return program_counter + i_field_num_bytes 
        
    addr = calc_address(_B1, _D1)
    op1 = int(instrdata_list[addr],16)    
    op1_list = list(bin(op1).lstrip('0b').rjust(8,'0'))
    
    zeroct = 0
    for i in range(0,8):
        if mask[i] == '1':
            if op1_list[i] == '0':
                zeroct = zeroct + 1

    if zeroct == numb:
        pass
    elif zeroct == 0:
        cond_code = ['0','0','0','1']
    else:
        cond_code = ['0','1','0','0']    
        
    return program_counter + i_field_num_bytes
    
    
#Translate
def TR():
    global instrdata_list
    #OC,LL,B1,D1,B3,D3
    
    arg_addr = calc_address(_B1, _D1)
    func_addr = calc_address(_B3, _D3)

    for i in range(0,_LL+1):
        offset = int(instrdata_list[arg_addr+i],16)
        instrdata_list[arg_addr+i] = instrdata_list[func_addr+offset]
        
    return program_counter + i_field_num_bytes


#Translate and Test
def TRT():
    global regs, instrdata_list, cond_code
    #OC,LL,B1,D1,B3,D3
    
    cond_code = ['1','0','0','0']   #assume All function bytes are zero
    
    arg_addr = calc_address(_B1, _D1)
    func_addr = calc_address(_B3, _D3)
    
    got_hit_on_last = False
    
    for i in range(0,_LL+1):
        offset = int(instrdata_list[arg_addr+i],16)
        trans_byte = instrdata_list[func_addr+offset]
        
        if trans_byte != '00':
            regs[1] = arg_addr+i
            R2_str = cast_to_type(regs[2],str)
            regs[2] = R2_str[0:6] + trans_byte
            if i == _LL:
                got_hit_on_last = True
            break
            
    if i < _LL:
        cond_code = ['0','1','0','0']
    elif got_hit_on_last:    
        cond_code = ['0','0','1','0']  

    return program_counter + i_field_num_bytes


#UnPack
def UNPK():
    global instrdata_list
    #OC,L1,L2,B1,D1,B3,D3
    
    addr1 = calc_address(_B1, _D1)
    numb1 = _L1 + 1

    addr2 = calc_address(_B3, _D3)
    numb2 = _L2 + 1
    
    op2 = ''.join(instrdata_list[addr2:addr2+numb2])    
    
    digits = op2[0:-1].rjust(numb1,'0')

    sign = op2[-1]
    
    unpacked_result = ''
    
    for i in range(0,len(digits)-1):
        unpacked_result = unpacked_result + 'F' + digits[i]
        
    unpacked_result = unpacked_result + sign + digits[-1]

    j = 0
    for i in range(0,numb1*2,2):
        instrdata_list[addr1+j] = unpacked_result[i:i+2]
        j = j + 1

    return program_counter + i_field_num_bytes    
    

#XOR
def X():
    #OC,R1,X2,B2,D2
    And_Or_Xor_code(i_format, ' ^ ')
    
    return program_counter + i_field_num_bytes


#XOR Characters
def XC():
    #OC,LL,B1,D1,B3,D3
    And_Or_Xor_code(i_format, ' ^ ')
    
    return program_counter + i_field_num_bytes 


#XOR Immediate
def XI():
    #OC,I2,B1,D1
    And_Or_Xor_code(i_format, ' ^ ')
    
    return program_counter + i_field_num_bytes


#XOR Register
def XR():
    #OC,R1,R2
    And_Or_Xor_code(i_format, ' ^ ')
    
    return program_counter + i_field_num_bytes

    
#Zero and Add Packed
def ZAP():
    #OC,L1,L2,B1,D1,B3,D3
    Add_Sub_Mul_Packed_code('z')
    
    return program_counter + i_field_num_bytes    


#Execute
def EX():
    global Execute_list, save_program_counter
    #OC,R1,X2,B2,D2
    op1 = cast_to_type(regs[_R1],str)

    op1_list = [op1[i:i+2] for i in range(0,8,2)]  #make list of _R1 bytes
    
    addr = calc_address(_B2, _D2, _X2)
    Execute_list = instrdata_list[addr:addr+6]   #copy instruction to be EXECUTEd to a list
    
    field1 = int(op1_list[3],16)     #bits 24-31 of the register specified by R1
    field2 = int(Execute_list[1],16) #Bits 8-15 of the instruction designated by the branch address
    
    result = field1 | field2             #OR the two
    
    Execute_list[1] = hex(result).lstrip('0x').rjust(2,'0').upper() #and replace Bits 8-15 of the instruction
    
    save_program_counter = program_counter + i_field_num_bytes
    
    return 999999
    
    
#Supervisor Call
def SVC(): 
    global regs, instrdata_list
    global file_handle_dict
    global term_output
    
    term_output = ''
    
    #OC,R1,R2   
    SVCnum = (_R1 * 16) + _R2
    
    if SVCnum == 255:                       #print alphanumeric data to terminal
        addr = cast_to_type(regs[0],int)    #register 0 points to data
        numb = cast_to_type(regs[1],int)    #register 1 is the data length
        if not Debug:
            for ebyte in instrdata_list[addr:addr+numb]:
                print(chr(int(EBC2ASC[int(ebyte,16)],16)), end="")
            print(' ')
        else:
            for ebyte in instrdata_list[addr:addr+numb]:
                term_output += chr(int(EBC2ASC[int(ebyte,16)],16))
            
        
    elif SVCnum == 254:   #print contents of register 0 to terminal as signed integer
        print(cast_to_type(regs[0],int))
        
    elif SVCnum == 253:   #print contents of register 0 to terminal as 4 byte hex string
        print(cast_to_type(regs[0],str))
        
    elif SVCnum == 252:   #print contents of the cond_code
        print(cond_code)
        
    elif SVCnum == 251:   #print the contents of the regs
        print(regs)
        
    elif SVCnum == 250:   #sleep for x ms
        numms = cast_to_type(regs[0],int)    #register 0 is the number of ms to sleep
        time.sleep(numms / 1000)
        
    elif SVCnum == 249:   #open PC file
        rw_dict = {'00': 'r', '01': 'w'}
        addr = cast_to_type(regs[0],int)    #register 0 points to file name to open
        R1_str = cast_to_type(regs[1],str)  #register 1 byte 0 = file handle number; byte 1 = r/w indicator; bytes 2-3 = file name length
        file_handle_num = R1_str[0:2]       #00 - 99 file handle
        rw_indicator = R1_str[2:4]          #00 = open for read; 01 = open for write 
        
        if rw_indicator not in rw_dict.keys():
            print('SVC 249 - Open Error: register 1 byte 1 r/w indicator invalid')
            regs[15] = 1                            #invalid r/w indicator then set rc in register 15 to 1
        else:
            try:
                t = int(file_handle_num)            #make sure file handle is valid
                filename_len = int(R1_str[4:],16)
                filename = ''
                for i in range(0,filename_len):
                    ebyte = instrdata_list[addr+i]
                    filename = filename + chr(int(EBC2ASC[int(ebyte,16)],16))
                try:    
                    open_string = 'fh' + file_handle_num + ' = open(filename, rw_dict[rw_indicator])'
                    exec(open_string)
                    file_handle_dict['fh' + file_handle_num] = eval('fh' + file_handle_num)
                    regs[15] = 0                    #good file open then set rc in register 15 to 0
                except:
                    print('SVC 249 - Open Error: general file open error')
                    regs[15] = 3                    #bad file open then set rc in register 15 to 3
            except ValueError:
                print('SVC 249 - Open Error: register 1 byte 0 invalid file handle number')
                regs[15] = 2                        #invalid file handle then set rc in register 15 to 2
                
    elif SVCnum == 248:   #close PC file
        R1_str = cast_to_type(regs[1],str)          #register 1 byte 0 = file handle number
        file_handle_num = R1_str[0:2]               #00 - 99 file handle
        try:
            t = int(file_handle_num)                #make sure file handle is valid
            try:
                file_handle_dict['fh' + file_handle_num].close()
                del file_handle_dict['fh' + file_handle_num]
                regs[15] = 0                        #indicate good return from close
            except:
                print('SVC 248 - Close Error: general file close error')
                regs[15] = 2                        #indicate bad return from close
        except ValueError:
            print('SVC 248 - Close Error: register 1 byte 0 invalid file handle')
            regs[15] = 1                            #invalid file handle then set rc in register 15 to 1            
        
    elif SVCnum == 247:   #get record from PC file
        R1_str = cast_to_type(regs[1],str)          #register 1 byte 0 = file handle number
        file_handle_num = R1_str[0:2]               #00 - 99 file handle
        try:
            t = int(file_handle_num)                #make sure file handle is valid
            try:
                record = file_handle_dict['fh' + file_handle_num].readline().rstrip('\n')
                reclen = len(record)
                regs[15] = reclen                       #load register 15 with the length of the record read 
                if reclen > 0:                          #a record length of 0 indicates an EOF condition
                    addr = cast_to_type(regs[0],int)    #register 0 points to data area
                    for i in range(0,reclen):
                        instrdata_list[addr+i] = ASC2EBC[ord(record[i])]
            except:
                print('SVC 247 - Get Error: general file get error')
                regs[15] = -1                           #indicate bad return from get
        except ValueError:
            print('SVC 247 - Get Error: register 1 byte 0 invalid file handle')
            regs[15] = 1                            #invalid file handle then set rc in register 15 to 1            
            
    elif SVCnum == 246:   #put record to PC file
        addr = cast_to_type(regs[0],int)            #register 0 points to data
        R1_str = cast_to_type(regs[1],str)          #register 1 byte 0 = file handle number; bytes 2-3 = the data length
        file_handle_num = R1_str[0:2]               #00 - 99 file handle
        numb = int(R1_str[4:],16)                   #extract data length from register 1 bytes 2-3
        try:
            t = int(file_handle_num)                #make sure file handle is valid
            try:
                for ebyte in instrdata_list[addr:addr+numb]:
                    file_handle_dict['fh' + file_handle_num].write(chr(int(EBC2ASC[int(ebyte,16)],16)))
                file_handle_dict['fh' + file_handle_num].write('\n')
                regs[15] = 0                        #indicate good return from put
            except:
                print('SVC 246 - Get Error: general file put error')
                regs[15] = 2                        #indicate bad return from put
        except ValueError:
            print('SVC 246 - Put Error: register 1 byte 1 invalid file handle')
            regs[15] = 1                            #invalid file handle then set rc in register 15 to 1            
    else:
        print('Invalid SVC')
    
    return program_counter + i_field_num_bytes


# -------------------------------------------------------------------
#main
# -------------------------------------------------------------------

ASC2EBC = ['00', '01', '02', '03', '1A', '09', '1A', '7F', '1A', '1A', '1A', '0B', '0C', '0D', '0E', '0F',    # 00 - 0F
           '10', '11', '12', '13', '3C', '3D', '32', '26', '18', '19', '3F', '27', '1C', '1D', '1E', '1F',    # 10 - 1F
           '40', '4F', '7F', '7B', '5B', '6C', '50', '7D', '4D', '5D', '5C', '4E', '6B', '60', '4B', '61',    # 20 - 2F
           'F0', 'F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8', 'F9', '7A', '5E', '4C', '7E', '6E', '6F',    # 30 - 3F
           '7C', 'C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7', 'C8', 'C9', 'D1', 'D2', 'D3', 'D4', 'D5', 'D6',    # 40 - 4F
           'D7', 'D8', 'D9', 'E2', 'E3', 'E4', 'E5', 'E6', 'E7', 'E8', 'E9', '4A', 'E0', '5A', '5F', '6D',    # 50 - 5F
           '79', '81', '82', '83', '84', '85', '86', '87', '88', '89', '91', '92', '93', '94', '95', '96',    # 60 - 6F
           '97', '98', '99', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7', 'A8', 'A9', 'C0', '6A', 'D0', 'A1', '07',    # 70 - 7F
           '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F',    # 80 - 8F
           '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F',    # 90 - 9F
           '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F',    # A0 - AF
           '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F',    # B0 - BF
           '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F',    # C0 - CF
           '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F',    # D0 - DF
           '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F',    # E0 - EF
           '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F', '3F']    # F0 - FF

EBC2ASC = ['00', '01', '02', '03', '1A', '09', '1A', '7F', '1A', '1A', '1A', '0B', '0C', '0D', '0E', '0F',    # 00 - 0F
           '10', '11', '12', '13', '1A', '1A', '08', '1A', '18', '19', '1A', '1A', '1C', '1D', '1E', '1F',    # 10 - 1F
           '1A', '1A', '1A', '1A', '1A', '0A', '17', '1B', '1A', '1A', '1A', '1A', '1A', '05', '06', '07',    # 20 - 2F
           '1A', '1A', '16', '1A', '1A', '1A', '1A', '04', '1A', '1A', '1A', '1A', '14', '15', '1A', '1A',    # 30 - 3F
           '20', '1A', '1A', '1A', '1A', '1A', '1A', '1A', '1A', '1A', '5B', '2E', '3C', '28', '2B', '21',    # 40 - 4F
           '26', '1A', '1A', '1A', '1A', '1A', '1A', '1A', '1A', '1A', '5D', '24', '2A', '29', '3B', '5E',    # 50 - 5F
           '2D', '1A', '1A', '1A', '1A', '1A', '1A', '1A', '1A', '1A', '7C', '2C', '25', '5F', '3E', '3F',    # 60 - 6F
           '1A', '1A', '1A', '1A', '1A', '1A', '1A', '1A', '1A', '60', '3A', '23', '40', '27', '3D', '22',    # 70 - 7F
           '1A', '61', '62', '63', '64', '65', '66', '67', '68', '69', '1A', '1A', '1A', '1A', '1A', '1A',    # 80 - 8F
           '1A', '6A', '6B', '6C', '6D', '6E', '6F', '70', '71', '72', '1A', '1A', '1A', '1A', '1A', '1A',    # 90 - 9F
           '1A', '7E', '73', '74', '75', '76', '77', '78', '79', '7A', '1A', '1A', '1A', '1A', '1A', '1A',    # A0 - AF
           '1A', '1A', '1A', '1A', '1A', '1A', '1A', '1A', '1A', '1A', '1A', '1A', '1A', '1A', '1A', '1A',    # B0 - BF
           '7B', '41', '42', '43', '44', '45', '46', '47', '48', '49', '1A', '1A', '1A', '1A', '1A', '1A',    # C0 - CF
           '7D', '4A', '4B', '4C', '4D', '4E', '4F', '50', '51', '52', '1A', '1A', '1A', '1A', '1A', '1A',    # D0 - DF
           '5C', '1A', '53', '54', '55', '56', '57', '58', '59', '5A', '1A', '1A', '1A', '1A', '1A', '1A',    # E0 - EF
           '30', '31', '32', '33', '34', '35', '36', '37', '38', '39', '1A', '1A', '1A', '1A', '1A', '1A']    # F0 - FF
           
#Here are the machine instructions that are emulated
mach_inst = { '05': ('RR',BALR), '46': ('RX',BCT),   '06': ('RR',BCTR), '47': ('RX',BC),  '07': ('RR',BCR), 
              '45': ('RX',BAL),  '58': ('RX',L),     '48': ('RX',LH),   '18': ('RR',LR),  '41': ('RX',LA),
              'D2': ('SS',MVC),  '92': ('SI',MVI),   '5A': ('RX',A),    '4A': ('RX',AH),  '1A': ('RR',AR),
              '5B': ('RX',S),    '4B': ('RX',SH),    '1B': ('RR',SR),   '59': ('RX',C),   '49': ('RX',CH),
              '55': ('RX',CL),   '15': ('RR',CLR),   '95': ('SI',CLI),  'D5': ('SS',CLC), 'BD': ('RS',CLM),
              '50': ('RX',ST),   '42': ('RX',STC),   '40': ('RX',STH),  '4F': ('RX',CVB), '4E': ('RX',CVD),
              '14': ('RR',NR),   '54': ('RX',N),     '94': ('SI',NI),   'D4': ('SS',NC),  '5D': ('RX',D),   
              '16': ('RR',OR),   '56': ('RX',O),     '96': ('SI',OI),   'D6': ('SS',OC),  '1D': ('RR',DR), 
              '17': ('RR',XR),   '57': ('RX',X),     '97': ('SI',XI),   'D7': ('SS',XC),  '5C': ('RX',M),
              '43': ('RX',IC),   'BF': ('RS',ICM),   'BE': ('RS',STCM), '12': ('RR',LTR), '44': ('RX',EX),
              '0A': ('RR',SVC),  '19': ('RR',CR),    '91': ('SI',TM),   'DC': ('SS',TR),  'DD': ('SS',TRT), 
              'FA': ('SS2',AP),  'FB': ('SS2',SP),   'FC': ('SS2',MP),  'F8': ('SS2',ZAP),'4C': ('RX',MH),
              '1C': ('RR',MR),   'F2': ('SS2',PACK), 'F3': ('SS2',UNPK),'F9': ('SS2',CP), 'FD': ('SS2',DP),
              '90': ('RS',STM),  '98': ('RS',LM),    '10': ('RR',LPR),  '11': ('RR',LNR), '13': ('RR',LCR),
              '5E': ('RX',AL),   '1E': ('RR',ALR),   '5F': ('RX',SL),   '1F': ('RR',SLR), '8B': ('RX',SLA),
              '8F': ('RX',SLDA), '8D': ('RX',SLDL),  '89': ('RX',SLL),  '8A': ('RX',SRA), '8E': ('RX',SRDA),
              '8C': ('RX',SRDL), '88': ('RX',SRL),   'D1': ('SS',MVN),  'F1': ('SS2',MVO),'D3': ('SS',MVZ),
              '0F': ('RR',CLCL), '0E': ('RR',MVCL),  'BA': ('RS',CS),   'BB': ('RS',CDS), 'F0': ('SS2',SRP),
              'DE': ('SS',ED),   'DF': ('SS',EDMK),  '86': ('RS',BXH),  '87': ('RS',BXLE) }

OC = '_OC = mi_slice[0:2]'
R1 = '_R1 = int(mi_slice[2:3],16)'
R2 = '_R2 = int(mi_slice[3:4],16)'
X2 = '_X2 = int(mi_slice[3:4],16)'
B1 = '_B1 = int(mi_slice[4:5],16)'
B2 = '_B2 = int(mi_slice[4:5],16)'
D1 = '_D1 = int(mi_slice[5:8],16)'
D2 = '_D2 = int(mi_slice[5:8],16)'
LL = '_LL = int(mi_slice[2:4],16)'
L1 = '_L1 = int(mi_slice[2:3],16)'
L2 = '_L2 = int(mi_slice[3:4],16)'
B3 = '_B3 = int(mi_slice[8:9],16)'
D3 = '_D3 = int(mi_slice[9:12],16)'
I2 = '_I2 = mi_slice[2:4]'

format = { 'RR': [2,(OC,R1,R2)], 'RX': [4,(OC,R1,X2,B2,D2)], 'SI': [4,(OC,I2,B1,D1)], 'SS': [6,(OC,LL,B1,D1,B3,D3)],
           'RS': [4,(OC,R1,R2,B2,D2)], 'SS2': [6,(OC,L1,L2,B1,D1,B3,D3)] }
           
file_handle_dict = {}           

breakpoints = []
hit_on_breakpoint = False

last_command = ''

napms_delay = 1000

if Debug:
    # create Main Window
    screen = curses.initscr()

    num_rows, num_cols = screen.getmaxyx()
    if num_rows < 18 or num_cols < 75:
        print("Screen too small")
        print("You must have > 18 rows and > 75 cols")
        print("Your current Rows:    %d" % num_rows)
        print("Your current Columns: %d" % num_cols)
        print("Aborting")
        exit()
    
    # create Command Window
    cmd_window = curses.newwin(5, 75, 12, 1) # lines, columns, start line, start column

# Fetch - Decode - Execute Loop
while True:

    if program_counter == 978670:   #handle a 'BR    14' to normally exit this program
        print('Normal Program End')
        break
        
    if program_counter == 999999:   #handle a staged EXECUTE instruction
        try:
            instr = Execute_list[0]
        except IndexError:
            print('Abnormal Program End from EXECUTE')
            break
    else:
        try:
            instr = instrdata_list[program_counter]
        except IndexError:
            print('Abnormal Program End')
            break
        
    try:    
        i_format = mach_inst[instr][0]
    except KeyError:
        print('Abnormal Program End')
        break
        
    i_fields = format[i_format]
    i_field_num_bytes = i_fields[0]
    i_field_parts = i_fields[1]
    
    if program_counter == 999999:   #handle a staged EXECUTE instruction
        mi_slice = ''.join(Execute_list[0:i_field_num_bytes])
    else:
        mi_slice = ''.join(instrdata_list[program_counter:program_counter + i_field_num_bytes])

    for part in i_field_parts:
       exec(part)

    screen_program_counter = hex(program_counter).lstrip('0x').rjust(6,'0').upper()
    try:
        screen_last_instr = source_code_dict[screen_program_counter]
    except KeyError:
        screen_last_instr = '????'
        
    if screen_program_counter in breakpoints:
        hit_on_breakpoint = True
        
    program_counter = mach_inst[_OC][1]()
    
    if program_counter > 999999:    #if we returned from an EXECUTEd instruction, restore program_counter
        program_counter = save_program_counter
        
    try:
        screen_cond_code = str(cond_code.index('1'))
    except ValueError:
        screen_cond_code = 'Not Set'
        
    if not Debug:
        continue
        
    screen.clear()
    screen.border(0)
    screen.addstr(1, 24, "S/370 BAL Emulator and Debugger")
    
    screen.addstr(2, 2, "Program Counter:")
    screen.addstr(2, 19, screen_program_counter)

    screen.addstr(3, 2, "Last Instruction:")
    screen.addstr(3, 20, screen_last_instr)

    screen.addstr(4, 2, "Condition Code after Last Instruction:")
    screen.addstr(4, 41, screen_cond_code)

    screen.addstr(6, 2, "Registers after Last Instruction:")
    screen.addstr(7, 2, "R0-R3 ")
    screen.addstr(8, 2, "R4-R7 ")
    screen.addstr(9, 2, "R8-R11 ")
    screen.addstr(10, 2, "R12-R15 ")
    
    # Send the registers to the screen
    k = 0
    c = 11
    for r in range(0,4):
        for j in range(0,4):
            screen.addstr(r+7, c, cast_to_type(regs[k],str))
            k = k + 1
            c = c + 10
        c = 11    
        
    # Changes go in to the screen buffer and only get
    # displayed after calling `refresh()` to update
    screen.refresh()
    
    # Handle Debug Commands
    while True:
        cmd_window.clear()
        cmd_window.border(0)
        cmd_window.addstr(1, 2, "Command: ")
        cmd_window.addstr(2, 13, term_output)
        term_output = ''
        cmd_window.refresh()
        
        #if no hit on breakpoint and last command = go (g) then keep going
        if not hit_on_breakpoint: 
            if last_command == 'g':
                curses.napms(napms_delay)
                break
        else:
            hit_on_breakpoint = False
            last_command = ''
            
        #read the command     
        screen_str = cmd_window.getstr(1, 11, 30).decode("utf-8")  
        #decode changes byte object to string object
        
        #handle single step (s) command - format:  s
        if screen_str == 's':
            break
            
        #handle go (g) command - format:  g
        elif screen_str == 'g':
            last_command = 'g'
            break
            
        #handle set execution delay (sd) command - format:  sd delay_in_ms
        elif screen_str.startswith('sd '):
            napms_delay = int(screen_str[3:])
            cmd_window.addstr(2, 2, "Delay set to "+screen_str[3:]+" ms")
            
        #handle set breakpoint (sb) command - format:  sb breakpoint_address_to_stop_at
        #address is in form of string of 1-6 hex digits
        elif screen_str.startswith('sb '):
            addr = screen_str[3:].rjust(6,'0').upper()
            breakpoints.append(addr)
            cmd_window.addstr(2, 2, "Breakpoints: ")
            cmd_window.addstr(2, 15, str(breakpoints))

        #handle clear breakpoint (cb) command - format:  cb breakpoint_address_to_clear
        #or   cb all   to clear ALL breakpoints
        #address is in form of string of 1-6 hex digits
        elif screen_str.startswith('cb '):
            addr = screen_str[3:].rjust(6,'0').upper()
            try:
                if addr != '000ALL':
                    breakpoints.remove(addr)
                else:
                    breakpoints = []
                cmd_window.addstr(2, 2, "Breakpoints: ")
                cmd_window.addstr(2, 15, str(breakpoints))
            except ValueError:
                cmd_window.addstr(2, 2, "Breakpoint Not Found")
                
        #handle display breakpoints (db) command - format:  db
        elif screen_str == 'db':
            cmd_window.addstr(2, 2, "Breakpoints: ")
            cmd_window.addstr(2, 15, str(breakpoints))

        #handle display memory (dm) command - format:  dm start_address_to_display num_of_bytes
        #address is in form of string of 1-6 hex digits
        #number of bytes in form of 1-2 dec digits
        elif screen_str.startswith('dm '):
            addr, num_of_bytes = screen_str[3:].split(' ')
            addr_int = int(addr,16)
            num_of_bytes_int = int(num_of_bytes)
            #clamp to a max of 48 bytes
            if num_of_bytes_int > 48:
                num_of_bytes_int = 48
            memory_contents = '[' + ' '.join(instrdata_list[addr_int:addr_int+num_of_bytes_int]) + ']'
            cmd_window.addstr(2, 2, memory_contents)            
            
        #handle display field (df) command - format:  df valid_field_name or df valid_field_name(dsect_reg)
        #example: assume FIELDA is addressed directly off the CSECT base register then 'df FIELDA' means
        #means lookup FIELDA in symbol_dict, then find its start_address
        #example: assume FIELD1 is in a DSECT pointed to by R10 then 'df FIELD1(10)'  means lookup FIELD1 
        #in symbol_dict, find its start_address, then add contents of dsect pointer R10 to start_address
        #valid_field_name is a data area defined by a DS or DC 
        #and is a key in the symbol_dict dictionary
        elif screen_str.startswith('df '):
            field_list = screen_str[3:].rstrip(')').split('(')
            field = field_list[0]
            try:
                st_addr, field_len = symbol_dict[field.ljust(8).upper()]
                if len(field_list) == 2:
                    st_addr_int = cvthex2int(st_addr) + regs[int(field_list[1])]
                else:
                    st_addr_int = cvthex2int(st_addr)
                field_len_int = cvthex2int(field_len)
                #clamp to a max of 48 bytes
                if field_len_int > 48:
                    field_len_int = 48
                field_contents = '[' + ' '.join(instrdata_list[st_addr_int:st_addr_int+field_len_int]) + ']'
                cmd_window.addstr(2, 2, field+" = ")
                cmd_window.addstr(2, 13, str(field_contents))
            except KeyError:
                cmd_window.addstr(2, 2, "Field Name Not Found ")
        else:
            cmd_window.addstr(2, 2, "Invalid Command")
            
        cmd_window.addstr(1, 2, "Press <ENTER> to Continue")
        cmd_window.getch()
        cmd_window.refresh()
        
if Debug:        
    curses.endwin()

exit()