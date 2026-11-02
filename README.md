# supermini-lipo-motor

ESP32-C3 SuperMini の下に重ねる、2 モーター駆動と LiPo 充電の拡張基板です。外形は 18 × 24 mm、2 層です。回路図のリビジョンは 1（2026-11-01）です。

SuperMini のピンヘッダ（2.54 mm、左右 1×8）に合わせたスルーホールで接続します。電池、電源スイッチ、モーターは基板端の手はんだパッド（1.5 mm ピッチ、ドリル 0.7 mm）へ配線します。

## 電源

| ネット | 役割 |
| --- | --- |
| V5 | SuperMini の 5V。TP4056 の入力（USB 充電） |
| VBAT | LiPo 正極。TP4056 の BAT |
| VSW | モータードライバの電源。外部スイッチの負荷側 |
| GND | 共通グランド |

J3 の `SW_BAT`（VBAT）と `SW_LOAD`（VSW）のあいだに電源スイッチを入れます。スイッチを入れると電池が TC118S に供給されます。

D1（B5819W）はカソードが V5、アノードが VSW です。スイッチオンのとき電池から SuperMini の 5V ピンへ給電し、USB の 5V はモーター電源へ流れません。

TP4056 の PROG は 10 kΩ で、充電電流は約 120 mA です。CE は VCC、TEMP は GND に接続しています。充電中は LED1（赤）が点灯します。

## モーター

ドライバは Fuman TC118S が 2 個です。入力は 100 Ω を直列に入れています。

| モーター | INA | INB |
| --- | --- | --- |
| M1 | GPIO4 | GPIO3 |
| M2 | GPIO10 | GPIO7 |

GPIO2、GPIO8、GPIO9 は ESP32-C3 のストラップピンです。駆動に使わないでください。

## 手はんだパッド（J3、左から）

1. BAT+
2. BAT-
3. SW_BAT（VBAT）
4. SW_LOAD（VSW）
5. M1+
6. M1-
7. M2+
8. M2-

USB 側が基板の +Y 端です。部品面を上、USB を上にしたとき、5V 列が左側、GPIO5 列が右側です。

## ファイル

| パス | 内容 |
| --- | --- |
| `supermini-lipo-motor.kicad_pro` | KiCad 10 プロジェクト |
| `symbols/` `footprints/` | 独自シンボルとワイヤパッド |
| `tools/build_board.py` | 回路図・基板・BOM の生成スクリプト |
| `fabrication/` | JLCPCB 向け Gerber、BOM、座標 |
| `production/` | 製造データの別書き出し |

KiCad 10 で `supermini-lipo-motor.kicad_pro` を開きます。生成し直す場合は、KiCad 10 の `pcbnew` が使える Python で `tools/build_board.py` を実行します。スクリプト内のパスはローカル環境向けです。

JLCPCB へ出すときは `fabrication/jlcpcb-gerber.zip` と `fabrication/bom.csv`、`fabrication/cpl.csv` を使います。ヘッダ J1/J2 とワイヤパッド J3 は BOM に含まれません。
