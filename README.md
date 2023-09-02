## Intel 核显直通 optionROM

### 本ROM 有两个rom文件:
#### gen12_igd.rom: 核显直通 OptionROM （基本通用）
#### gen12_gop.rom: GOP 驱动 （此rom从华南金牌B760主板BIOS文件提取 仅支持Intel 12th，13th CPU， Intel N95/N100/N305/N5105 等属于不同核显平台，大家自行提取）


### 因为使用两个rom文件，conf配置文件中，一个rom文件加在显卡，另一个加在声卡。
```
hostpci0: 0000:00:02.0,legacy-igd=1,romfile=gen12_igd.rom
hostpci1: 0000:00:1f.3,romfile=gen12_gop.rom
```
#### 大家可以参考我的100.conf 
其中的 “-debugcon file:/root/igd_debug.log” 为调试文件，介意的可以不加。



### 使用限制

1) 本ROM不支持商用,仅供DIY爱好者技术研究
2)  本ROM仅支持Intel核显,不支持AMD
3) 仅支持UEFI,正常启动.安全启动暂不支持
4) 仅支持OVMF模式,seabios不支持
5) 内存至少4G，小于4G可能有问题
6) 注意BIOS设定：DVMT pre allocated，不要大过64M，64M对应x-igd-gms=0x2，如果超过64M,x-igd-gms要加大！
7) 仅在PVE8.0环境下测试, 其他环境未测试.

### 本ROM仅在一以下环境下测试,其他环境未测试.
1) 华南金牌760主板 + 13600CPU
2) PVE 8.0
3）测试结果基本完美，没有花屏，可以完成整个windows安装。


### 本ROM应该可以支持Intel 11-13代CPU核显，Intel N95/N100/N305/N5105 等属于不同核显平台，需要提取相应核显GOP rom

#### 如果大家不愿意用两个rom文件，也可以合成一个。

