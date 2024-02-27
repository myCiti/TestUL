version = "1.0"

import machine, time, json, gc
from machine_i2c_lcd import I2cLcd
from menu import Menu
from rotary_enc import Rotary

machine.freq(133_000_000)   # set cpu frequency
config_file = "config.json"

config ={
    'TIMERS':   {
        'T1':   5,
        'T2':   5,
        'T3':   5,
        'T4':   5
    }
}

### input/output pins
inPin = {
    'Open'      : 22,
    'Close'     : 21,
    'Stop'      : 6,
    'OpenLmt'   : 3, 
    'CloseLmt'  : 2,
}

outPin = {
    'Open'      : 10,
    'Close'     : 11,
    'Stop'      : 12,
    'Counter'   : 7,
    'O4'        : 13
}

Input = dict((name, machine.Pin(pin, machine.Pin.IN, machine.Pin.PULL_DOWN)) for (name, pin) in inPin.items())
Output = dict((name, machine.Pin(pin, machine.Pin.OUT, machine.Pin.PULL_DOWN)) for (name, pin) in outPin.items())

def load_file(file):
    """Load json file configuration."""
    global config
    with open(file, 'r') as infile:
        config = json.load(infile)

def write_file(file):
    """Write config to file."""
    with open(file, 'w') as outfile:
        json.dump(config, outfile)

try:
    load_file(config_file)
except OSError:
    write_file(config_file)
    load_file(config_file)

# define global variables
stop_signal:bool = False
is_stopled_on:bool = False
is_running:bool = False

i2c = machine.I2C(0, sda = machine.Pin(4), scl=machine.Pin(5), freq = 400_000 )
lcd = I2cLcd(i2c, 0x27, 4, 20)

rotary_encoder = Rotary(
    button_pin= 9,
    clk_pin= 15,
    dt_pin= 8,
    half_step= False
)

def initialize () -> None:
    """ Initialization before each run"""
    global stop_signal, is_running

    stop_signal = False
    is_running = False

    for p in Output:
        Output[p].low()

    for p in Input:
        Input[p]

    lcd.clear()
    lcd.write_line_center(f'WELCOME V{version}', 1)
    lcd.write_line_center(f'OPEN/CLOSE TO START', 3)
    time.sleep_ms(1500)
    lcd.clear()
    for line, (k, v) in enumerate(sorted(config['TIMERS'].items())):
        lcd.write_line('{0:<10}: {1:>3}'.format(k,v),line+1, 1)

    gc.collect()

def readPin(pin:str, delay:int = 50) -> bool:
    """Read value of a pin a number of times to determine good signal, delay in microseconds."""

    counter = 0
    ntime = 3
        
    if pin not in Input:
        return False
        
    for _ in range(ntime):
        if Input[pin].value():
            counter += 1
        time.sleep_us(delay)

    if counter == ntime:
        return True

    return False    

def writePin(pin:str, delay:int=500):
    """Write low/high value to a pin for a duration in milliseconds. 
       If still pressed, wait for a time.
    """
    if not stop_signal:
        Output[pin].high()
    
    elapsed = 0
    start = time.ticks_ms()
    while readPin(pin) or elapsed < delay:
        time.sleep_ms(50)
        elapsed = time.ticks_diff(time.ticks_ms(), start)

    Output[pin].low()

def turnPinOn(pin:str) -> None:
    """Turn pin high value"""
    if not stop_signal:
        Output[pin].high()

def turnPinOff(pin:str) -> None:
    """Turn pin low value"""
    if not stop_signal:
        Output[pin].low()

def write_line_center(msg: str, line:int) -> None:
    """Write message to lcd at center of screen"""
    if not stop_signal:
        lcd.write_line_center(msg, line)

def count_down(duration:int):
    """Count down in second and display remaining time on LCD."""
    for i in range(duration, 0, -1):
        start = time.ticks_ms()
        lcd.write_line(f'{i:<4}', 2,17)
        if stop_signal: break
        elapsed = time.ticks_diff(time.ticks_ms(), start)
        time.sleep_ms(1000 - elapsed)

    lcd.write_line(f'{"    ":<4}', 2, 17)

def stop_signal_handler(pin):
    """"Send stop signal when detected with IRQ"""
    global stop_signal, is_stopled_on

    if not is_stopled_on and readPin('Stop'):    # if Stop LED still on, do not turn it on again
        Output['Stop'].high()
        is_stopled_on = True
        Input['Stop'].irq(trigger=machine.Pin.IRQ_RISING, handler=None)

    if is_stopled_on:
        elapsed = 0
        start = time.ticks_ms()
        while readPin('Stop') or elapsed < 5:
            time.sleep_ms(10)
            elapsed = time.ticks_diff(time.ticks_ms(), start)
        Output['Stop'].low()

        is_stopled_on = False
        stop_signal = True
        Input['Stop'].irq(trigger=machine.Pin.IRQ_RISING, handler=stop_signal_handler)


def main_logic_loop():
    """Core program - main logic loop"""
    global is_running 

    is_running = True

    lcd.clear()
    while not stop_signal:
        write_line_center(f'OPENNING...', 1)
        write_line_center(f'WAITING....', 2)
        writePin('Open')
        count_down(config['TIMERS']['T1'])
        write_line_center(f'TURN ON....', 2)
        turnPinOn('O4')
        count_down(config['TIMERS']['T2'])
        write_line_center(f'TURN OFF...', 2)
        turnPinOff('O4')
        count_down(config['TIMERS']['T3'])
        write_line_center(f'CLOSING....', 1)
        write_line_center(f'WAITING....', 2)
        writePin('Close')
        count_down(config['TIMERS']['T1'])
        write_line_center(f'TURN ON....', 2)
        turnPinOn('O4')
        count_down(config['TIMERS']['T2'])
        write_line_center(f'TURN OFF...', 2)
        turnPinOff('O4')
        count_down(config['TIMERS']['T4'])

#####
menu = Menu(['TIMERS'], 4)
menu_fct = ['TIMERS']

def config_menu(current_menu):
    """Configuration for Kostal single turn absolute encoder"""
    global config
    is_value_modified = False
    first_entry = True
    first_select = True
    menu_max_lines = min(len(config[current_menu]), 4)

    menu_keys = Menu(sorted(config[current_menu]), menu_max_lines)
    menu_values = Menu([config[current_menu][k] for k in sorted(config[current_menu])], menu_max_lines)
    line = 0
    
    while not stop_signal:
        rotary_value = rotary_encoder.value()

        if first_entry or rotary_value != 0:
            line = 1
            lcd.clear()
        
        if first_entry:
            for k, v in zip(menu_keys.show(), menu_values.show()):
                if line == menu_keys.current_line:
                    lcd.write_line('>>{0:<8}: {1:<8}'.format(k, v), line, 1)
                else:
                    lcd.write_line('{0:<8}: {1:<8}'.format(k, v), line, 3)
                line += 1
            first_entry = False
        elif rotary_value > 0:
            for k, v in zip(menu_keys.next(), menu_values.next()):
                if line == menu_keys.current_line:
                    lcd.write_line('>>{0:<8}: {1:<8}'.format(k, v), line, 1)
                else:
                    lcd.write_line('{0:<8}: {1:<8}'.format(k, v), line, 3)
                line += 1
        elif rotary_value < 0:
            for k, v in zip(menu_keys.previous(), menu_values.previous()):
                if line == menu_keys.current_line:
                    lcd.write_line('>>{0:<8}: {1:<8}'.format(k, v), line, 1)
                else:
                    lcd.write_line('{0:<8}: {1:<8}'.format(k, v), line, 3)
                line += 1
        elif rotary_encoder.select():   # go into change value mode
            key = menu_keys.items[menu_keys.current_line + menu_keys.shift - 1]
            value = menu_values.items[menu_keys.current_line + menu_keys.shift - 1]

            if not first_select:
                is_value_modified = not is_value_modified
                lcd.write_line('{0:<8}:>> {1:<8}'.format(key, value), menu_keys.current_line, 1)
            else:
                first_select = False

            time.sleep_ms(500)
            value_format = '{:<8}'
            start_time = time.ticks_ms()
            while not stop_signal and is_value_modified:
                rotary_value = rotary_encoder.value()
                if rotary_value != 0:
                    if key in ['T1', 'T2', 'T3','T4']:
                        value = int(value + rotary_value)     #type:ignore
                        if value < 0 or value >= 9999: value = 0
                elif rotary_encoder.select():

                    config[current_menu].update({key : value})
                    write_file(config_file)
                    load_file(config_file)

                    menu_keys.update(sorted(config[current_menu]))
                    menu_values.update([config[current_menu][k] for k in sorted(config[current_menu]) ])
                    is_value_modified = not is_value_modified
                    time.sleep_ms(300)
                
                elapsed = time.ticks_diff(time.ticks_ms(), start_time)
                if elapsed > 200:
                    lcd.write_line(value_format.format(value), menu_keys.current_line, 13)
                    start_time = time.ticks_ms()

            lcd.write_line('>>{0:<8}: {1:<8}'.format(key, value), menu_keys.current_line, 1)
    
    # go back to Configuration menu
    Configuration()

def Configuration():
    """Configuration main menu."""

    global stop_signal
    stop_signal = False     # TODO: This is not elequant, only stop_signal_handler should modify this variable.
    first_entry = True

    while not stop_signal:
        rotary_value = rotary_encoder.value()
        if first_entry:

            line = 1
            lcd.clear()
            for item in menu.show():
                if line == menu.current_line:
                    lcd.write_line('>>' + item.upper(), line, 1)
                else:
                    lcd.write_line(item.upper(), line, 5)
                line += 1
            first_entry = False
            time.sleep_ms(300)

        elif rotary_value > 0:
            line = 1
            lcd.clear()
            for item in menu.next():
                if line == menu.current_line:
                    lcd.write_line('>>' + item.upper(), line, 1)
                else:
                    lcd.write_line(item.upper(), line, 5)
                line += 1
        elif rotary_value < 0:
            line = 1
            lcd.clear()
            for item in menu.previous():
                if line == menu.current_line:
                    lcd.write_line('>>' + item.upper(), line, 1)
                else:
                    lcd.write_line(item.upper(), line, 5)
                line += 1
        elif rotary_encoder.select():
            # menu_fct[menu.current_line + menu.shift - 1]()
            config_menu(menu_fct[menu.current_line + menu.shift - 1])

######
Input['Stop'].irq(trigger=machine.Pin.IRQ_RISING, handler=stop_signal_handler)

def main():
    """Main function - start here"""

    initialize()

    while True:
        if not is_running:
            if (readPin('Close') or readPin('Open')) and not Output['Stop'].value():
                main_logic_loop()
            elif rotary_encoder.select():
                Configuration()
            
        if stop_signal:
            initialize()

        time.sleep_ms(50)

if __name__ == '__main__':
    main()