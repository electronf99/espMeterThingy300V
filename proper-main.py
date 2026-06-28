
# Import necessary modules
from machine import PWM, Pin, I2C, disable_irq, enable_irq
import machine
import bluetooth
from ble_simple_peripheral import BLESimplePeripheral
from time import sleep
from msgpack_decoder import decode
import micropython
import neopixel


PIN_ONBOARD = 10 
PIXEL_COUNT = 1
np = neopixel.NeoPixel(machine.Pin(PIN_ONBOARD), PIXEL_COUNT)

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
    x=int(x/65536*100)
    for i in range(len(pos_table) - 1):
        if pos_table[i] <= x <= pos_table[i+1]:
            f = (x - pos_table[i]) / (pos_table[i+1] - pos_table[i])
            return int(pwm_table[i] + f * (pwm_table[i+1] - pwm_table[i]))

    return 0
    
micropython.alloc_emergency_exception_buf(256)  # safer error text in IRQ

# ------------------------
# PWM (meters)
# ------------------------
frequency = 2000
m1_volt_pin = machine.Pin(1)
m1_volt_meter = PWM(m1_volt_pin)
m1_volt_meter.freq(frequency)
m1_volt_meter.duty_u16(0)

def pprint(obj, indent=0):
    spacing = '  ' * indent
    if isinstance(obj, dict):
        for k, v in obj.items():
            print(f"{spacing}{k}:")
            pprint(v, indent + 1)
    elif isinstance(obj, list):
        for item in obj:
            pprint(item, indent + 1)
    else:
        print(f"{spacing}{obj}")

# ------------------------
# State / counters
# ------------------------
packet_count = 0
fail_count   = 0
reboots      = 0  # unused unless you add your reboot counter
heap_free_hwm = 0

# ------------------------
# Safe message assembly (pre-allocated)
# ------------------------
# TUNE: choose a maximum assembled message size you expect
_MAX_MSG = 8192           # bytes
_ASSEM   = bytearray(_MAX_MSG)
_ASSEM_LEN = 0            # how many bytes copied
_ASSEM_MSG_ID = -1        # last msg_id seen (optional)
_ASSEM_EXPECTED_SEQ = 0   # expected next seq
_ASSEM_TOTAL = 0          # total packets expected
_MESSAGE_READY = 0        # 0/1 flag
_MESSAGE_LEN = 0
_SCHEDULE_PENDING = 0     # avoid flooding scheduler

# Optional: strip trailing zero padding without allocations
def _trimmed_len(view):
    # walk backward for b'\x00' pad
    n = len(view)
    while n > 0 and view[n-1] == 0:
        n -= 1
    return n

def _reset_assembly(total, msg_id):
    global _ASSEM_LEN, _ASSEM_MSG_ID, _ASSEM_EXPECTED_SEQ, _ASSEM_TOTAL
    _ASSEM_LEN = 0
    _ASSEM_MSG_ID = msg_id
    _ASSEM_EXPECTED_SEQ = 0
    _ASSEM_TOTAL = total

def _commit_message():
    """Mark the currently assembled bytes as a complete message."""
    global _MESSAGE_READY, _MESSAGE_LEN
    _MESSAGE_LEN = _ASSEM_LEN
    _MESSAGE_READY = 1

def _schedule_process():
    global _SCHEDULE_PENDING
    if not _SCHEDULE_PENDING:
        _SCHEDULE_PENDING = 1
        micropython.schedule(_process_message, 0)

# -------------
# on_rx callback (IRQ/soft-IRQ context! Keep it tiny & no heavy allocs)
# -------------
def on_rx(data: bytes):

    global packet_count, fail_count
    global _ASSEM_LEN, _ASSEM_EXPECTED_SEQ, _ASSEM_TOTAL, _ASSEM_MSG_ID
    global _MESSAGE_READY

    if not data or len(data) < 3:
        return

    seq         = data[0]
    total_pkts  = data[1]
    msg_id      = data[2]

    # If first packet or new message id, reset assembly
    if seq == 0 or msg_id != _ASSEM_MSG_ID:
        _reset_assembly(total_pkts, msg_id)

    # drop if seq is not what we expect (out-of-order)
    if seq != _ASSEM_EXPECTED_SEQ:
        # out-of-sequence; restart assembly for robustness
        _reset_assembly(total_pkts, msg_id)
        # attempt to treat this packet as seq 0
        if seq != 0:
            return

    # Copy payload into pre-allocated buffer
    # Use memoryview to avoid creating new objects
    src  = memoryview(data)
    pay  = src[3:]  # payload slice (view)
    # Trim trailing zeros without allocating
    n = _trimmed_len(pay)
    if n:
        # bounds check against _MAX_MSG
        if _ASSEM_LEN + n > _MAX_MSG:
            # message too large; reset and drop
            _reset_assembly(total_pkts, msg_id)
            return
        _ASSEM[_ASSEM_LEN:_ASSEM_LEN+n] = pay[:n]
        _ASSEM_LEN += n

    _ASSEM_EXPECTED_SEQ += 1

    # If last packet, mark ready and schedule processing
    if (seq + 1) == total_pkts:
        packet_count += 1
        fail_count = 0
        _commit_message()
        _schedule_process()

# -------------
# Run the needle down gently
# -------------
def run_meter_down():
    pwm = m1_volt_meter.duty_u16()
    print(f"pwm={pwm}")
    while pwm > 1000:
        pwm -= 1000
        print(f"running down: {pwm}")
        m1_volt_meter.duty_u16(pwm)
        sleep(0.05)
    
    m1_volt_meter.duty_u16(int(0))

# -------------
# Scheduled message processor (runs in main VM context)
# -------------
def _process_message(_arg):
    global _MESSAGE_READY, _MESSAGE_LEN, _SCHEDULE_PENDING, fail_count, heap_free_hwm
    try:
        # Atomically snapshot message length and clear READY
        state = disable_irq()
        try:
            ready = _MESSAGE_READY
            msg_len = _MESSAGE_LEN
            _MESSAGE_READY = 0
        finally:
            enable_irq(state)

        if not ready or msg_len <= 0:
            return

        # Decode (safe to allocate here)
        msg_bytes = bytes(memoryview(_ASSEM)[:msg_len])
        message = decode(msg_bytes)

        try:

            print(message)
            # Clamp and drive meter 1
            m1_val = message["m"] # type: ignore
            #m1_volt_meter.duty_u16(32767)
            if m1_val is not None:
                pwm = get_pwm(int(m1_val))
                #m1_val = min(0, int(m1_val))
                m1_volt_meter.duty_u16(int(pwm))

        except Exception as e:
            # If message lacks fields, keep running
            print("Process msg error:", e)

    finally:
        _SCHEDULE_PENDING = 0  # allow another schedule

# ------------------------
# Main
# ------------------------
if __name__ == "__main__":
    in_failure = 0
    has_connected = False

    #oled.poweroff()

    try:

        ble = bluetooth.BLE()
      
        print(">>------------")
        sp = BLESimplePeripheral(ble, "300V")
        print("------------<<")
        


        mac = ble.config('mac')[1]
        mac_str = (':'.join('%02X' % b for b in mac))

        # Register on_write ONCE (BLESimplePeripheral queues it internally)
        sp.on_write(on_rx)
        icon = 0
        

        while True:
            if sp.is_connected():
                has_connected = True
                np[0] = (80, 255, 0)
                np.write()
                #run_meter_down()
                sleep(1)
                fail_count -= 1
                if fail_count < -10:
                    run_meter_down()

            else:
                in_failure += 1
                fail_count += 1

                #print(f"Not Connected Fail Count {fail_count}")
                if fail_count == 5:
                    np[0] = (000, 000, 255)
                    np.write()
                    run_meter_down()

    except KeyboardInterrupt:
        print("Ctrl-C")
        run_meter_down()
        sleep(0.1)
        np[0] = (0,0,0)
        np.write()
    finally:
        run_meter_down()
        print("Ctrl-C final")
