// SPDX-License-Identifier: GPL-2.0-only
/*
 * Kinesis Freestyle2 for Mac (KB800HM) — consumer control descriptor fixup.
 *
 * The keyboard shares Alcor's 058F:9410 VID/PID with the Maltron L90, so
 * hid-maltron claims it, but that driver's report_fixup is gated on an exact
 * 106-byte memcmp against the Maltron descriptor. This device presents a
 * different 53-byte descriptor, so the fixup never fires and the device falls
 * through unpatched.
 *
 * The Consumer collection (Report ID 3) declares no Logical Minimum/Maximum,
 * so it inherits 15 00 / 25 01 (0..1) from the Sys Control collection above.
 * The kernel then parses a 16-bit Array field with a logical range of 0..1 and
 * drops every media usage (Volume Up is 0x00E9) in hid_input_field() because
 * the value falls outside that range. The reports do arrive — they are visible
 * on hidraw — but they never reach the input layer.
 *
 * Insert an explicit Logical Minimum (0) / Logical Maximum (0x023C) into the
 * Report ID 3 collection so the range matches the declared Usage Maximum.
 *
 * Original descriptor (53 bytes):
 *
 *  0: 0x05, 0x01,        // Usage Page (Generic Desktop)
 *  2: 0x09, 0x80,        // Usage (Sys Control)
 *  4: 0xA1, 0x01,        // Collection (Application)
 *  6: 0x85, 0x02,        //   Report ID (2)
 *  8: 0x75, 0x01,        //   Report Size (1)
 * 10: 0x95, 0x01,        //   Report Count (1)
 * 12: 0x15, 0x00,        //   Logical Minimum (0)
 * 14: 0x25, 0x01,        //   Logical Maximum (1)
 * 16: 0x09, 0x81,        //   Usage (Sys Power Down)
 * 18: 0x81, 0x06,        //   Input (Data,Var,Rel)
 * 20: 0x09, 0x82,        //   Usage (Sys Sleep)
 * 22: 0x81, 0x06,        //   Input (Data,Var,Rel)
 * 24: 0x09, 0x83,        //   Usage (Sys Wake Up)
 * 26: 0x81, 0x06,        //   Input (Data,Var,Rel)
 * 28: 0x75, 0x05,        //   Report Size (5)
 * 30: 0x81, 0x01,        //   Input (Cnst,Arr,Abs)
 * 32: 0xC0,              // End Collection
 * 33: 0x05, 0x0C,        // Usage Page (Consumer)
 * 35: 0x09, 0x01,        // Usage (Consumer Control)
 * 37: 0xA1, 0x01,        // Collection (Application)
 * 39: 0x85, 0x03,        //   Report ID (3)      <- insert 15 00 26 3C 02 here
 * 41: 0x95, 0x01,        //   Report Count (1)
 * 43: 0x75, 0x10,        //   Report Size (16)
 * 45: 0x19, 0x00,        //   Usage Minimum (0)
 * 47: 0x2A, 0x3C, 0x02,  //   Usage Maximum (0x023C)
 * 50: 0x81, 0x00,        //   Input (Data,Arr,Abs)
 * 52: 0xC0               // End Collection
 */

#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>
#include <linux/errno.h>

#define VID_ALCOR		0x058F
#define PID_KINESIS_FS2_MAC	0x9410

#define RDESC_SIZE		53
#define RDESC_SIZE_FIXED	58

/* Offset of the Report ID (3) item in the Consumer collection. */
#define RID3_OFFSET		39
/* Everything from Report Count (1) to End Collection. */
#define TAIL_OFFSET		41
#define TAIL_LEN		(RDESC_SIZE - TAIL_OFFSET)
#define PATCH_LEN		5

#define HID_MAX_DESCRIPTOR_SIZE	4096

#define BUS_USB			0x03
#define HID_GROUP_GENERIC	0x0001

#define HID_BPF_RDESC_FIXUP	"struct_ops/hid_rdesc_fixup"
#define HID_BPF_OPS(name)	SEC(".struct_ops.link") struct hid_bpf_ops name

#define COMBINE1(X, Y) X ## Y
#define COMBINE(X, Y) COMBINE1(X, Y)

#define HID_DEVICE(b, g, ven, prod)	\
	struct {			\
		__uint(name, 0);	\
		__uint(bus, (b));	\
		__uint(group, (g));	\
		__uint(vid, (ven));	\
		__uint(pid, (prod));	\
	} COMBINE(_entry, __LINE__)

#define HID_BPF_CONFIG(...) union { __VA_ARGS__; } _device_ids SEC(".hid_bpf_config")

struct hid_bpf_probe_args {
	unsigned int hid;
	unsigned int rdesc_size;
	unsigned char rdesc[HID_MAX_DESCRIPTOR_SIZE];
	int retval;
};

extern __u8 *hid_bpf_get_data(struct hid_bpf_ctx *ctx,
			      unsigned int offset,
			      const size_t __sz) __ksym;

HID_BPF_CONFIG(
	HID_DEVICE(BUS_USB, HID_GROUP_GENERIC, VID_ALCOR, PID_KINESIS_FS2_MAC)
);

SEC(HID_BPF_RDESC_FIXUP)
int BPF_PROG(hid_rdesc_fixup_kinesis_fs2_mac, struct hid_bpf_ctx *hctx)
{
	__u8 *data = hid_bpf_get_data(hctx, 0 /* offset */, HID_MAX_DESCRIPTOR_SIZE);
	int i;

	if (!data)
		return 0; /* EPERM check */

	/*
	 * Only touch the interface that carries the Consumer collection.
	 * Interface 0 (the plain keyboard) has a different descriptor and is
	 * left alone.
	 */
	if (data[RID3_OFFSET] != 0x85 || data[RID3_OFFSET + 1] != 0x03)
		return 0;

	/* Shift the tail right by PATCH_LEN, back to front. */
	for (i = TAIL_LEN - 1; i >= 0; i--)
		data[TAIL_OFFSET + PATCH_LEN + i] = data[TAIL_OFFSET + i];

	/* Logical Minimum (0), Logical Maximum (0x023C) */
	data[TAIL_OFFSET + 0] = 0x15;
	data[TAIL_OFFSET + 1] = 0x00;
	data[TAIL_OFFSET + 2] = 0x26;
	data[TAIL_OFFSET + 3] = 0x3C;
	data[TAIL_OFFSET + 4] = 0x02;

	return RDESC_SIZE_FIXED;
}

HID_BPF_OPS(kinesis_fs2_mac) = {
	.hid_rdesc_fixup = (void *)hid_rdesc_fixup_kinesis_fs2_mac,
};

SEC("syscall")
int probe(struct hid_bpf_probe_args *ctx)
{
	/*
	 * Bind only to the consumer-control interface. Interface 0 shares the
	 * same VID/PID but has a 65-byte keyboard descriptor.
	 */
	if (ctx->rdesc_size != RDESC_SIZE ||
	    ctx->rdesc[RID3_OFFSET] != 0x85 ||
	    ctx->rdesc[RID3_OFFSET + 1] != 0x03) {
		ctx->retval = -EINVAL;
		return 0;
	}

	ctx->retval = 0;
	return 0;
}

char _license[] SEC("license") = "GPL";
