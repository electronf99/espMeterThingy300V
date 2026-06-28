# Import necessary modules
from machine import PWM, Pin, I2C
import machine
import time


frequency = 500
duty=0

m1_volt_pin = machine.Pin(1)
m1_volt_meter = PWM(m1_volt_pin)
m1_volt_meter.freq(frequency)
print(duty)

dir=0
inc = 100
try:
    while 1==1:
        print(duty)
        m1_volt_meter.duty_u16(int(duty))
        print("*******************")

        time.sleep(0.05)
        print(duty)
        if(dir==0):
            duty += inc
        if(dir==-1):
            duty -= inc
        
        if duty > 50000:
            dir=-1
        if duty < 1000:
            dir=0

except KeyboardInterrupt:
    print("Ctrl-C Pressed")
finally:
    print("Setting to neutral")
    m1_volt_meter.duty_u16(32768)
    time.sleep(1)
    m1_volt_meter.duty_u16(32768)
