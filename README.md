# kinesis-freestyle2-mac-hid-bpf

Media keys for the Kinesis Freestyle2 for Mac (KB800HM) on Linux, via HID-BPF.

## The problem

The keyboard's media keys do nothing. They produce no input events, in any
desktop environment, with no error logged.

The reports *are* being sent. They are visible on hidraw:

```
$ sudo cat /dev/hidraw7 | xxd     # press Volume Up
00000000: 03e9 00
```

But nothing reaches the input layer:

```
$ sudo evtest /dev/input/event11  # "... Consumer Control"
(silence)
```

## Root cause

The consumer control interface presents this report descriptor:

```
05 01        Usage Page (Generic Desktop)
09 80        Usage (Sys Control)
A1 01        Collection (Application)
85 02          Report ID (2)
75 01          Report Size (1)
95 01          Report Count (1)
15 00          Logical Minimum (0)      <-- scope leaks into the next collection
25 01          Logical Maximum (1)      <--
09 81          Usage (Sys Power Down)
81 06          Input (Data,Var,Rel)
09 82          Usage (Sys Sleep)
81 06          Input (Data,Var,Rel)
09 83          Usage (Sys Wake Up)
81 06          Input (Data,Var,Rel)
75 05          Report Size (5)
81 01          Input (Cnst,Arr,Abs)
C0           End Collection
05 0C        Usage Page (Consumer)
09 01        Usage (Consumer Control)
A1 01        Collection (Application)
85 03          Report ID (3)
95 01          Report Count (1)         <-- no Logical Minimum/Maximum here
75 10          Report Size (16)
19 00          Usage Minimum (0)
2A 3C 02       Usage Maximum (0x023C)
81 00          Input (Data,Arr,Abs)
C0           End Collection
```

The Consumer collection never declares Logical Minimum/Maximum. Per the HID
spec these are global items, so the collection inherits `15 00 / 25 01`
(0..1) from the Sys Control collection above it.

The kernel therefore parses a 16-bit Array field with a logical range of
0..1. When Volume Up (`0x00E9`) arrives, `hid_input_field()` sees a value far
outside that range and drops it. Every media usage is discarded after a
successful parse, which is why there is no error anywhere.

The fix is to give the collection a logical range matching its declared usage
range: `Logical Minimum (0)` / `Logical Maximum (0x023C)`.

## Why hid-maltron does not fix it

The keyboard uses Alcor's `058F:9410`, shared with the Maltron L90. The
in-tree `hid-maltron` driver claims that VID/PID and exists to patch exactly
this class of bug — its patched descriptor comments even mark the two changed
lines as the logical min/max. But its fixup is gated on an exact match:

```c
if (*rsize == sizeof(maltron_rdesc_o) &&
    !memcmp(maltron_rdesc_o, rdesc, sizeof(maltron_rdesc_o)))
```

The Maltron descriptor is 106 bytes. This device's is 53. The size check
fails immediately, the fixup returns the descriptor untouched, and the driver
binds the device without doing anything — while keeping `hid-generic` away
from it.

So this package blacklists `hid-maltron` and applies the fixup via HID-BPF
instead.

`hid-apple` does not help either: its `report_fixup` is gated on quirks like
`APPLE_RDESC_JIS`, and binding via `new_id` passes `driver_data = 0`. It
cannot alter logical min/max.

## Requirements

- Kernel with `CONFIG_HID_BPF=y` and `CONFIG_DEBUG_INFO_BTF=y` (6.3+)
- `udev-hid-bpf`
- To build: `clang`, `bpftool`, `make`

## Install

From the RPM:

```bash
sudo dnf install ./kinesis-freestyle2-mac-hid-bpf-1.0.0-1.fc44.noarch.rpm
sudo modprobe -r hid_maltron    # if already loaded, else reboot
```

Then unplug and replug the keyboard.

From source:

```bash
make
sudo make install
sudo systemd-hwdb update
sudo udevadm control --reload
```

## Verify

`/sys/.../report_descriptor` is **not** a useful check — it exposes
`hdev->dev_rdesc`, the *original* descriptor. The fixed-up one lives in
`hdev->rdesc` and is never exported, so that file reads 53 bytes either way.

Check that the program is loaded:

```bash
sudo bpftool struct_ops list | grep kinesis
```

Check `dmesg` for a double registration of the consumer interface. HID-BPF
probes the device, attaches, then re-probes:

```
input: ... Consumer Control as .../0003:058F:9410.000C/input/input35
hid-generic 0003:058F:9410.000C: input,hidraw6: ...
input: ... Consumer Control as .../0003:058F:9410.000C/input/input37
hid-generic 0003:058F:9410.000C: input,hidraw6: ...
```

Interface 0 (the plain keyboard) should register only once — the BPF
`probe()` rejects it.

Then test the keys:

```bash
sudo evtest    # pick the "Consumer Control" device
```

## Testing without installing

```bash
make
sudo make test
```

This loads the object against the live device via `udev-hid-bpf add
--replace`. Replug the keyboard to revert.
