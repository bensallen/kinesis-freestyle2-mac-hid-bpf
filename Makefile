NAME     := kinesis-freestyle2-mac-hid-bpf
BPF_OBJ  := 0010-Kinesis__Freestyle2-Mac.bpf.o
BPF_SRC  := src/Kinesis__Freestyle2-Mac.bpf.c
VMLINUX  := src/vmlinux.h

HWDB     := hwdb.d/81-hid-bpf-kinesis-freestyle2-mac.hwdb
MODPROBE := modprobe.d/blacklist-hid-maltron.conf

CLANG    ?= clang
BPFTOOL  ?= bpftool
ARCH     := $(shell uname -m | sed -e 's/x86_64/x86/' -e 's/aarch64/arm64/')

DESTDIR  ?=
PREFIX   ?= /usr
BPFDIR   := $(PREFIX)/lib/firmware/hid/bpf
HWDBDIR  := $(PREFIX)/lib/udev/hwdb.d
MODDIR   := $(PREFIX)/lib/modprobe.d

CFLAGS := -g -O2 -Wall -Wno-missing-declarations \
	  -target bpf -D__TARGET_ARCH_$(ARCH) -Isrc

all: $(BPF_OBJ)

# Generated from the running kernel's BTF. Override BTF= to build against a
# different kernel.
BTF ?= /sys/kernel/btf/vmlinux

$(VMLINUX):
	$(BPFTOOL) btf dump file $(BTF) format c > $@

$(BPF_OBJ): $(BPF_SRC) $(VMLINUX)
	$(CLANG) $(CFLAGS) -c $< -o $@

install: $(BPF_OBJ)
	install -D -m 0644 $(BPF_OBJ)  $(DESTDIR)$(BPFDIR)/$(BPF_OBJ)
	install -D -m 0644 $(HWDB)     $(DESTDIR)$(HWDBDIR)/$(notdir $(HWDB))
	install -D -m 0644 $(MODPROBE) $(DESTDIR)$(MODDIR)/$(notdir $(MODPROBE))

uninstall:
	rm -f $(DESTDIR)$(BPFDIR)/$(BPF_OBJ)
	rm -f $(DESTDIR)$(HWDBDIR)/$(notdir $(HWDB))
	rm -f $(DESTDIR)$(MODDIR)/$(notdir $(MODPROBE))

inspect: $(BPF_OBJ)
	udev-hid-bpf inspect $(BPF_OBJ)

# Load against the live device without installing anything.
test: $(BPF_OBJ)
	udev-hid-bpf add --replace - $(CURDIR)/$(BPF_OBJ)

clean:
	rm -f $(BPF_OBJ) $(VMLINUX)

.PHONY: all install uninstall inspect test clean
