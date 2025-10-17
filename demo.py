import cv2
import time

# 创建 VideoCapture 对象，参数 0 表示默认摄像头
cap = cv2.VideoCapture(1 + cv2.CAP_MSMF)

# 设置 Capture 属性
_ = cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*"MJPG"))
_ = cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
_ = cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
_ = cap.set(cv2.CAP_PROP_FPS, 30)


# 检查摄像头是否成功打开
if not cap.isOpened():
    print("无法打开摄像头")
    exit()
last_print_time = time.time()
frame_count = 0
start_time = time.time()
while True:
    # 逐帧读取视频
    ret, frame = cap.read()
    if not ret:
        print("无法接收帧，结束")
        break
    frame_count += 1
    # 显示当前帧
    cv2.imshow("Camera", frame)
    # 每隔5秒打印分辨率和帧率
    current_time = time.time()
    if current_time - last_print_time >= 5:
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        elapsed = current_time - start_time
        fps = frame_count / elapsed if elapsed > 0 else 0
        print(f"当前分辨率: {width}x{height}, 帧率: {fps:.2f} FPS")
        last_print_time = current_time
        frame_count = 0
        start_time = current_time
    # 按下 'q' 键退出
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break
# 释放资源并关闭窗口
cap.release()
cv2.destroyAllWindows()
