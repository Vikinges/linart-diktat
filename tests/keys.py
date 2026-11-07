import keyboard, time, sys
for n in ("right ctrl", "ctrl", "strg", "strg-rechts", "right control"):
    try:
        print("map", repr(n), "->", keyboard.key_to_scan_codes(n), flush=True)
    except Exception as e:
        print("map", repr(n), "-> ERROR", e, flush=True)
seen = []
def h(e):
    seen.append((e.event_type, e.name, e.scan_code, getattr(e, "is_keypad", None)))
    print("EVENT", e.event_type, repr(e.name), e.scan_code, flush=True)
keyboard.hook(h)
time.sleep(float(sys.argv[1]) if len(sys.argv) > 1 else 25)
print("total events:", len(seen), flush=True)
