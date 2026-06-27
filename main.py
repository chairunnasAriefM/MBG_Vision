# --- DAFTAR IMPORT ---
from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles     
from fastapi.responses import FileResponse      
from ultralytics import YOLO
import cv2
import numpy as np
import base64

# ==========================================
# INISIALISASI APLIKASI & KONFIGURASI
# ==========================================

app = FastAPI(title="MBG Vision API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],     
    allow_credentials=True,
    allow_methods=["*"],     
    allow_headers=["*"],     
)

# Muat Model YOLO
model = YOLO("best.pt") 

# ==========================================
# ROUTING UNTUK FRONTEND (HTML, CSS, JS)
# ==========================================

app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/")
async def serve_frontend():
    return FileResponse("frontend/index.html")


# ==========================================
# ENDPOINT 1: HTTP POST (Upload Gambar Tunggal)
# ==========================================

@app.post("/detect/")
async def detect_objects(
    file: UploadFile = File(...), 
    conf: float = Query(default=0.326, description="Confidence threshold untuk model YOLOv8")
):
    try:
        contents = await file.read()
        
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        # Menjalankan deteksi dengan nilai threshold dinamis
        results = model(img, conf=conf)

        detections_count = 0
        total_confidence = 0.0

        for r in results:
            detections_count += len(r.boxes) 
            for box in r.boxes:
                total_confidence += float(box.conf[0])
            
            img_with_boxes = r.plot()

        avg_confidence = (total_confidence / detections_count) if detections_count > 0 else 0.0

        _, buffer = cv2.imencode('.jpg', img_with_boxes)
        img_base64 = base64.b64encode(buffer).decode('utf-8')

        return {
            "image_base64": img_base64,
            "detections_count": detections_count,
            "confidence": avg_confidence
        }

    except Exception as e:
        return {"error": str(e)}


# ==========================================
# ENDPOINT 2: WEBSOCKET (Streaming Real-time)
# ==========================================

@app.websocket("/ws/detect/")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # Membaca threshold awal yang dikirim via URL handshake WebSocket (default: 0.326)
    query_params = websocket.query_params
    current_conf = float(query_params.get("conf", 0.326))
    
    try:
        while True:
            data = await websocket.receive_text()
            
            # Mendukung jika frontend mengirimkan pesan instruksi ganti threshold di tengah jalan
            if data.startswith("SET_CONF:"):
                current_conf = float(data.split(":")[1])
                continue

            encoded_data = data.split(',')[1]
            
            nparr = np.frombuffer(base64.b64decode(encoded_data), np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            # Menjalankan deteksi real-time dengan threshold terpilih
            results = model(img, conf=current_conf)
            detections_count = 0
            total_confidence = 0.0

            for r in results:
                detections_count += len(r.boxes)
                for box in r.boxes:
                    total_confidence += float(box.conf[0])
                
                img_with_boxes = r.plot() 

            avg_confidence = (total_confidence / detections_count) if detections_count > 0 else 0.0

            _, buffer = cv2.imencode('.jpg', img_with_boxes)
            img_base64 = base64.b64encode(buffer).decode('utf-8')

            await websocket.send_json({
                "image_base64": img_base64,
                "detections_count": detections_count,
                "confidence": avg_confidence
            })

    except WebSocketDisconnect:
        print("Client disconnected dari WebSocket.")
    except Exception as e:
        print(f"WebSocket Error: {str(e)}")