"""Le direto dos endpoints USB, sem o driver cdc_acm."""
import usb.core, usb.util, time, sys, os

dev = usb.core.find(idVendor=0xfff0, idProduct=0x0008)
if dev is None:
    sys.exit("dispositivo nao encontrado")

for cfg in dev:
    for intf in cfg:
        n = intf.bInterfaceNumber
        if dev.is_kernel_driver_active(n):
            dev.detach_kernel_driver(n)
            print(f"driver do kernel solto da interface {n}")

dev.set_configuration()
print("config aplicada")

# EP 0x82 = interrupt IN (notificacao CDC), EP 0x81 = bulk IN (dados)
for ep_addr, kind, size in ((0x82, 'interrupt', 8), (0x81, 'bulk', 64)):
    print(f"\n--- lendo EP {ep_addr:#04x} ({kind}) por 3s ---")
    t0 = time.time(); n = 0
    while time.time() - t0 < 3:
        try:
            data = dev.read(ep_addr, size, timeout=300)
            if data:
                n += len(data)
                print("  RX:", bytes(data).hex(' '))
        except usb.core.USBTimeoutError:
            pass
        except usb.core.USBError as e:
            print("  erro:", e); break
    print(f"  total: {n} bytes")

# tenta acordar com um DUML no bulk OUT
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import duml
print("\n--- enviando DUML no EP 0x03 e lendo EP 0x81 ---")
try:
    dev.write(0x03, duml.build(duml.addr(2,6), duml.addr(6,0), 1, 0x40, 0x00, 0x01), timeout=500)
    print("  escrita ok")
except usb.core.USBError as e:
    print("  escrita falhou:", e)
t0 = time.time(); n = 0
while time.time() - t0 < 3:
    try:
        data = dev.read(0x81, 64, timeout=300)
        if data:
            n += len(data); print("  RX:", bytes(data).hex(' '))
    except usb.core.USBTimeoutError:
        pass
    except usb.core.USBError as e:
        print("  erro:", e); break
print(f"  total: {n} bytes")
