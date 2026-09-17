# ThaiAir

เว็บแผนที่ PM2.5 รอบกรุงเทพฯ 25 กิโลเมตร แสดงค่าตรวจวัดล่าสุดจาก OpenAQ และเลือกดู
พยากรณ์ล่วงหน้าทุก 3 ชั่วโมงจนถึง 24 ชั่วโมงได้

- Frontend: Next.js แบบ static export สำหรับ Vercel
- API: FastAPI บน Render Free
- Model: HistGradientBoostingRegressor; ช่วงที่โมเดลไม่ชนะ baseline จะใช้ค่าล่าสุดและแสดงป้ายกำกับตรง ๆ
- Data: refresh OpenAQ เบื้องหลังทุกชั่วโมง และยังเปิดได้ด้วย snapshot เมื่อ upstream ล่มหรือไม่มี key

## รันในเครื่อง

API:

```bash
cp .env.example .env
# ใส่ OPENAQ_API_KEY ใน .env หากต้องการข้อมูลสด
docker build -f docker/Dockerfile.api -t thaiair-api .
docker run --rm --env-file .env -p 8000:8000 thaiair-api
```

Frontend:

```bash
cd web
npm install
npm run dev
```

เปิด `http://localhost:3000` ส่วน API docs อยู่ที่ `http://localhost:8000/docs`

## API

- `GET /health` — process ยังทำงาน
- `GET /ready` — โมเดลและข้อมูลพร้อม
- `GET /map-data` — สถานี พิกัด ค่าปัจจุบัน และทุกช่วงพยากรณ์สำหรับหน้าแผนที่
- `GET /stations` — รายการ station ID
- `POST /predict` — พยากรณ์สถานีเดียว โดยส่ง `horizon_hours` เป็น 3, 6, …, 24

## Deploy โดยไม่ใช้ AWS

1. เชื่อม repo นี้กับ Render Blueprint จาก `render.yaml` และใช้แผน Free
2. ตั้ง secret `OPENAQ_API_KEY` ใน Render เพื่อเปิด hourly refresh
3. สร้าง Vercel project โดยเลือก Root Directory เป็น `web`
4. ตั้ง `NEXT_PUBLIC_API_URL=https://thaiair-api.onrender.com` ใน Vercel แล้ว deploy
5. นำ URL ที่ Vercel ให้ไปตั้งใน Render เป็นทั้ง `WEB_APP_URL` และ `CORS_ORIGINS`

เมื่อไม่มี traffic Render Free อาจพัก service ทำให้คำขอแรกช้าได้ ตัวหน้าเว็บจะแจ้งสถานะนี้ให้ผู้ใช้ทราบ
ไม่ต้องใช้ Airflow หรือฐานข้อมูลสำหรับเวอร์ชันนี้
