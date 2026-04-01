# 🖼️ Serverless Image Resizer

A **production-grade** cloud-based image resizing system built with AWS serverless architecture. Upload images and instantly generate optimized variants at multiple sizes and formats.


---

## ✨ Features

### Core
- **Image upload** with drag-and-drop or file picker
- **Automatic resizing** into preset sizes:
  - 🔹 Thumbnail: 100×100
  - 🔹 Medium: 300×300
  - 🔹 Large: 800×800
- **Format conversion** (JPEG, PNG, WebP) with compression optimization
- **Dynamic resizing** via API — custom width, height, and format

### Production
- **Pre-signed S3 upload URLs** for secure direct-to-S3 uploads
- **CloudFront CDN** delivery for fast global access
- **S3 event-driven processing** via AWS Lambda
- **Dual-mode architecture** — works locally and on AWS with a single env toggle
- **Upload progress tracking** with visual progress bar
- **Image history** with recent uploads gallery
- **Image history** with recent uploads gallery (optimized thumbnails)
- **Copy-to-clipboard** for all variant URLs
- **Structured logging** and request metadata (ID, timing)

---

## 🏗️ Architecture

```
                                 ┌──────────────┐
  Browser / Client ──────────►   │  API Gateway  │
          │                      └──────┬───────┘
          │                             │
          │  (pre-signed URL)           ▼
          └──────────────────►   ┌──────────────┐
                                 │    S3 Input   │
                                 │    Bucket     │
                                 └──────┬───────┘
                                        │ (S3 event trigger)
                                        ▼
                                 ┌──────────────┐
                                 │   Lambda      │
                                 │   (Pillow)    │
                                 └──────┬───────┘
                                        │
                                        ▼
                                 ┌──────────────┐
                                 │  S3 Output    │
                                 │  Bucket       │
                                 └──────┬───────┘
                                        │
                                        ▼
                                 ┌──────────────┐
                                 │  CloudFront   │
                                 │  CDN          │
                                 └──────────────┘
```

### AWS Services Used
| Service | Purpose |
|---------|---------|
| **Amazon S3** | Image storage (input + output buckets) |
| **AWS Lambda** | Event-driven image processing |
| **API Gateway** | REST API with validation and throttling |
| **CloudFront** | CDN for fast global image delivery |
| **CloudWatch** | Monitoring, logging, and alerting |

---

## 📁 Project Structure

```text
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI application with all endpoints
│   │   ├── config.py            # Configuration with dual-mode (local/S3)
│   │   ├── schemas.py           # Pydantic request/response models
│   │   ├── lambda_handler.py    # AWS Lambda S3 event handler
│   │   └── services/
│   │       ├── image_service.py  # Core image processing
│   │       ├── s3_service.py     # S3 operations wrapper
│   │       └── metadata_service.py # JSON metadata persistence
│   ├── requirements.txt
│   ├── lambda_requirements.txt
│   ├── .env                     # Environment configuration (ignored in VCS)
│   └── .env.example             # Template (safe for VCS)
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # React UI with glassmorphism theme
│   │   ├── api.js               # API client with progress tracking
│   │   ├── styles.css           # Dark glassmorphism design system
│   │   └── main.jsx             # Entry point
│   ├── index.html
│   └── package.json
├── deploy/
│   ├── aws-setup.md             # Step-by-step AWS deployment guide
│   └── iam-policy.json          # Least-privilege Lambda IAM policy
└── README.md
```

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- (Optional) AWS CLI configured with credentials

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API runs at `http://127.0.0.1:8000` — Docs at `/docs`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173`

---

## ⚙️ Configuration

All settings use the `IMAGE_RESIZER_` prefix and load from `backend/.env`:

```env
# Storage mode: "local" (development) or "s3" (production)
IMAGE_RESIZER_STORAGE_BACKEND=local

# AWS
IMAGE_RESIZER_AWS_REGION=ap-south-1
IMAGE_RESIZER_AWS_ACCESS_KEY_ID=your-key
IMAGE_RESIZER_AWS_SECRET_ACCESS_KEY=your-secret

# S3 Buckets
IMAGE_RESIZER_S3_INPUT_BUCKET=serverless-image-resizer-buckets-input
IMAGE_RESIZER_S3_OUTPUT_BUCKET=serverless-image-resizer-buckets-output

# CloudFront
IMAGE_RESIZER_CLOUDFRONT_DOMAIN=d1234abcdef.cloudfront.net
```

Switch from local to AWS by changing `IMAGE_RESIZER_STORAGE_BACKEND=s3`.

---

## 🌐 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check with version and storage backend |
| `POST` | `/upload` | Upload image and generate preset variants |
| `GET` | `/image/{image_id}` | Fetch image metadata by ID |
| `GET` | `/images?limit=20&offset=0` | List recent images with pagination |
| `GET` | `/resize?image_id=...&width=...&height=...&format=...` | Create custom-sized variant |
| `GET` | `/presign?filename=...&content_type=...` | Get pre-signed S3 upload URL |
| `POST` | `/confirm-upload` | Confirm S3 upload and trigger processing |

---

## ☁️ AWS Deployment

See [`deploy/aws-setup.md`](deploy/aws-setup.md) for the complete step-by-step guide with AWS CLI commands to set up:

1. S3 input/output buckets with CORS
2. Lambda function with IAM role
3. S3 → Lambda event trigger
4. API Gateway REST API
5. CloudFront CDN distribution
6. CloudWatch monitoring alarms

---

## 🔒 Security

- **IAM roles** with least-privilege access ([policy](deploy/iam-policy.json))
- **File type validation** — only JPG, PNG, WebP allowed
- **Max file size limit** — 5 MB
- **Pre-signed upload URLs** — expire after 5 minutes
- **CORS** configured for known origins
- **Request IDs** and timing headers on all responses

---

## 📊 Monitoring

- **CloudWatch Logs** — structured Lambda execution logs
- **CloudWatch Alarms** — error rate and latency alerts
- **Request metadata** — every response includes `X-Request-Id` and `X-Process-Time-Ms` headers

---

## 🏁 Success Metrics

| Metric | Target |
|--------|--------|
| Processing time | < 2 seconds per image |
| CDN latency | < 200 ms |
| Error rate | < 1% |
| Availability | 99.9% |

---

## 🔮 Future Enhancements

- AI-based auto-cropping and face detection
- Watermarking
- Batch processing
- Dashboard analytics
- DynamoDB metadata storage

---

## 💼 Author
[Shivansh Thakur](https://www.linkedin.com/in/thakur-shivansh/)
