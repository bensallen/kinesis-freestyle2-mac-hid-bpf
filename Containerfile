ARG BASE_IMAGE=registry.fedoraproject.org/fedora:44
FROM ${BASE_IMAGE}

ARG VERSION=1.0.0

RUN dnf -y install \
      bpftool \
      clang \
      libbpf-devel \
      make \
      rpm-build \
      rpmdevtools \
      systemd-rpm-macros \
    && dnf clean all

WORKDIR /root
RUN rpmdev-setuptree

COPY kinesis-freestyle2-mac-hid-bpf-${VERSION}.tar.gz /root/rpmbuild/SOURCES/
COPY kinesis-freestyle2-mac-hid-bpf.spec /root/rpmbuild/SPECS/

# vmlinux.h is generated from /sys/kernel/btf/vmlinux, which the container
# inherits from the host kernel. The resulting object is CO-RE and relocates
# against whatever kernel it is loaded on, so the build host's BTF only needs
# to contain the types the program references.
RUN rpmbuild -ba /root/rpmbuild/SPECS/kinesis-freestyle2-mac-hid-bpf.spec

RUN mkdir -p /output \
    && cp -v /root/rpmbuild/RPMS/*/*.rpm /root/rpmbuild/SRPMS/*.rpm /output/
