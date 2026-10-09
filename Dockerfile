FROM python:3.12-slim

# Ngăn Python tạo bytecode .pyc và bật xuất log tức thì ra console
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Cài đặt công cụ biên dịch tối thiểu cho các gói C-extensions nếu cần
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Cài đặt dependencies từ requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Sao chép toàn bộ mã nguồn dự án vào container
COPY . .

# Port mặc định của web app (các nền tảng cloud tự truyền biến PORT)
ENV PORT=8000
EXPOSE 8000

# Lệnh khởi động server FastAPI với uvicorn
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
