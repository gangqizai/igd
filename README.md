## Intel 核显直通 optionROM



GOP ROM 文件名       | 适用CPU平台
--------------------|-------------------------
gen12_gop.rom       | Intel 11-13代 酷睿 
5105_gop.rom        | N5105 / N5095
8505_gop.rom        | 8505

\* 大家根据主机的CPU选用相应GOP ROM，选用错误GOP ROM功能导致无启动画面
   
#### 本ROM 需要使用两个rom文件: 
> 1. **gen12_igd.rom**: 核显直通 OptionROM （基本通用）
> 2. **gen12_gop.rom**: GOP ROM （此rom从华南金牌B760主板BIOS文件提取 仅支持Intel 11-13th CPU， Intel N95/N100/N305/N5105 等属于不同核显平台，大家自行提取）

#### 把这两个rom file copy to /use/share/kvm/

#### 使用本ROM,无需修改OVMF,使用PVE自带即可!

#### 因为使用两个rom文件，conf配置文件中，一个rom文件加在显卡，另一个加在声卡,大家注意一下。
```
hostpci0: 0000:00:02.0,legacy-igd=1,romfile=gen12_igd.rom
hostpci1: 0000:00:1f.3,romfile=gen12_gop.rom
```

#### 大家可以参考我的100.conf 
其中的 “-debugcon file:/root/igd_debug.log” 为调试文件，介意的可以不加。



#### 使用限制

1) 本ROM不支持商用,仅供DIY爱好者技术研究
2)  本ROM仅支持Intel核显,不支持AMD
3) 仅支持UEFI,正常启动.安全启动暂不支持
4) 仅支持OVMF模式,seabios不支持
5) 内存至少4G，小于4G可能有问题
6) 注意BIOS设定：DVMT pre allocated，不要大过64M，64M对应x-igd-gms=0x2，如果超过64M,x-igd-gms要加大！
7) 仅在PVE8.0环境下测试, 其他环境未测试.

#### 本ROM仅在以下环境下测试,其他环境未测试.
1) 华南金牌760主板 + 13600CPU
2) PVE 8.0
3）测试结果基本完美，没有花屏，可以完成整个windows安装。

#### 欢迎提供调试信息
1. 本人仅有一台机器，无法测试更多平台，欢迎大家提供测试调试信息。
2. 在conf文件中确认打开 args: -debugcon file:/root/igd_debug.log -global isa-debugcon.iobase=0x402
3. 提供生成的调试文件：/root/igd_debug.log
4. 在PVE主机shell, 发两个命令：lspci -s 00:02.0 -xxx 和 lspci -s 00:00.0 -xxx， 把输出结果发给我


#### 本ROM应该可以支持Intel 11-13代CPU核显，Intel N95/N100/N305/N5105 等属于不同核显平台，需要提取相应核显GOP rom

#### 如果大家不愿意用两个rom文件，也可以合成一个。

#### PVE 显卡直通设定：

```
vim /etc/default/grub
```
```
GRUB_CMDLINE_LINUX_DEFAULT="quiet intel_iommu=on"
```
```
update-grub
```

```
vim /etc/modules
```
```
vfio
vfio_iommu_type1
vfio_pci
vfio_virqfd
```
```
echo "blacklist i915" >> /etc/modprobe.d/pve-blacklist.conf
```
```
echo "options vfio-pci ids=8086:a780" >> /etc/modprobe.d/vifo.conf
```
### vifo.conf 没有 disable_vga=1，有的删掉！

Email: gangqizai@gmail.com
