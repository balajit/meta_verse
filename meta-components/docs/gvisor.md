Absolutely. I'll consolidate the process into a team-ready runbook, including the important OrbStack-specific details, verification steps, and the mistakes/false starts to avoid.
Writing


gVisor on Apple Silicon Mac with OrbStack
Purpose
This document describes how to install and verify gVisor (runsc) on an Apple Silicon Mac, using OrbStack to provide an ARM64 Linux environment and Docker Engine.
The setup was validated on:

Apple Silicon M5 Mac
macOS 26.4
OrbStack
Ubuntu 26.04.1 LTS
ARM64 / aarch64
Docker Engine 29.7.2
containerd 2.3.4
gVisor release-20260817.0
The final architecture is:
                    Apple M5
                       │
                    macOS
                       │
                    OrbStack
                       │
              Ubuntu 26.04 ARM64 VM
                       │
                 Docker Engine
                       │
             ┌─────────┴─────────┐
             │                   │
           runc                runsc
             │                   │
       Normal containers    gVisor sandbox
                                 │
                                 ▼
                         Sandboxed container

1. Why OrbStack is needed
gVisor is a Linux sandbox. It does not run directly as a macOS runtime.
On an Apple Silicon Mac, the recommended approach is therefore:

macOS
  ↓
OrbStack
  ↓
Linux ARM64 VM
  ↓
Docker
  ↓
gVisor

The important distinction is that gVisor must be installed inside Linux, not directly into macOS.
2. Verify the Mac
From the normal macOS terminal:
uname -m

Expected:
arm64

Check macOS:
sw_vers

Verify Docker:
docker version
docker info

If Docker is using OrbStack, the Docker context will normally show:
Context: orbstack

3. Verify OrbStack
Check that OrbStack is running:
orb status

Expected:
Running

It is important to understand that:
orb shell

does not provide a shell into OrbStack's internal Docker VM.
Likewise, commands such as:

orb which docker
orb which containerd
orb which runsc

do not expose the Docker VM's internal binaries.
Do not attempt to install gVisor into OrbStack's managed Docker environment.

Instead, create a dedicated Linux VM.

4. Create an Ubuntu ARM64 VM
From macOS:
orb create ubuntu gvisor

Verify:
orb list

Expected output should contain something similar to:
NAME    STATE    DISTRO  VERSION   ARCH
gvisor  running  ubuntu  resolute  arm64

Enter the VM:
orb -m gvisor

Verify the architecture:
uname -m

Expected:
aarch64

Verify Ubuntu:
cat /etc/os-release

For this setup the result was:
PRETTY_NAME="Ubuntu 26.04.1 LTS"
VERSION_ID="26.04"
VERSION_CODENAME=resolute

At this point we have:
Apple M5
   ↓
OrbStack
   ↓
Ubuntu 26.04 ARM64

5. Install gVisor
Inside the Ubuntu VM:
sudo apt update
sudo apt upgrade -y

Install prerequisites:
sudo apt install -y \
  apt-transport-https \
  ca-certificates \
  curl \
  gnupg

Add the gVisor signing key:
curl -fsSL https://gvisor.dev/archive.key | \
  sudo gpg --dearmor -o /usr/share/keyrings/gvisor-archive-keyring.gpg

Add the gVisor repository:
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/gvisor-archive-keyring.gpg] https://storage.googleapis.com/gvisor/releases release main" | \
  sudo tee /etc/apt/sources.list.d/gvisor.list > /dev/null

Verify the Linux package architecture:
dpkg --print-architecture

Expected:
arm64

Install gVisor:
sudo apt update
sudo apt install -y runsc

Verify:
runsc --version

Example:
runsc version release-20260817.0
spec: 1.2.1

Verify the binary:
which runsc

Expected:
/usr/bin/runsc

6. Important: gVisor is a multi-file installation
Recent gVisor releases install more than just /usr/bin/runsc.
Check:

ls -la /usr/bin/runsc /usr/bin/gvisor-bin

The installation should contain:
/usr/bin/runsc
/usr/bin/gvisor-bin/

The gvisor-bin directory contains supporting binaries such as:
checkpointgofer
gvisor-sentry-prewarmer
gvisor_sentry
runsc-metric-server

Also verify the containerd shim:
dpkg -L runsc | grep -E 'runsc|gvisor-bin|containerd-shim'

You should see:
/usr/bin/containerd-shim-runsc-v1
/usr/bin/runsc
/usr/bin/gvisor-bin
...
/etc/containerd/runsc.toml

Do not move /usr/bin/runsc away from /usr/bin/gvisor-bin.
The package installation already puts the files in the correct locations.

7. Install Docker Engine inside the Ubuntu VM
The dedicated Ubuntu VM needs its own Docker Engine.
Install prerequisites:

sudo apt update
sudo apt install -y ca-certificates curl

Create the Docker keyring directory:
sudo install -m 0755 -d /etc/apt/keyrings

Install the Docker signing key:
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc

Set permissions:
sudo chmod a+r /etc/apt/keyrings/docker.asc

Add the Docker repository:
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

Update:
sudo apt update

Install Docker:
sudo apt install -y \
  docker-ce \
  docker-ce-cli \
  containerd.io \
  docker-buildx-plugin \
  docker-compose-plugin

Enable and start Docker:
sudo systemctl enable --now docker

Verify:
sudo systemctl status docker --no-pager

Expected:
Active: active (running)

Verify Docker:
sudo docker version

8. Allow the normal user to run Docker
Add the current user to the Docker group:
sudo usermod -aG docker "$USER"

Exit the VM:
exit

Re-enter it:
orb -m gvisor

Now test:
docker version

Docker should work without sudo.
9. Verify the Docker environment
Run:
docker version

The validated environment was:
Docker Engine - Community
Version: 29.7.2
OS/Arch: linux/arm64

Check the storage/runtime configuration:
docker info | grep -E "Storage Driver|Docker Root Dir|Runtimes|Default Runtime"

The validated environment initially showed:
Storage Driver: overlayfs
Runtimes: io.containerd.runc.v2 runc
Default Runtime: runc
Docker Root Dir: /var/lib/docker

Check containerd:
containerd --version

Validated version:
containerd containerd v2.3.4

10. Configure Docker to use gVisor
Run:
sudo runsc install

This creates/updates:
/etc/docker/daemon.json

The resulting configuration was:
{
    "runtimes": {
        "runsc": {
            "path": "/usr/bin/runsc"
        }
    }
}

Before restarting Docker, inspect it:
sudo cat /etc/docker/daemon.json

If the file already contains other Docker configuration, make sure it is preserved.
11. Restart Docker
Restart:
sudo systemctl restart docker

Verify that Docker recognizes gVisor:
docker info | grep -E "Runtimes|Default Runtime"

Expected:
Runtimes: io.containerd.runc.v2 runc runsc
Default Runtime: runc

This means:
runc remains the default.
runsc is available when explicitly requested.
This is the recommended configuration for a gradual migration.
12. Run the first gVisor container
Run:
docker run --rm --runtime=runsc hello-world

Expected:
Hello from Docker!

The important part is:
--runtime=runsc

This explicitly tells Docker to launch the container using gVisor.
13. Verify that gVisor is really running
A successful hello-world is useful, but we should verify the sandbox itself.
Run:

docker run --rm --runtime=runsc alpine uname -a

The validated result was:
Linux b16281e629b9 4.19.0-gvisor #1 SMP Sun Jan 10 15:06:54 PST 2016 aarch64 Linux

The important part is:
4.19.0-gvisor

The container is seeing the gVisor kernel interface rather than the host's Ubuntu kernel.
14. Verify with gVisor dmesg
Run:
docker run --rm --runtime=runsc alpine dmesg | head -20

The validated result included:
[   0.000000] Starting gVisor...
[   0.250098] Preparing for the zombie uprising...
[   0.410239] Consulting tar man page...
[   0.756254] Creating cloned children...
[   1.155185] Searching for socket adapter...
[   1.157705] Rewriting the kernel in Rust...
[   1.449951] Checking naughty and nice process list...
[   1.795467] Letting the watchdogs out...
[   1.892694] Politicking the oom killer...
[   2.238780] Mounting deweydecimalfs...
[   2.706948] Verifying that no non-zero bytes made their way into /dev/zero...
[   2.831418] Ready!

This provides strong confirmation that the container is actually running inside the gVisor sandbox.
15. Verify a real Python container
Test Python under gVisor:
docker run --rm --runtime=runsc python:3.13-slim \
    python -c "import platform; print(platform.platform())"

The validated result was:
Linux-4.19.0-gvisor-aarch64-with-glibc2.41

This confirms that a real Python ARM64 container can execute successfully under gVisor.
16. Running normal versus gVisor containers
Normal container:
docker run --rm alpine uname -a

gVisor container:
docker run --rm --runtime=runsc alpine uname -a

Conceptually:
Normal:

Application
    ↓
Container
    ↓
Linux kernel


gVisor:

Application
    ↓
Container
    ↓
gVisor Sentry
    ↓
Linux kernel

gVisor's Sentry implements the kernel interface exposed to applications inside the sandbox.
17. Docker Compose
A Compose service can explicitly request gVisor:
services:
  app:
    build: .
    runtime: runsc

Then:
docker compose up

Only the service specifying:
runtime: runsc

will use gVisor.
This allows normal and sandboxed workloads to coexist.

For example:

services:

  normal-service:
    image: nginx:latest

  sandboxed-service:
    build: .
    runtime: runsc

18. Recommended runtime strategy
Do not make gVisor the Docker default initially.
Keep:

Default Runtime: runc

and explicitly use:
--runtime=runsc

for workloads that need sandboxing.
This provides:

Docker
│
├── runc
│   ├── databases
│   ├── development services
│   └── trusted workloads
│
└── runsc
    ├── untrusted code
    ├── Python execution
    ├── plugins
    └── workloads requiring additional isolation

This makes migration and troubleshooting significantly easier.
19. Things to test before migrating an application
gVisor intentionally does not implement every Linux kernel interface.
Before migrating a production workload, test:

Python subprocesses
multiprocessing
filesystem operations
bind mounts
named volumes
networking
DNS
TCP/UDP behavior
/proc
/sys
Linux capabilities
signals
native Python extensions
database drivers
packages requiring unusual syscalls
FUSE
eBPF
ptrace
low-level networking
A conventional Python web application will often work without changes, but workloads depending on unusual kernel functionality may require adjustments.
20. Troubleshooting checklist
Docker cannot connect
Check:
sudo systemctl status docker --no-pager

Then:
docker info

runsc is missing from Docker
Check:
docker info | grep -E "Runtimes|Default Runtime"

If runsc isn't listed:
sudo cat /etc/docker/daemon.json

It should contain:
{
    "runtimes": {
        "runsc": {
            "path": "/usr/bin/runsc"
        }
    }
}

Then:
sudo systemctl restart docker

runsc itself is missing
Check:
which runsc
runsc --version

Expected:
/usr/bin/runsc

gVisor supporting binaries are missing
Check:
ls -la /usr/bin/gvisor-bin

The directory should contain the supporting gVisor executables.
Docker permission errors
If Docker only works with sudo:
sudo usermod -aG docker "$USER"

Then exit and re-enter the VM.
21. Important OrbStack distinction
There are two Docker/Linux environments involved:
macOS
 │
 └── OrbStack-managed Docker environment
       └── Existing Docker containers


macOS
 │
 └── OrbStack "gvisor" Linux VM
       ├── Ubuntu
       ├── Docker Engine
       └── gVisor

The gVisor installation described in this document is performed in the second environment.
This avoids modifying OrbStack's managed Docker engine and prevents accidentally disrupting existing containers.

22. Final verification commands
After installation, the following commands provide a quick health check:
uname -m

Expected:
aarch64

runsc --version

Expected:
runsc version release-20260817.0

docker version

Expected:
OS/Arch: linux/arm64

docker info | grep -E "Runtimes|Default Runtime"

Expected:
Runtimes: io.containerd.runc.v2 runc runsc
Default Runtime: runc

Then:
docker run --rm --runtime=runsc alpine uname -a

Expected to contain:
gvisor

Finally:
docker run --rm --runtime=runsc alpine dmesg | head

Expected to contain:
Starting gVisor...

If all of these work, gVisor is successfully installed and functioning.
23. Reference documentation
gVisor installation: https://gvisor.dev/docs/user_guide/install/
gVisor Docker quick start: https://gvisor.dev/docs/user_guide/quick_start/docker/
gVisor architecture: https://gvisor.dev/docs/architecture_guide/architecture/
Docker Engine installation on Ubuntu: https://docs.docker.com/engine/install/ubuntu/
24. Summary
The critical lesson from this setup is:
Do not try to install gVisor directly into macOS or OrbStack's managed Docker environment.

Instead:

1. Apple M5 Mac
       ↓
2. OrbStack
       ↓
3. Create Ubuntu ARM64 VM
       ↓
4. Install gVisor inside Ubuntu
       ↓
5. Install Docker Engine inside Ubuntu
       ↓
6. Register runsc with Docker
       ↓
7. Run containers with --runtime=runsc
       ↓
8. Verify using uname and dmesg

The final working command is:
docker run --rm --runtime=runsc python:3.13-slim \
    python -c "import platform; print(platform.platform())"

with the expected result:
Linux-4.19.0-gvisor-aarch64-with-glibc2.41

At that point, the Python application is running on ARM64 with the gVisor sandbox between the application and the underlying Linux kernel.
This should be suitable as a team runbook. One thing I'd recommend before sharing it broadly: pin the Ubuntu/gVisor/Docker versions in your team's setup documentation or provisioning script, so future installations don't silently pick up incompatible versions.