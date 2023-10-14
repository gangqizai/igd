## Intel 核显直通 optionROM


### 简介
  - 本ROM为Intel 10-13核显直通PCI optionROM, 搭配OVMF可以实现虚拟机启动,显示器 HDMI/DP 输出画面, HDMI/DP声音正常工作
  - 本ROM使用简单,无需修改或定制OVMF,使用PVE自带即可!
  - 虚拟机启动无花屏，蓝屏。


### 使用方法:

+ 本ROM 需要使用两个rom文件:
  - 核显直通 OptionROM: **gen12_igd.rom**   --各平台基本通用
  - GOP ROM:  --- 根据不同核显平台选择相应rom文件，见下表：

GOP ROM 文件名         | 适用CPU平台
----------------------|----------------------------
gen12_gop.rom         | Intel 11-13代 酷睿 
5105_gop.rom          | N5105 / N5095
8505_gop.rom          | 8505
n100_gop.rom          | N100

  - 大家根据主机的CPU选用相应GOP ROM，选用错误GOP ROM功能导致无启动画面

+ 把这两个rom file copy to /use/share/kvm/
+ 因为使用两个rom文件，conf配置文件中，一个rom文件加在显卡，另一个加在声卡,大家注意一下。

   ```
   hostpci0: 0000:00:02.0,legacy-igd=1,romfile=gen12_igd.rom
   hostpci1: 0000:00:1f.3,romfile=gen12_gop.rom
   ```

### 大家可以参考我的100.conf, 注意以下事项：
 + 机型必须i440fx，（QEMU不支持Q35 核显Legacy模式下显示，可以定制QEMU支持Q35，不在本文讨论）
 + BIOS必须OVMF，Intel核显已不支持传统BIOS启动
 + 核显PCI加入legacy-igd=1以支持核显Legacy模式下显示
 + args加入：-set device.hostpci0.addr=02.0 -set device.hostpci0.x-igd-gms=0x2 -set device.hostpci0.x-igd-opregion=on
 + args中的 “-debugcon file:/root/d-debug.log -global isa-debugcon.iobase=0x402” 为调试文件，介意的不加
 + 虚拟机内存至少4G，小于4G可能有问题
 + 建议 x-igd-gms=0x2，同时注意BIOS设定：DVMT pre allocated，不要大过64M 


#### 使用限制

+ 本ROM不支持商用,仅供DIY爱好者技术研究
+ 本ROM仅支持Intel核显,不支持AMD
+ 仅支持UEFI,正常启动.安全启动暂不支持
+ 仅支持OVMF模式,seabios不支持
+ 内存至少4G，小于4G可能有问题
+ 注意BIOS设定：DVMT pre allocated，不要大过64M，64M对应x-igd-gms=0x2，如果超过64M,x-igd-gms要加大！


#### 本ROM仅在以下环境下测试,其他环境本人未测试.
+ 华南金牌760主板 + 13600CPU
+ PVE 8.0.3
+ 测试结果基本完美，有logo和启动画面，没有花屏，HDMI/DP声音正常工作。也可以完成整个windows从头安装，。

#### 油管播放4K视频：任务管理器GPU占用
> ![GPU](https://raw.githubusercontent.com/gangqizai/igd/main/test_screenshot/task_manager.PNG "GPU")

#### HDMI Audio 
> ![HDMI Audio](https://raw.githubusercontent.com/gangqizai/igd/main/test_screenshot/hdmi-audio.PNG "HDMI Audio")

#### 常见错误
> 1. 无启动Logo 显示和开机动画
> + PVE shell 用命令启动虚拟机,必须仅能看到以下声卡错误，若有其他错误，检查PVE直通设定，参考下面本人设置
>   ```
>   root@pve:/etc/pve/qemu-server# qm start 300
>   kvm: vfio: Cannot reset device 0000:00:1f.3, no available reset mechanism.
>   kvm: vfio: Cannot reset device 0000:00:1f.3, no available reset mechanism.
>   ```
>   + /etc/modprobe.d/vifo.conf 文件中不能有 disable_vga=1，有的删掉！然后命令“update-initramfs -u” 和重启PVE
   
> 2. 无HDMI/DP 声音
> + 首先检查音频控制器驱动: 设备管理器->系统设备-> HD audio 控制器，如果没有，检查芯片组和音频驱动
> + ![HD Audio controller](https://raw.githubusercontent.com/gangqizai/igd/main/test_screenshot/hdmi-audio-controller.PNG "HD Audio Controller")
> + 可以删除显卡驱动，重启后再安装
> + 核显直通模式下完整从头安装windows（本ROM支持,安装过程无花屏）
> + 

#### 欢迎提供调试信息
+ 本人仅有一台机器，无法测试更多平台，欢迎大家提供测试调试信息。
+ 在conf文件中确认打开 args: -debugcon file:/root/igd_debug.log -global isa-debugcon.iobase=0x402
+ 提供生成的调试文件：/root/igd_debug.log
+ 在PVE主机shell, 发两个命令：lspci -s 00:02.0 -xxx 和 lspci -s 00:00.0 -xxx， 把输出结果发给我


#### 如果大家不愿意用两个rom文件，也可以合成一个。

#### PVE 显卡直通设定：

>  编辑 grub，增加 intel_iommu=on
> ```
> vim /etc/default/grub
> ```
> ```
> GRUB_CMDLINE_LINUX_DEFAULT="quiet intel_iommu=on"
> ```
> ```
> update-grub
> ```
>
> 编辑 /etc/modules
> ```
> vim /etc/modules
> ```
> 增加以下module
> ```
> vfio
> vfio_iommu_type1
> vfio_pci
> vfio_virqfd
> ```
> 把显卡驱动加入黑名单
> ```
> echo "blacklist i915" >> /etc/modprobe.d/pve-blacklist.conf
> ```
> 通过设备ID绑定vfio-pci
> 执行 lspci -n | grep -E "0300" 查看并记录核显 VendorID 和 DeviceID
>
> ```
> echo "options vfio-pci ids=8086:a780" >> /etc/modprobe.d/vifo.conf
> ```
> ```
> update-initramfs -u
> reboot
> ```
### vifo.conf 没有 disable_vga=1，有的删掉！

#### PVE Windows 虚拟机 CONF：

```
args: -set device.hostpci0.addr=02.0 -set device.hostpci0.x-igd-gms=0x2 -set device.hostpci0.x-igd-opregion=on -debugcon file:/root/igd_debug.log -global isa-debugcon.iobase=0x402
bios: ovmf
boot: order=scsi0;ide0
cores: 4
cpu: host
efidisk0: local-lvm:vm-200-disk-0,efitype=4m,size=4M
hostpci0: 0000:00:02.0,legacy-igd=1,romfile=gen12_igd.rom
hostpci1: 0000:00:1f.3,romfile=gen12_gop.rom
ide0: local:iso/virtio-win-0.1.229.iso,media=cdrom,size=522284K
ide2: local:iso/Win10_22H2_English_x64.iso,media=cdrom,size=5971862K
machine: pc-i440fx-8.0
memory: 8192
meta: creation-qemu=8.0.2,ctime=1692935943
name: Win10
net0: virtio=32:02:47:A8:40:01,bridge=vmbr0,firewall=1
numa: 0
ostype: win10
scsi0: local-lvm:vm-200-disk-1,iothread=1,size=60G
scsihw: virtio-scsi-single
serial1: socket
smbios1: uuid=d9fadf8d-eae0-4cb3-a3d5-cf222c305b91
sockets: 1
usb0: host=046d:c016,usb3=1
usb1: host=1c4f:0059,usb3=1
vga: none
vmgenid: 8f84e0f9-534d-440b-bb6d-09ed75cdc167
```

Email: gangqizai@gmail.com
