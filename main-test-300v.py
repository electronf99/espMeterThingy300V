# Import necessary modules
from machine import PWM, Pin, I2C
import machine
import time
import neopixel


PIN_ONBOARD = 10 
PIXEL_COUNT = 1

pos_table = [
    0, 5,10,15,20,
    25,30,35,40,45,
    50,55,60,65,70,
    75,80,85,90,95,
    100
]

pwm_table = [
      0,  9500, 18400, 22000, 24900,
  27000, 29250, 31000, 32500, 34000,
  35750, 38000, 40150, 43000, 45500,
  48000, 50850, 54000, 57400, 61000,
  65000
]

def get_pwm(x):
    for i in range(len(pos_table) - 1):
        if pos_table[i] <= x <= pos_table[i+1]:
            f = (x - pos_table[i]) / (pos_table[i+1] - pos_table[i])
            return int(pwm_table[i] + f * (pwm_table[i+1] - pwm_table[i]))
    
    if x < 0:
        return 0
    return 65000


np = neopixel.NeoPixel(machine.Pin(PIN_ONBOARD), PIXEL_COUNT)

np[0] = (100, 255, 1)
np.write()

frequency = 500
duty=0


m1_volt_pin = machine.Pin(1)
m1_volt_meter = PWM(m1_volt_pin)
m1_volt_meter.freq(frequency)
print(duty)

dir=0
inc = 1
percentage = 0
try:
    while 1==1:
        # voltage = float(input("voltage: "))
        # duty=int(60000*(voltage/300))
        #percentage = float(input("percent: "))
        
        if percentage == 100:
            inc = -1
        if percentage == 0:
            inc = 1
        
        percentage = percentage + inc
        # percentage = 99

        duty = get_pwm(percentage)# / 100)  # * 63000
        
        #duty = int(input(duty))
        print(f"{duty} {inc} {percentage}")

        m1_volt_meter.duty_u16(int(duty))
        print("*******************")

        
        time.sleep(0.02)


except KeyboardInterrupt:
    print("Ctrl-C Pressed")
finally:
    print("Setting to neutral")
    m1_volt_meter.duty_u16(int(0))