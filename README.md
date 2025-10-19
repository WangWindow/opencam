# OpenCamV 多摄像头录制

使用 OpenCV 采集+录制，配合 PySide6(Qt) 事件驱动 UI 进行预览，移动窗口时不会阻塞采集/录制；支持按键控制：

- r：开始所有摄像头录制（窗口左上角显示红点与 REC）
- s：停止所有摄像头录制
- q / Esc：退出程序

预览为“单窗口马赛克”：

- 预览总宽度固定（--window-width），根据子窗口比例与设备数量自动计算高度；
- 行列按“最接近方阵”自动计算（cols≈ceil(sqrt(N))，rows=ceil(N/cols)）。

录制文件存放：`target_dir/time_dir/cam_id_time.extension`，例如：

```
outputs/20250101_120000/cam0_20250101_120000.mp4
```

## 依赖

- Python 3.10+（pyproject 当前要求 3.14，可按需调整）
- opencv-python
- loguru
- numpy
- PySide6（新的 Qt UI，替代 cv2.imshow + waitKey 轮询）

## 运行

在本仓库根目录：

```
python .\main.py --width 1920 --height 1080 --fps 30 --backend MSMF --target-dir outputs --max-devices 4 --window-width 1280
```

参数说明：

- --width / --height：每路相机目标分辨率，默认 1920x1080（若预览首帧尚未到达，会用作比例推断）
- --fps：目标帧率，默认 30
- --backend：OpenCV 后端（ANY/MSMF/DSHOW/V4L2），默认 ANY；Windows 推荐 MSMF 或 DSHOW
- --target-dir：录制文件根目录，默认 outputs
- --output-type：封装/编码预设 mp4/avi/mkv，默认 mp4（mp4v）
- --device-mask：指定设备 id，示例 "0,2-3"；若不指定则扫描 0..max-devices-1
- --max-devices：未指定 device-mask 时最大扫描数量，默认 4
- --window-width：预览总宽度（固定），默认 1280；高度自动计算
- --window-height：已废弃（忽略），高度由行列与比例计算
- --log-dir：可选日志目录；--log-level：日志级别

## 变更说明（UI 框架切换）

- 移除了所有 `cv2.imshow` 与 `cv2.waitKey` 轮询按键监听；
- 新增 `ui_qt.py` 提供 Qt 主窗口，使用 QTimer 刷新画面与 QShortcut 监听按键（非阻塞、事件驱动）；
- `main.py` 入口统一走 Qt UI；
- 采集/录制仍在后台线程中进行，即使拖动/移动窗口，采集与录制不会被阻塞；
- 旧版 `MultiCamApp.run()` 已废弃，改为抛出提示异常。

如需使用其它 UI（例如 Tkinter/Wx），可复用 `MultiCamApp.compose_mosaic()` 获取当前马赛克帧并在你的 UI 中渲染。
