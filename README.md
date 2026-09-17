# ThaiAir

พยากรณ์ PM2.5 ในกรุงเทพฯ ล่วงหน้า 24 ชั่วโมงจากข้อมูล OpenAQ ด้วย FastAPI
และโมเดล `HistGradientBoostingRegressor`

หน้าเว็บ: https://thaiair-api.onrender.com

## API

- `GET /health` ตรวจว่า process ทำงานอยู่
- `GET /ready` ตรวจว่าโมเดลและข้อมูลพร้อมใช้งาน
- `GET /stations` แสดงสถานีที่เลือกพยากรณ์ได้
- `POST /predict` พยากรณ์จากสถานีและเวลาที่ระบุ
- `GET /docs` ทดลอง API ผ่าน Swagger UI

ตัวอย่าง:

```bash
curl -X POST http://localhost:8000/predict \
  -H 'Content-Type: application/json' \
  -d '{"station_id":"oa:135:5077838"}'
```

## รันด้วย Docker

```bash
docker build -f docker/Dockerfile.api -t thaiair-api .
docker run --rm -p 8000:8000 thaiair-api
```

Image พก production snapshot ของโมเดลและข้อมูลไปด้วย จึงไม่ต้องใช้ API key ตอนเสิร์ฟ
ข้อมูลจะไม่อัปเดตจนกว่าจะสร้าง snapshot และ deploy ใหม่

## Deploy

`render.yaml` กำหนด Render Web Service แผน Free ใน Singapore ไว้แล้ว เชื่อม public
GitHub repository เป็น Render Blueprint ได้โดยไม่ต้องตั้ง environment variable เพิ่ม

Free service จะหลับเมื่อไม่มี traffic และคำขอแรกหลังตื่นอาจใช้เวลาประมาณหนึ่งนาที
เพื่อป้องกันค่าใช้จ่าย อย่าเพิ่ม payment method หรือเปลี่ยน compute plan ออกจาก `free`
