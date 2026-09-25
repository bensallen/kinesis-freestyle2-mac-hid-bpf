# The payload is a BPF ELF object, not a native executable. Stripping or
# extracting debuginfo from it breaks BTF/CO-RE relocations.
%global debug_package %{nil}
%global __strip /bin/true
%global __brp_strip %{nil}
%global __brp_strip_comment_note %{nil}
%global __brp_strip_static_archive %{nil}

%{!?_udevhwdbdir: %global _udevhwdbdir %{_prefix}/lib/udev/hwdb.d}
%{!?_modprobedir: %global _modprobedir %{_prefix}/lib/modprobe.d}

%global bpfdir %{_prefix}/lib/firmware/hid/bpf
%global bpfobj 0010-Kinesis__Freestyle2-Mac.bpf.o

Name:           kinesis-freestyle2-mac-hid-bpf
Version:        1.0.0
Release:        1%{?dist}
Summary:        HID-BPF media key fixup for the Kinesis Freestyle2 for Mac

License:        GPL-2.0-only
URL:            https://github.com/bensallen/kinesis-freestyle2-mac-hid-bpf
Source0:        %{name}-%{version}.tar.gz

BuildRequires:  clang
BuildRequires:  bpftool
# Provides bpf/bpf_helpers.h and bpf/bpf_tracing.h
BuildRequires:  libbpf-devel
BuildRequires:  make
BuildRequires:  systemd-rpm-macros

# BPF objects are CO-RE and relocate against the running kernel's BTF, but
# HID-BPF struct_ops support is required at runtime (kernel >= 6.3).
Requires:       udev-hid-bpf
Requires:       systemd-udev
Requires(post): systemd-udev

# The object is built from the build host's BTF but is CO-RE relocatable, so
# it is not tied to a specific kernel build.
BuildArch:      noarch

%description
The Kinesis Freestyle2 for Mac (KB800HM) does not deliver media keys to
userspace on Linux. Its consumer control collection declares no Logical
Minimum/Maximum, so it inherits a 0..1 range from the preceding System
Control collection. The kernel then parses a 16-bit Array field with a
logical range of 0..1 and discards every consumer usage, since values such
as Volume Up (0x00E9) fall outside that range. The reports are visible on
hidraw but never reach the input layer.

This package ships a HID-BPF program that inserts the missing Logical
Minimum/Maximum into the report descriptor at probe time, making the media
keys work without a userspace daemon.

It also ships a hwdb keymap that corrects two further quirks. The brightness
keys send keyboard usages 0x69/0x6A, which the kernel maps to F14/F15 in the
Apple convention, so they are remapped to brightnessdown/brightnessup. The
transport keys send Fast Forward / Rewind rather than Scan Next / Previous
Track, which makes applications seek within a track instead of skipping, so
they are remapped to nextsong/previoussong.

It also blacklists hid-maltron. That driver claims the same 058F:9410
VID/PID but its report_fixup only fires on an exact match against the
106-byte Maltron L90 descriptor, so it binds the Kinesis and does nothing
while preventing hid-generic from handling it.

%prep
%autosetup

%build
%make_build BPF_OBJ=%{bpfobj}

%install
%make_install PREFIX=%{_prefix} BPF_OBJ=%{bpfobj}

%post
%{?udev_hwdb_update:%udev_hwdb_update}
%{!?udev_hwdb_update:systemd-hwdb update || :}
cat <<'EOF'

kinesis-freestyle2-mac-hid-bpf installed.

hid-maltron is now blacklisted. If it is currently loaded, either reboot or
run:

    modprobe -r hid_maltron

Then unplug and replug the keyboard for the BPF program to attach.

EOF

%postun
%{?udev_hwdb_update:%udev_hwdb_update}
%{!?udev_hwdb_update:systemd-hwdb update || :}

%files
%license LICENSE
%doc README.md
%{bpfdir}/%{bpfobj}
%{_udevhwdbdir}/81-hid-bpf-kinesis-freestyle2-mac.hwdb
%{_udevhwdbdir}/61-keyboard-kinesis-freestyle2-mac.hwdb
%{_modprobedir}/blacklist-hid-maltron.conf

%changelog
* Fri Sep 25 2026 Benjamin Allen <bsallen@alcf.anl.gov> - 1.0.0-1
- Initial package
- HID-BPF rdesc fixup inserting Logical Minimum/Maximum into the consumer
  collection so media keys reach the input layer
- Blacklist hid-maltron, whose report_fixup does not match this device
