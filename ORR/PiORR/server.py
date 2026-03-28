from flask import Flask, request, jsonify, Response
from flask_socketio import SocketIO, emit
import threading
import cv2

AUTH_TOKEN = "bluebot123"

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

robot = None


# =========================
# AUTH
# =========================
def is_authorized(req):
    token = req.headers.get("Authorization")
    return token == AUTH_TOKEN


# =========================
# VIDEO STREAM
# =========================
def generate_frames():
    while True:
        frame = robot.capture_frame()
        if frame is None:
            continue

        _, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')


@app.route('/video')
def video():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


# =========================
# HTTP COMMAND (optional)
# =========================
@app.route('/command', methods=['POST'])
def command():
    if not is_authorized(request):
        return jsonify({"error": "unauthorized"}), 401

    cmd = request.json.get("cmd")
    execute(cmd)
    return jsonify({"status": "ok"})


# =========================
# WEBSOCKET EVENTS
# =========================
@socketio.on('connect')
def on_connect():
    print("Client connected")
    emit("status", {"msg": "connected"})


@socketio.on('command')
def on_command(data):
    cmd = data.get("cmd")
    execute(cmd)
    emit("ack", {"cmd": cmd})


# =========================
# COMMAND HANDLER
# =========================
def execute(cmd):
    print(f"[CMD] {cmd}")

    if cmd == "START":
        threading.Thread(target=robot.run_autonomous_mission).start()

    elif cmd == "LEFT":
        robot.controller.left()

    elif cmd == "RIGHT":
        robot.controller.right()

    elif cmd == "FORWARD":
        robot.controller.forward()

    elif cmd == "STOP":
        robot.controller.stop()

    elif cmd == "SEARCH":
        robot.controller.send_command("SEARCH")

    elif cmd == "RETURN":
        robot.controller.execute_return_path()


# =========================
# STATUS STREAM
# =========================
def status_loop():
    while True:
        if robot:
            socketio.emit('status', {
                "stage": robot.current_stage.value,
                "objects": [o.color.value for o in robot.retrieved_objects],
                "recording": robot.controller.recording_enabled
            })
        socketio.sleep(0.5)


# =========================
# START SERVER
# =========================
def start_server(robot_instance):
    global robot
    robot = robot_instance

    socketio.start_background_task(status_loop)
    socketio.run(app, host='0.0.0.0', port=5000)